"""Tool registry SQLAlchemy model.

Stores metadata for every tool available to agent workflows, including
health status, version, and an optional embedding for semantic search.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PGUUID, Base, TimestampMixin

# pgvector support -- column type imported conditionally so the module can
# still be loaded even if pgvector is not yet installed in the DB.
try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]


class ToolHealthStatus(str, enum.Enum):
    """Operational health of a registered tool."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class Tool(Base, TimestampMixin):
    """Registry entry for a callable tool.

    Tools are the external capabilities that agent workflows can invoke.
    Each tool has a SemVer version, an optional embedding for semantic
    search, and health monitoring metadata.
    """

    __tablename__ = "tools"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID, primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID,
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ── Version ──────────────────────────────────────────────────────
    version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="0.1.0",
        comment="SemVer version string (e.g. 1.2.3)",
    )

    # ── Schema & Configuration ───────────────────────────────────────
    input_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=False, default=dict, comment="JSON Schema for tool input"
    )
    output_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=False, default=dict, comment="JSON Schema for tool output"
    )
    access_scopes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True, default=list)
    examples: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=30000)
    retry_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cost_per_call: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False, default=0)

    # ── Health ───────────────────────────────────────────────────────
    health_status: Mapped[ToolHealthStatus] = mapped_column(
        Enum(ToolHealthStatus, name="tool_health_status", native_enum=True),
        nullable=False,
        default=ToolHealthStatus.HEALTHY,
    )
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Semantic Search ──────────────────────────────────────────────
    # Uses pgvector Vector(1536) for OpenAI-dimension embeddings.
    # The column is defined as a raw column type to avoid hard-failing
    # when pgvector is not yet available during initial migration.
    embedding = mapped_column(
        Vector(1536) if Vector is not None else Text,
        nullable=True,
        comment="1536-dim embedding for semantic tool search",
    )

    # ── Flags ────────────────────────────────────────────────────────
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
