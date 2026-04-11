"""Agent-run router.

Manages triggering, listing, cancelling, streaming, tracing, and cost queries
for agent runs. All endpoints are org-scoped.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.core.security import TokenPayload, get_current_user
from app.middleware.org_scope import current_org_id
from app.models.audit import ActorType, AuditEventType
from app.models.run import AgentRun, RunStatus, TriggerType
from app.services.audit import build_audit_event

router = APIRouter(prefix="/runs", tags=["runs"])


class RunCreate(BaseModel):
    """Payload for triggering a new agent run."""

    workflow_id: uuid.UUID
    workflow_version: int = Field(default=1, ge=1)
    trigger_type: TriggerType = TriggerType.MANUAL
    trigger_payload: dict[str, Any] | None = None


class RunResponse(BaseModel):
    """Serialised agent run."""

    id: uuid.UUID
    org_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version: int
    trigger_type: TriggerType
    trigger_payload: dict[str, Any] | None = None
    status: RunStatus
    plan: list[dict[str, Any]] | None = None
    steps_completed: int
    tool_calls: list[dict[str, Any]] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_cost_usd: float | None = None
    wall_time_ms: int | None = None
    error: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    items: list[RunResponse]
    next_cursor: str | None = None
    total: int


class CostBreakdown(BaseModel):
    """Cost details for a single run."""

    run_id: uuid.UUID
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost_usd: float
    cost_per_step: float
    steps_completed: int
    wall_time_ms: int | None = None


class RunTraceResponse(BaseModel):
    """Condensed trace payload for live and historical diagnostics."""

    run_id: uuid.UUID
    status: RunStatus
    plan: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


def _to_response(row: AgentRun) -> RunResponse:
    return RunResponse(
        id=row.id,
        org_id=row.org_id,
        workflow_id=row.workflow_id,
        workflow_version=row.workflow_version,
        trigger_type=row.trigger_type,
        trigger_payload=row.trigger_payload,
        status=row.status,
        plan=row.plan,
        steps_completed=row.steps_completed,
        tool_calls=row.tool_calls,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        total_cost_usd=float(row.total_cost_usd) if row.total_cost_usd is not None else None,
        wall_time_ms=row.wall_time_ms,
        error=row.error,
        output=row.output,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


async def _get_run_or_404(db: AsyncSession, *, run_id: uuid.UUID, org_id: uuid.UUID) -> AgentRun:
    result = await db.execute(select(AgentRun).where(AgentRun.id == run_id, AgentRun.org_id == org_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": "Run not found"},
        )
    return run


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    body: RunCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> RunResponse:
    """Trigger a new agent run for a given workflow."""

    org_id = current_org_id(request)
    now = datetime.now(tz=timezone.utc)

    run = AgentRun(
        org_id=org_id,
        workflow_id=body.workflow_id,
        workflow_version=body.workflow_version,
        trigger_type=body.trigger_type,
        trigger_payload=body.trigger_payload,
        status=RunStatus.QUEUED,
        started_at=now,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.RUN_STARTED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"run_id": str(run.id), "workflow_id": str(run.workflow_id), "trigger_type": run.trigger_type.value},
            decision="allowed",
            run_id=run.id,
        )
    )

    return _to_response(run)


@router.get("", response_model=RunListResponse)
async def list_runs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    workflow_id: uuid.UUID | None = Query(None),
    status_filter: RunStatus | None = Query(None, alias="status"),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> RunListResponse:
    """List runs with cursor-based pagination."""

    org_id = current_org_id(request)
    base_q = select(AgentRun).where(AgentRun.org_id == org_id)

    if workflow_id is not None:
        base_q = base_q.where(AgentRun.workflow_id == workflow_id)
    if status_filter is not None:
        base_q = base_q.where(AgentRun.status == status_filter)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()
    base_q = base_q.order_by(AgentRun.created_at.desc(), AgentRun.id.desc())

    if cursor is not None:
        try:
            cursor_uuid = uuid.UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_CURSOR", "message": "Malformed cursor"},
            ) from exc

        cursor_row = await db.execute(select(AgentRun.created_at).where(AgentRun.id == cursor_uuid))
        cursor_ts = cursor_row.scalar_one_or_none()
        if cursor_ts is not None:
            base_q = base_q.where(
                (AgentRun.created_at < cursor_ts)
                | ((AgentRun.created_at == cursor_ts) & (AgentRun.id < cursor_uuid))
            )

    result = await db.execute(base_q.limit(limit))
    rows = result.scalars().all()
    return RunListResponse(
        items=[_to_response(row) for row in rows],
        next_cursor=str(rows[-1].id) if len(rows) == limit else None,
        total=total,
    )


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> RunResponse:
    """Retrieve a single run by ID with its execution state."""

    run = await _get_run_or_404(db, run_id=run_id, org_id=current_org_id(request))
    return _to_response(run)


@router.get("/{run_id}/trace", response_model=RunTraceResponse)
async def get_run_trace(
    run_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> RunTraceResponse:
    """Return the step plan, tool call manifest, and terminal output."""

    run = await _get_run_or_404(db, run_id=run_id, org_id=current_org_id(request))
    return RunTraceResponse(
        run_id=run.id,
        status=run.status,
        plan=run.plan,
        tool_calls=run.tool_calls,
        output=run.output,
        error=run.error,
    )


@router.delete("/{run_id}", status_code=status.HTTP_200_OK, response_model=RunResponse)
async def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> RunResponse:
    """Cancel a queued, running, or approval-blocked run."""

    org_id = current_org_id(request)
    run = await _get_run_or_404(db, run_id=run_id, org_id=org_id)

    cancellable = {RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.AWAITING_APPROVAL}
    if run.status not in cancellable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "NOT_CANCELLABLE",
                "message": f"Run in status '{run.status.value}' cannot be cancelled",
            },
        )

    now = datetime.now(tz=timezone.utc)
    await db.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id)
        .values(status=RunStatus.CANCELLED, completed_at=now)
    )
    await db.flush()
    await db.refresh(run)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.RUN_CANCELLED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"run_id": str(run_id), "status": RunStatus.CANCELLED.value},
            decision="allowed",
            run_id=run_id,
        )
    )

    return _to_response(run)


@router.get("/{run_id}/stream")
async def stream_run(
    run_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> StreamingResponse:
    """Server-Sent Events stream for a running agent execution."""

    run = await _get_run_or_404(db, run_id=run_id, org_id=current_org_id(request))

    async def event_generator() -> Any:
        terminal_statuses = {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }
        last_steps = -1
        yield _sse(
            "run.started",
            {"run_id": str(run.id), "workflow_id": str(run.workflow_id), "trigger": run.trigger_type.value},
        )

        while True:
            async with async_session_factory() as session:
                row = await session.execute(select(AgentRun).where(AgentRun.id == run_id))
                current = row.scalar_one_or_none()
                if current is None:
                    yield _sse("run.failed", {"error_code": "NOT_FOUND", "error_message": "Run not found"})
                    return

                if current.steps_completed != last_steps:
                    yield _sse(
                        "step.started",
                        {"run_id": str(current.id), "step_index": current.steps_completed, "status": current.status.value},
                    )
                    last_steps = current.steps_completed

                if current.status in terminal_statuses:
                    event_name = "run.completed" if current.status == RunStatus.COMPLETED else "run.failed"
                    payload = {
                        "run_id": str(current.id),
                        "status": current.status.value,
                        "output_preview": current.output,
                        "error": current.error,
                        "cost": float(current.total_cost_usd or 0),
                        "duration_ms": current.wall_time_ms or 0,
                    }
                    yield _sse(event_name, payload)
                    return

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/cost", response_model=CostBreakdown)
async def get_run_cost(
    run_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> CostBreakdown:
    """Get cost breakdown for a completed or in-flight run."""

    run = await _get_run_or_404(db, run_id=run_id, org_id=current_org_id(request))
    input_tokens = run.input_tokens or 0
    output_tokens = run.output_tokens or 0
    total_cost = float(run.total_cost_usd or 0)
    steps = max(run.steps_completed, 1)

    return CostBreakdown(
        run_id=run.id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        total_cost_usd=total_cost,
        cost_per_step=round(total_cost / steps, 6),
        steps_completed=run.steps_completed,
        wall_time_ms=run.wall_time_ms,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event payload."""

    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
