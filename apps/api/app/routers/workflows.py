"""Workflow CRUD router.

All endpoints are org-scoped and align to the versioned workflow contract used
by Agent Studio.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_user
from app.middleware.org_scope import current_org_id
from app.models.audit import ActorType, AuditEventType
from app.models.workflow import Workflow, WorkflowStatus
from app.services.audit import build_audit_event

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    """Request body for creating a new workflow."""

    name: str = Field(..., min_length=1, max_length=256)
    slug: str = Field(..., min_length=1, max_length=256, pattern=r"^[a-z0-9\-]+$")
    definition: dict[str, Any] = Field(default_factory=lambda: {"steps": [], "edges": []})
    trigger_config: dict[str, Any] | None = None
    tool_scope: list[str] = Field(default_factory=list)
    budget_config: dict[str, Any] | None = None
    kpi_config: list[dict[str, Any]] | None = None
    owner_team: str | None = None


class WorkflowUpdate(BaseModel):
    """Request body for updating a workflow (creates a new version when needed)."""

    name: str | None = None
    definition: dict[str, Any] | None = None
    trigger_config: dict[str, Any] | None = None
    tool_scope: list[str] | None = None
    budget_config: dict[str, Any] | None = None
    kpi_config: list[dict[str, Any]] | None = None
    owner_team: str | None = None


class WorkflowResponse(BaseModel):
    """Serialised workflow returned to callers."""

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    version: int
    status: WorkflowStatus
    definition: dict[str, Any]
    trigger_config: dict[str, Any] | None = None
    tool_scope: list[str] | None = None
    budget_config: dict[str, Any] | None = None
    kpi_config: list[dict[str, Any]] | None = None
    owner_team: str | None = None
    created_by: uuid.UUID | None = None
    promoted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowListResponse(BaseModel):
    """Paginated list of workflows."""

    items: list[WorkflowResponse]
    next_cursor: str | None = None
    total: int


class PromoteRequest(BaseModel):
    """Body for promoting a workflow status."""

    target_status: WorkflowStatus


class DryRunResponse(BaseModel):
    """Structured dry-run output for Agent Studio simulations."""

    workflow_id: uuid.UUID
    workflow_version: int
    estimated_cost_usd: float
    estimated_steps: int
    requires_approval: bool
    plan_preview: list[dict[str, Any]]
    warnings: list[str]


def _row_to_response(row: Workflow) -> WorkflowResponse:
    return WorkflowResponse.model_validate(row)


async def _get_workflow_or_404(
    db: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Workflow:
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.org_id == org_id)
    )
    workflow = result.scalar_one_or_none()
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": "Workflow not found"},
        )
    return workflow


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> WorkflowResponse:
    """Create a new workflow definition."""

    org_id = current_org_id(request)

    existing = await db.execute(
        select(Workflow).where(Workflow.org_id == org_id, Workflow.slug == body.slug)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SLUG_EXISTS",
                "message": f"Workflow with slug '{body.slug}' already exists in this organisation",
            },
        )

    workflow = Workflow(
        org_id=org_id,
        name=body.name,
        slug=body.slug,
        version=1,
        status=WorkflowStatus.DRAFT,
        definition=body.definition,
        trigger_config=body.trigger_config,
        tool_scope=body.tool_scope,
        budget_config=body.budget_config,
        kpi_config=body.kpi_config,
        owner_team=body.owner_team,
        created_by=user.sub,
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(workflow)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.WORKFLOW_CREATED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"workflow_id": str(workflow.id), "slug": workflow.slug, "version": workflow.version},
            decision="allowed",
        )
    )

    return _row_to_response(workflow)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    status_filter: WorkflowStatus | None = Query(None, alias="status"),
    tag: str | None = Query(None),
    cursor: str | None = Query(None, description="Cursor for pagination (workflow ID)"),
    limit: int = Query(50, ge=1, le=200),
) -> WorkflowListResponse:
    """List workflows with cursor-based pagination and optional filters."""

    org_id = current_org_id(request)
    base_q = select(Workflow).where(Workflow.org_id == org_id)

    if status_filter is not None:
        base_q = base_q.where(Workflow.status == status_filter)
    if tag is not None:
        base_q = base_q.where(Workflow.tool_scope.any(tag))

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    base_q = base_q.order_by(Workflow.created_at.desc(), Workflow.id.desc())

    if cursor is not None:
        try:
            cursor_uuid = uuid.UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_CURSOR", "message": "Malformed cursor"},
            ) from exc

        cursor_row = await db.execute(select(Workflow.created_at).where(Workflow.id == cursor_uuid))
        cursor_ts = cursor_row.scalar_one_or_none()
        if cursor_ts is not None:
            base_q = base_q.where(
                (Workflow.created_at < cursor_ts)
                | ((Workflow.created_at == cursor_ts) & (Workflow.id < cursor_uuid))
            )

    result = await db.execute(base_q.limit(limit))
    rows = result.scalars().all()

    return WorkflowListResponse(
        items=[_row_to_response(row) for row in rows],
        next_cursor=str(rows[-1].id) if len(rows) == limit else None,
        total=total,
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> WorkflowResponse:
    """Retrieve a single workflow version by ID."""

    workflow = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=current_org_id(request))
    return _row_to_response(workflow)


@router.get("/{workflow_id}/versions", response_model=WorkflowListResponse)
async def list_workflow_versions(
    workflow_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> WorkflowListResponse:
    """List all stored versions for a workflow lineage."""

    org_id = current_org_id(request)
    workflow = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=org_id)

    result = await db.execute(
        select(Workflow)
        .where(Workflow.org_id == org_id, Workflow.slug == workflow.slug)
        .order_by(Workflow.version.desc())
    )
    rows = result.scalars().all()
    return WorkflowListResponse(items=[_row_to_response(row) for row in rows], next_cursor=None, total=len(rows))


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> WorkflowResponse:
    """Update a workflow and preserve historical versions."""

    org_id = current_org_id(request)
    existing = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=org_id)

    if existing.status == WorkflowStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "WORKFLOW_ARCHIVED", "message": "Cannot update an archived workflow"},
        )

    update_data = body.model_dump(exclude_unset=True)
    if existing.status == WorkflowStatus.DRAFT:
        if update_data:
            await db.execute(update(Workflow).where(Workflow.id == workflow_id).values(**update_data))
            await db.flush()
            await db.refresh(existing)
        updated = existing
    else:
        updated = Workflow(
            org_id=org_id,
            name=body.name or existing.name,
            slug=existing.slug,
            version=existing.version + 1,
            status=WorkflowStatus.DRAFT,
            definition=body.definition or existing.definition,
            trigger_config=body.trigger_config if body.trigger_config is not None else existing.trigger_config,
            tool_scope=body.tool_scope if body.tool_scope is not None else existing.tool_scope,
            budget_config=body.budget_config if body.budget_config is not None else existing.budget_config,
            kpi_config=body.kpi_config if body.kpi_config is not None else existing.kpi_config,
            owner_team=body.owner_team if body.owner_team is not None else existing.owner_team,
            created_by=user.sub,
        )
        db.add(updated)
        await db.flush()
        await db.refresh(updated)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.WORKFLOW_UPDATED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"workflow_id": str(updated.id), "version": updated.version},
            decision="allowed",
        )
    )

    return _row_to_response(updated)


@router.post("/{workflow_id}/promote", response_model=WorkflowResponse)
async def promote_workflow(
    workflow_id: uuid.UUID,
    body: PromoteRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> WorkflowResponse:
    """Promote a workflow through draft -> staging -> production."""

    org_id = current_org_id(request)
    workflow = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=org_id)

    valid_transitions: dict[WorkflowStatus, set[WorkflowStatus]] = {
        WorkflowStatus.DRAFT: {WorkflowStatus.STAGING},
        WorkflowStatus.STAGING: {WorkflowStatus.PRODUCTION},
    }
    allowed = valid_transitions.get(workflow.status, set())
    if body.target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_TRANSITION",
                "message": f"Cannot transition from {workflow.status.value} to {body.target_status.value}",
                "details": {"allowed": [value.value for value in allowed]},
            },
        )

    promoted_at = datetime.now(tz=timezone.utc) if body.target_status == WorkflowStatus.PRODUCTION else workflow.promoted_at
    await db.execute(
        update(Workflow)
        .where(Workflow.id == workflow_id)
        .values(status=body.target_status, promoted_at=promoted_at)
    )
    await db.flush()
    await db.refresh(workflow)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.WORKFLOW_PROMOTED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"workflow_id": str(workflow.id), "target_status": workflow.status.value},
            decision="allowed",
        )
    )

    return _row_to_response(workflow)


@router.post("/{workflow_id}/rollback", response_model=WorkflowResponse)
async def rollback_workflow(
    workflow_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> WorkflowResponse:
    """Rollback a workflow to the immediately previous version."""

    org_id = current_org_id(request)
    current = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=org_id)

    previous_result = await db.execute(
        select(Workflow)
        .where(
            Workflow.org_id == org_id,
            Workflow.slug == current.slug,
            Workflow.version == current.version - 1,
        )
    )
    previous = previous_result.scalar_one_or_none()
    if previous is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "NO_PREVIOUS_VERSION", "message": "No previous version to rollback to"},
        )

    previous_status = current.status if current.status != WorkflowStatus.ARCHIVED else WorkflowStatus.STAGING
    await db.execute(update(Workflow).where(Workflow.id == current.id).values(status=WorkflowStatus.ARCHIVED))
    await db.execute(update(Workflow).where(Workflow.id == previous.id).values(status=previous_status))
    await db.flush()
    await db.refresh(previous)
    return _row_to_response(previous)


@router.post("/{workflow_id}/dry-run", response_model=DryRunResponse)
async def dry_run_workflow(
    workflow_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> DryRunResponse:
    """Simulate a workflow without executing external tool calls."""

    workflow = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=current_org_id(request))
    steps = workflow.definition.get("steps", [])
    requires_approval = any(step.get("requires_approval") for step in steps if isinstance(step, dict))

    preview = [
        {
            "step_index": index,
            "step_type": step.get("type", "unknown"),
            "description": step.get("name", step.get("id", f"step-{index + 1}")),
        }
        for index, step in enumerate(steps[:10])
        if isinstance(step, dict)
    ]

    return DryRunResponse(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        estimated_cost_usd=round(max(len(steps), 1) * 0.0065, 4),
        estimated_steps=len(steps),
        requires_approval=requires_approval,
        plan_preview=preview,
        warnings=[
            "External connectors are simulated during dry-run mode.",
            "Approval gates are evaluated but never dispatched to reviewers.",
        ],
    )


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> None:
    """Soft-delete a workflow by archiving the selected version."""

    workflow = await _get_workflow_or_404(db, workflow_id=workflow_id, org_id=current_org_id(request))
    await db.execute(update(Workflow).where(Workflow.id == workflow.id).values(status=WorkflowStatus.ARCHIVED))
