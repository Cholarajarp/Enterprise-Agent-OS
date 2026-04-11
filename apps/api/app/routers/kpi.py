"""KPI and metrics router.

Exposes dashboard statistics, per-workflow KPI metrics, and cost breakdowns
by querying the ``kpi_snapshots`` and ``agent_runs`` tables.  All endpoints
are org-scoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_user
from app.middleware.org_scope import current_org_id
from app.models.run import AgentRun, RunStatus
from app.models.workflow import Workflow, WorkflowStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/kpi", tags=["kpi"])


# ── Response Schemas ────────────────────────────────────────────────


class DashboardStats(BaseModel):
    """High-level dashboard statistics."""

    total_runs: int
    completed_runs: int
    failed_runs: int
    success_rate: float = Field(description="Percentage of runs that completed successfully")
    avg_cost_usd: float
    total_cost_usd: float
    active_workflows: int
    avg_wall_time_ms: float


class WorkflowKPI(BaseModel):
    """Per-workflow KPI metrics."""

    workflow_id: uuid.UUID
    workflow_name: str
    total_runs: int
    completed_runs: int
    failed_runs: int
    success_rate: float
    avg_cost_usd: float
    total_cost_usd: float
    avg_wall_time_ms: float
    avg_steps: float
    last_run_at: datetime | None = None


class CostEntry(BaseModel):
    """Cost breakdown for a single grouping key."""

    key: str = Field(description="Grouping key (provider name or workflow ID)")
    label: str = Field(description="Human-readable label")
    total_cost_usd: float
    total_runs: int
    avg_cost_per_run: float
    total_input_tokens: int
    total_output_tokens: int


class CostBreakdownResponse(BaseModel):
    """Aggregated cost breakdown."""

    entries: list[CostEntry]
    total_cost_usd: float
    period_start: datetime | None = None
    period_end: datetime | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    date_from: datetime | None = Query(None, alias="from", description="Start of period (ISO 8601)"),
    date_to: datetime | None = Query(None, alias="to", description="End of period (ISO 8601)"),
) -> DashboardStats:
    """Return high-level dashboard statistics for the current organisation.

    Computes totals, success rates, average cost, and active workflow count
    from the ``agent_runs`` and ``workflows`` tables.
    """
    org_id = current_org_id(request)

    # ── Run statistics ──────────────────────────────────────────────
    run_q = select(AgentRun).where(AgentRun.org_id == org_id)
    if date_from is not None:
        run_q = run_q.where(AgentRun.created_at >= date_from)
    if date_to is not None:
        run_q = run_q.where(AgentRun.created_at <= date_to)

    stats_q = select(
        func.count(AgentRun.id).label("total_runs"),
        func.count(AgentRun.id).filter(AgentRun.status == RunStatus.COMPLETED).label("completed_runs"),
        func.count(AgentRun.id).filter(AgentRun.status == RunStatus.FAILED).label("failed_runs"),
        func.coalesce(func.avg(AgentRun.total_cost_usd), 0).label("avg_cost"),
        func.coalesce(func.sum(AgentRun.total_cost_usd), 0).label("total_cost"),
        func.coalesce(func.avg(AgentRun.wall_time_ms), 0).label("avg_wall_time"),
    ).where(AgentRun.org_id == org_id)

    if date_from is not None:
        stats_q = stats_q.where(AgentRun.created_at >= date_from)
    if date_to is not None:
        stats_q = stats_q.where(AgentRun.created_at <= date_to)

    result = await db.execute(stats_q)
    row = result.one()

    total_runs = row.total_runs or 0
    completed_runs = row.completed_runs or 0
    failed_runs = row.failed_runs or 0
    success_rate = round((completed_runs / total_runs * 100) if total_runs > 0 else 0.0, 2)

    # ── Active workflows ────────────────────────────────────────────
    active_q = select(func.count(Workflow.id)).where(
        Workflow.org_id == org_id,
        Workflow.status.in_([WorkflowStatus.PRODUCTION, WorkflowStatus.STAGING]),
    )
    active_workflows = (await db.execute(active_q)).scalar_one()

    return DashboardStats(
        total_runs=total_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        success_rate=success_rate,
        avg_cost_usd=round(float(row.avg_cost), 6),
        total_cost_usd=round(float(row.total_cost), 6),
        active_workflows=active_workflows,
        avg_wall_time_ms=round(float(row.avg_wall_time), 2),
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowKPI)
async def get_workflow_kpi(
    workflow_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
) -> WorkflowKPI:
    """Return KPI metrics for a specific workflow."""
    org_id = current_org_id(request)

    # Verify workflow exists and belongs to this org
    wf_result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.org_id == org_id)
    )
    workflow = wf_result.scalar_one_or_none()
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": "Workflow not found"},
        )

    # Aggregate run metrics for this workflow
    stats_q = select(
        func.count(AgentRun.id).label("total_runs"),
        func.count(AgentRun.id).filter(AgentRun.status == RunStatus.COMPLETED).label("completed_runs"),
        func.count(AgentRun.id).filter(AgentRun.status == RunStatus.FAILED).label("failed_runs"),
        func.coalesce(func.avg(AgentRun.total_cost_usd), 0).label("avg_cost"),
        func.coalesce(func.sum(AgentRun.total_cost_usd), 0).label("total_cost"),
        func.coalesce(func.avg(AgentRun.wall_time_ms), 0).label("avg_wall_time"),
        func.coalesce(func.avg(AgentRun.steps_completed), 0).label("avg_steps"),
        func.max(AgentRun.created_at).label("last_run_at"),
    ).where(
        AgentRun.org_id == org_id,
        AgentRun.workflow_id == workflow_id,
    )

    if date_from is not None:
        stats_q = stats_q.where(AgentRun.created_at >= date_from)
    if date_to is not None:
        stats_q = stats_q.where(AgentRun.created_at <= date_to)

    result = await db.execute(stats_q)
    row = result.one()

    total_runs = row.total_runs or 0
    completed_runs = row.completed_runs or 0
    failed_runs = row.failed_runs or 0
    success_rate = round((completed_runs / total_runs * 100) if total_runs > 0 else 0.0, 2)

    return WorkflowKPI(
        workflow_id=workflow.id,
        workflow_name=workflow.name,
        total_runs=total_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        success_rate=success_rate,
        avg_cost_usd=round(float(row.avg_cost), 6),
        total_cost_usd=round(float(row.total_cost), 6),
        avg_wall_time_ms=round(float(row.avg_wall_time), 2),
        avg_steps=round(float(row.avg_steps), 2),
        last_run_at=row.last_run_at,
    )


@router.get("/cost", response_model=CostBreakdownResponse)
async def get_cost_breakdown(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    group_by: str = Query(
        default="workflow",
        description="Group cost by 'workflow' or 'provider'",
        pattern=r"^(workflow|provider)$",
    ),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> CostBreakdownResponse:
    """Return a cost breakdown grouped by workflow or provider.

    When grouped by ``workflow``, each entry represents a workflow's total
    spend. When grouped by ``provider``, the cost is split by the model
    provider recorded in each run's trigger payload (if available).
    """
    org_id = current_org_id(request)

    if group_by == "workflow":
        return await _cost_by_workflow(db, org_id, date_from, date_to, limit)
    else:
        return await _cost_by_provider(db, org_id, date_from, date_to, limit)


# ── Internal Helpers ────────────────────────────────────────────────


async def _cost_by_workflow(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
) -> CostBreakdownResponse:
    """Aggregate cost metrics grouped by workflow_id."""
    q = (
        select(
            AgentRun.workflow_id,
            func.coalesce(func.sum(AgentRun.total_cost_usd), 0).label("total_cost"),
            func.count(AgentRun.id).label("total_runs"),
            func.coalesce(func.sum(AgentRun.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AgentRun.output_tokens), 0).label("output_tokens"),
        )
        .where(AgentRun.org_id == org_id)
        .group_by(AgentRun.workflow_id)
        .order_by(func.sum(AgentRun.total_cost_usd).desc().nulls_last())
        .limit(limit)
    )

    if date_from is not None:
        q = q.where(AgentRun.created_at >= date_from)
    if date_to is not None:
        q = q.where(AgentRun.created_at <= date_to)

    result = await db.execute(q)
    rows = result.all()

    # Fetch workflow names for labels
    wf_ids = [row.workflow_id for row in rows]
    wf_name_map: dict[uuid.UUID, str] = {}
    if wf_ids:
        wf_result = await db.execute(
            select(Workflow.id, Workflow.name).where(Workflow.id.in_(wf_ids))
        )
        wf_name_map = {wf_id: name for wf_id, name in wf_result.all()}

    grand_total = 0.0
    entries: list[CostEntry] = []
    for row in rows:
        total_cost = float(row.total_cost)
        total_runs = row.total_runs or 1
        grand_total += total_cost
        entries.append(
            CostEntry(
                key=str(row.workflow_id),
                label=wf_name_map.get(row.workflow_id, str(row.workflow_id)),
                total_cost_usd=round(total_cost, 6),
                total_runs=row.total_runs,
                avg_cost_per_run=round(total_cost / total_runs, 6),
                total_input_tokens=int(row.input_tokens),
                total_output_tokens=int(row.output_tokens),
            )
        )

    return CostBreakdownResponse(
        entries=entries,
        total_cost_usd=round(grand_total, 6),
        period_start=date_from,
        period_end=date_to,
    )


async def _cost_by_provider(
    db: AsyncSession,
    org_id: uuid.UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
) -> CostBreakdownResponse:
    """Aggregate cost metrics grouped by model provider.

    The provider is extracted from the ``trigger_payload->>'provider'`` JSON
    field when available.  Runs without a provider are grouped as
    ``"unknown"``.
    """
    q = text(
        """
        SELECT
            COALESCE(trigger_payload->>'provider', 'unknown') AS provider,
            COALESCE(SUM(total_cost_usd), 0)                 AS total_cost,
            COUNT(id)                                         AS total_runs,
            COALESCE(SUM(input_tokens), 0)                   AS input_tokens,
            COALESCE(SUM(output_tokens), 0)                  AS output_tokens
        FROM agent_runs
        WHERE org_id = :org_id
          AND (:date_from IS NULL OR created_at >= :date_from)
          AND (:date_to   IS NULL OR created_at <= :date_to)
        GROUP BY provider
        ORDER BY total_cost DESC
        LIMIT :limit
        """
    )

    result = await db.execute(
        q,
        {
            "org_id": org_id,
            "date_from": date_from,
            "date_to": date_to,
            "limit": limit,
        },
    )
    rows = result.all()

    grand_total = 0.0
    entries: list[CostEntry] = []
    for row in rows:
        total_cost = float(row.total_cost)
        total_runs = row.total_runs or 1
        grand_total += total_cost
        entries.append(
            CostEntry(
                key=row.provider,
                label=row.provider.replace("_", " ").title(),
                total_cost_usd=round(total_cost, 6),
                total_runs=row.total_runs,
                avg_cost_per_run=round(total_cost / total_runs, 6),
                total_input_tokens=int(row.input_tokens),
                total_output_tokens=int(row.output_tokens),
            )
        )

    return CostBreakdownResponse(
        entries=entries,
        total_cost_usd=round(grand_total, 6),
        period_start=date_from,
        period_end=date_to,
    )
