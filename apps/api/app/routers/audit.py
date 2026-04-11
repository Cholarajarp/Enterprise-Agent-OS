"""Read-only audit log router.

The audit_events table is append-only. This router exposes only GET
endpoints and returns the immutable governance ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_user
from app.middleware.org_scope import current_org_id
from app.models.audit import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    """Serialised immutable audit event."""

    id: uuid.UUID
    org_id: uuid.UUID
    run_id: uuid.UUID | None = None
    agent_id: str | None = None
    event_type: str
    actor_type: str
    actor_id: str
    payload_hash: str
    payload: dict[str, Any]
    decision: str
    prev_hash: str | None = None
    latency_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    """Paginated list of audit events."""

    items: list[AuditEventResponse]
    next_cursor: str | None = None
    total: int


@router.get("", response_model=AuditListResponse)
async def query_audit_events(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    event_type: str | None = Query(None),
    actor_id: str | None = Query(None),
    run_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> AuditListResponse:
    """Query audit events with flexible filters and cursor pagination."""

    org_id = current_org_id(request)
    base_q = select(AuditEvent).where(AuditEvent.org_id == org_id)

    if event_type is not None:
        base_q = base_q.where(AuditEvent.event_type == event_type)
    if actor_id is not None:
        base_q = base_q.where(AuditEvent.actor_id == actor_id)
    if run_id is not None:
        base_q = base_q.where(AuditEvent.run_id == run_id)
    if date_from is not None:
        base_q = base_q.where(AuditEvent.created_at >= date_from)
    if date_to is not None:
        base_q = base_q.where(AuditEvent.created_at <= date_to)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()
    base_q = base_q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())

    if cursor is not None:
        try:
            cursor_uuid = uuid.UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_CURSOR", "message": "Malformed cursor"},
            ) from exc

        cursor_row = await db.execute(select(AuditEvent.created_at).where(AuditEvent.id == cursor_uuid))
        cursor_ts = cursor_row.scalar_one_or_none()
        if cursor_ts is not None:
            base_q = base_q.where(
                (AuditEvent.created_at < cursor_ts)
                | ((AuditEvent.created_at == cursor_ts) & (AuditEvent.id < cursor_uuid))
            )

    result = await db.execute(base_q.limit(limit))
    rows = result.scalars().all()
    return AuditListResponse(
        items=[AuditEventResponse.model_validate(row) for row in rows],
        next_cursor=str(rows[-1].id) if len(rows) == limit else None,
        total=total,
    )


@router.get("/{run_id}", response_model=AuditListResponse)
async def get_audit_events_for_run(
    run_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> AuditListResponse:
    """Retrieve all audit events associated with a specific agent run."""

    org_id = current_org_id(request)
    base_q = select(AuditEvent).where(AuditEvent.org_id == org_id, AuditEvent.run_id == run_id)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()
    base_q = base_q.order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())

    if cursor is not None:
        try:
            cursor_uuid = uuid.UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_CURSOR", "message": "Malformed cursor"},
            ) from exc

        cursor_row = await db.execute(select(AuditEvent.created_at).where(AuditEvent.id == cursor_uuid))
        cursor_ts = cursor_row.scalar_one_or_none()
        if cursor_ts is not None:
            base_q = base_q.where(
                (AuditEvent.created_at > cursor_ts)
                | ((AuditEvent.created_at == cursor_ts) & (AuditEvent.id > cursor_uuid))
            )

    result = await db.execute(base_q.limit(limit))
    rows = result.scalars().all()
    return AuditListResponse(
        items=[AuditEventResponse.model_validate(row) for row in rows],
        next_cursor=str(rows[-1].id) if len(rows) == limit else None,
        total=total,
    )
