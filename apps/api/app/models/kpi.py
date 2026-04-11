"""KPI snapshot SQLAlchemy model aligned with the platform ledger schema."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BIGINT, DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import PGUUID, Base, OrgScopedMixin


class KPISnapshot(Base, OrgScopedMixin):
    """Aggregated workflow KPI snapshot for a time window."""

    __tablename__ = "kpi_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID, primary_key=True, default=uuid.uuid4
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_cycle_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    p50_cycle_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    p95_cycle_time_ms: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    cost_per_run: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    human_hours_saved: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    error_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    approval_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    sla_compliance: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
