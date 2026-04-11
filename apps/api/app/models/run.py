"""AgentRun SQLAlchemy model.

Tracks every invocation of a workflow, including plan, steps, cost, and output.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PGUUID, Base, OrgScopedMixin


class RunStatus(str, enum.Enum):
    """Execution status of an agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TriggerType(str, enum.Enum):
    """How the run was initiated."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    EVENT = "event"


class AgentRun(Base, OrgScopedMixin):
    """Single execution of a workflow.

    Captures the full lifecycle from trigger to completion, including
    intermediate plan, step progression, cost tracking, and output.
    """

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID, primary_key=True, default=uuid.uuid4
    )

    # ── Workflow reference ───────────────────────────────────────────
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Trigger ──────────────────────────────────────────────────────
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType, name="trigger_type", native_enum=True),
        nullable=False,
    )
    trigger_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Execution State ──────────────────────────────────────────────
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", native_enum=True),
        nullable=False,
        default=RunStatus.QUEUED,
        index=True,
    )
    plan: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    steps_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # ── Cost Tracking ────────────────────────────────────────────────
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    wall_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Result ───────────────────────────────────────────────────────
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
