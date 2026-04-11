"""Knowledge management router.

Exposes endpoints for ingesting documents into the vector knowledge base,
searching knowledge collections, and deleting domains.  All endpoints are
org-scoped.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_user
from app.middleware.org_scope import current_org_id
from app.services.knowledge import (
    IngestionResult,
    SearchResult,
    SourceType,
    knowledge_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ── Request / Response Schemas ──────────────────────────────────────


class IngestRequest(BaseModel):
    """Payload for triggering a knowledge ingestion job."""

    source_type: SourceType = Field(
        ..., description="Type of source to ingest (text, url, file)"
    )
    source_config: dict[str, Any] = Field(
        ..., description="Provider-specific configuration (e.g. {'content': '...'})"
    )
    domain: str = Field(
        default="general",
        min_length=1,
        max_length=128,
        description="Knowledge domain / collection name",
    )


class IngestResponse(BaseModel):
    """Summary returned after a successful ingestion."""

    job_id: uuid.UUID
    collection: str
    chunks_stored: int
    source_type: SourceType
    elapsed_ms: int


class KnowledgeSearchResponse(BaseModel):
    """Paginated search results from the knowledge base."""

    results: list[SearchResult]
    query: str
    domain: str
    total: int


class DeleteCollectionResponse(BaseModel):
    """Result of deleting a knowledge domain."""

    domain: str
    qdrant_deleted: bool
    message: str


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_knowledge(
    body: IngestRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> IngestResponse:
    """Trigger a knowledge ingestion job.

    Loads the source content, chunks it, generates embeddings, and stores
    the vectors in the knowledge base for later retrieval.
    """
    org_id = current_org_id(request)

    logger.info(
        "knowledge_ingest_requested",
        org_id=str(org_id),
        source_type=body.source_type,
        domain=body.domain,
        user_id=str(user.sub),
    )

    try:
        result: IngestionResult = await knowledge_service.ingest(
            org_id=org_id,
            source_type=body.source_type,
            source_config=body.source_config,
            domain=body.domain,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INGESTION_ERROR",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        logger.exception("knowledge_ingest_failed", org_id=str(org_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "INGESTION_FAILED",
                "message": "Knowledge ingestion failed unexpectedly",
            },
        ) from exc

    return IngestResponse(
        job_id=result.job_id,
        collection=result.collection,
        chunks_stored=result.chunks_stored,
        source_type=result.source_type,
        elapsed_ms=result.elapsed_ms,
    )


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    request: Request,
    user: Annotated[TokenPayload, Depends(get_current_user)],
    query: str = Query(..., min_length=1, max_length=1000, description="Search query"),
    domain: str = Query(default="general", min_length=1, max_length=128),
    top_k: int = Query(default=5, ge=1, le=50, description="Number of results"),
) -> KnowledgeSearchResponse:
    """Search the knowledge base using vector similarity with BM25 fallback."""
    org_id = current_org_id(request)

    logger.info(
        "knowledge_search_requested",
        org_id=str(org_id),
        domain=domain,
        query_length=len(query),
        top_k=top_k,
    )

    try:
        results: list[SearchResult] = await knowledge_service.search(
            org_id=org_id,
            query=query,
            domain=domain,
            top_k=top_k,
        )
    except Exception as exc:
        logger.exception("knowledge_search_failed", org_id=str(org_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "SEARCH_FAILED",
                "message": "Knowledge search failed unexpectedly",
            },
        ) from exc

    return KnowledgeSearchResponse(
        results=results,
        query=query,
        domain=domain,
        total=len(results),
    )


@router.delete("/{domain}", response_model=DeleteCollectionResponse)
async def delete_knowledge_collection(
    domain: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> DeleteCollectionResponse:
    """Delete a knowledge collection for the current organisation."""
    org_id = current_org_id(request)

    logger.info(
        "knowledge_delete_requested",
        org_id=str(org_id),
        domain=domain,
        user_id=str(user.sub),
    )

    try:
        qdrant_deleted = await knowledge_service.delete_collection(
            org_id=org_id,
            domain=domain,
        )
    except Exception as exc:
        logger.exception("knowledge_delete_failed", org_id=str(org_id), domain=domain)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DELETE_FAILED",
                "message": "Failed to delete knowledge collection",
            },
        ) from exc

    message = (
        f"Collection '{domain}' deleted successfully"
        if qdrant_deleted
        else f"BM25 index for '{domain}' cleared; Qdrant collection was unavailable"
    )

    return DeleteCollectionResponse(
        domain=domain,
        qdrant_deleted=qdrant_deleted,
        message=message,
    )
