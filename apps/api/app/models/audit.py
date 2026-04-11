"""Audit and Approval SQLAlchemy models.

AuditEvent is an APPEND-ONLY table. No UPDATE or DELETE operations should ever
be performed against it. A PostgreSQL trigger must be installed to enforce this
at the database level:

    -- Enforce append-only on audit_events
    CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'audit_events is append-only: % not allowed', TG_OP;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_audit_events_no_update
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PGUUID, Base, OrgScopedMixin


class AuditEventType(str, enum.Enum):
    """Categories of auditable actions."""

    TOOL_CALL = "tool_call"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    INJECTION_DETECTED = "injection_detected"
    SCOPE_VIOLATION = "scope_violation"
    PII_REDACTED = "pii_redacted"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_UPDATED = "workflow_updated"
    WORKFLOW_PROMOTED = "workflow_promoted"
    TOOL_REGISTERED = "tool_registered"
    TOOL_UPDATED = "tool_updated"


class ActorType(str, enum.Enum):
    """Actor category for immutable audit entries."""

    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


class AuditEvent(Base, OrgScopedMixin):
    """Immutable audit log entry.

    This table is **append-only**. The PostgreSQL trigger
    ``trg_audit_events_no_update`` prevents any UPDATE or DELETE.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID, primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID,
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(ActorType, name="actor_type", native_enum=True),
        nullable=False,
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # ── Context ──────────────────────────────────────────────────────
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


# ── Approval ─────────────────────────────────────────────────────────


class ApprovalStatus(str, enum.Enum):
    """Decision state for an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


class ApprovalRequest(Base, OrgScopedMixin):
    """Human-in-the-loop approval gate.

    Created when an agent run reaches a step that requires explicit approval
    before proceeding.
    """

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID, primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID,
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    required_role: Mapped[str] = mapped_column(String(128), nullable=False)

    # ── Decision ─────────────────────────────────────────────────────
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status", native_enum=True),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(PGUUID, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID, nullable=True)
    decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
