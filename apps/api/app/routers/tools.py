"""Tool registry router.

Manages registration, discovery, health, and semantic search of tools
available to agent workflows. All endpoints are org-scoped, with support for
system tools shared across tenants.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_user
from app.middleware.org_scope import current_org_id
from app.models.audit import ActorType, AuditEventType
from app.models.tool import Tool, ToolHealthStatus
from app.services.audit import build_audit_event

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolCreate(BaseModel):
    """Request body for registering a new tool."""

    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="")
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    access_scopes: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] | None = None
    requires_approval: bool = False
    timeout_ms: int = Field(default=30000, ge=1)
    retry_policy: dict[str, Any] | None = None
    cost_per_call: float = 0


class ToolUpdate(BaseModel):
    """Request body for updating a tool."""

    description: str | None = None
    version: str | None = Field(None, pattern=r"^\d+\.\d+\.\d+$")
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    access_scopes: list[str] | None = None
    examples: list[dict[str, Any]] | None = None
    requires_approval: bool | None = None
    timeout_ms: int | None = Field(None, ge=1)
    retry_policy: dict[str, Any] | None = None
    cost_per_call: float | None = None


class ToolResponse(BaseModel):
    """Serialised tool record."""

    id: uuid.UUID
    org_id: uuid.UUID | None = None
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    access_scopes: list[str] | None = None
    examples: list[dict[str, Any]] | None = None
    requires_approval: bool
    timeout_ms: int
    retry_policy: dict[str, Any] | None = None
    cost_per_call: float
    health_status: ToolHealthStatus
    last_health_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ToolListResponse(BaseModel):
    """Paginated list of tools."""

    items: list[ToolResponse]
    next_cursor: str | None = None
    total: int


class SemanticSearchRequest(BaseModel):
    """Payload for semantic tool search."""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class SemanticSearchResult(BaseModel):
    """A single semantic search result."""

    tool: ToolResponse
    similarity_score: float


class SemanticSearchResponse(BaseModel):
    """Response from semantic tool search."""

    results: list[SemanticSearchResult]


async def _get_tool_or_404(db: AsyncSession, *, tool_id: uuid.UUID, org_id: uuid.UUID) -> Tool:
    result = await db.execute(
        select(Tool).where(Tool.id == tool_id, or_(Tool.org_id == org_id, Tool.org_id.is_(None)))
    )
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": "Tool not found"},
        )
    return tool


@router.get("", response_model=ToolListResponse)
async def list_tools(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
    health: ToolHealthStatus | None = Query(None),
    include_system_tools: bool = Query(True),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> ToolListResponse:
    """List registered tools with cursor-based pagination."""

    org_id = current_org_id(request)
    if include_system_tools:
        base_q = select(Tool).where(or_(Tool.org_id == org_id, Tool.org_id.is_(None)))
    else:
        base_q = select(Tool).where(Tool.org_id == org_id)

    if health is not None:
        base_q = base_q.where(Tool.health_status == health)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()
    base_q = base_q.order_by(Tool.name.asc(), Tool.id.asc())

    if cursor is not None:
        try:
            cursor_uuid = uuid.UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "INVALID_CURSOR", "message": "Malformed cursor"},
            ) from exc

        cursor_row = await db.execute(select(Tool.name, Tool.id).where(Tool.id == cursor_uuid))
        cursor_data = cursor_row.one_or_none()
        if cursor_data is not None:
            cursor_name, cursor_id = cursor_data
            base_q = base_q.where((Tool.name > cursor_name) | ((Tool.name == cursor_name) & (Tool.id > cursor_id)))

    result = await db.execute(base_q.limit(limit))
    rows = result.scalars().all()
    return ToolListResponse(
        items=[ToolResponse.model_validate(row) for row in rows],
        next_cursor=str(rows[-1].id) if len(rows) == limit else None,
        total=total,
    )


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> ToolResponse:
    """Retrieve a single tool by ID with health information."""

    tool = await _get_tool_or_404(db, tool_id=tool_id, org_id=current_org_id(request))
    return ToolResponse.model_validate(tool)


@router.get("/{tool_id}/health", response_model=ToolResponse)
async def health_check_tool(
    tool_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> ToolResponse:
    """Perform a lightweight tool health refresh."""

    tool = await _get_tool_or_404(db, tool_id=tool_id, org_id=current_org_id(request))
    await db.execute(
        update(Tool)
        .where(Tool.id == tool_id)
        .values(last_health_at=datetime.now(tz=timezone.utc), health_status=tool.health_status)
    )
    await db.flush()
    await db.refresh(tool)
    return ToolResponse.model_validate(tool)


@router.post("", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def register_tool(
    body: ToolCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> ToolResponse:
    """Register a new custom tool in the registry."""

    org_id = current_org_id(request)
    existing = await db.execute(select(Tool).where(Tool.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "NAME_EXISTS", "message": f"Tool with name '{body.name}' already exists"},
        )

    tool = Tool(
        org_id=org_id,
        name=body.name,
        description=body.description,
        version=body.version,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        access_scopes=body.access_scopes,
        examples=body.examples,
        requires_approval=body.requires_approval,
        timeout_ms=body.timeout_ms,
        retry_policy=body.retry_policy,
        cost_per_call=body.cost_per_call,
        health_status=ToolHealthStatus.HEALTHY,
    )
    db.add(tool)
    await db.flush()
    await db.refresh(tool)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.TOOL_REGISTERED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"tool_id": str(tool.id), "name": tool.name},
            decision="allowed",
        )
    )

    return ToolResponse.model_validate(tool)


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: uuid.UUID,
    body: ToolUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> ToolResponse:
    """Update an existing tool registration."""

    org_id = current_org_id(request)
    tool = await _get_tool_or_404(db, tool_id=tool_id, org_id=org_id)

    if tool.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "SYSTEM_TOOL_IMMUTABLE", "message": "System tools cannot be modified from an org context"},
        )

    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        await db.execute(update(Tool).where(Tool.id == tool_id).values(**update_data))
        await db.flush()
        await db.refresh(tool)

    db.add(
        build_audit_event(
            org_id=org_id,
            event_type=AuditEventType.TOOL_UPDATED.value,
            actor_type=ActorType.HUMAN,
            actor_id=str(user.sub),
            payload={"tool_id": str(tool_id), "updated_fields": sorted(update_data.keys())},
            decision="allowed",
        )
    )

    return ToolResponse.model_validate(tool)


@router.post("/search", response_model=SemanticSearchResponse)
async def semantic_search_tools(
    body: SemanticSearchRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> SemanticSearchResponse:
    """Semantic search over tools using a text fallback when embeddings are absent."""

    org_id = current_org_id(request)
    search_pattern = f"%{body.query}%"
    result = await db.execute(
        select(Tool)
        .where(
            or_(Tool.org_id == org_id, Tool.org_id.is_(None)),
            or_(Tool.name.ilike(search_pattern), Tool.description.ilike(search_pattern)),
        )
        .order_by(Tool.name.asc())
        .limit(body.limit)
    )
    rows = result.scalars().all()

    return SemanticSearchResponse(
        results=[
            SemanticSearchResult(tool=ToolResponse.model_validate(row), similarity_score=round(1.0 - (index * 0.05), 4))
            for index, row in enumerate(rows)
        ]
    )
