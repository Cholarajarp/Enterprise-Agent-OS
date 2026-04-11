"""Workflow SQLAlchemy model.

Represents a versioned, org-scoped agent workflow definition.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PGUUID, Base, OrgScopedMixin, TimestampMixin


class WorkflowStatus(str, enum.Enum):
    """Lifecycle status of a workflow definition."""

    DRAFT = "draft"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class Workflow(Base, OrgScopedMixin, TimestampMixin):
    """Persistent workflow definition table.

    Each row is a specific version of a workflow. The ``(org_id, slug)``
    pair uniquely identifies a workflow lineage; ``version`` distinguishes
    revisions within that lineage.
    """

    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", "version", name="uq_workflows_org_slug_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status", native_enum=True),
        nullable=False,
        default=WorkflowStatus.DRAFT,
        index=True,
    )

    # ── Definition & Configuration ───────────────────────────────────
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    trigger_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_scope: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True, default=list
    )
    budget_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    kpi_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Ownership ────────────────────────────────────────────────────
    owner_team: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Lifecycle timestamps ─────────────────────────────────────────
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
