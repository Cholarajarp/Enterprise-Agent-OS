"""SQLAlchemy declarative base, common mixins, and type helpers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Consistent naming convention for constraints (keeps Alembic autogenerate clean).
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Application-wide declarative base with naming conventions."""

    metadata = MetaData(naming_convention=convention)


# ── Type helpers ────────────────────────────────────────────────────
PGUUID = PG_UUID(as_uuid=True)
"""PostgreSQL-native UUID type, mapped to Python ``uuid.UUID``."""


# ── Mixins ──────────────────────────────────────────────────────────
class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` audit columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class OrgScopedMixin:
    """Adds an ``org_id`` column for row-level organisation scoping."""

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID,
        nullable=False,
        index=True,
    )
