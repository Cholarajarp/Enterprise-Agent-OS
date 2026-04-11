"""Knowledge ingestion and retrieval service with vector search and BM25 fallback.

Supports text, URL, and file source types.  Documents are chunked via tiktoken,
embedded through the LLM router, and stored in Qdrant.  When Qdrant is
unreachable a lightweight in-process BM25 index is used as a fallback so that
search never hard-fails in degraded conditions.

Ingestion jobs are tracked in the ``agent_runs`` table via raw SQL so the
service does not depend on a dedicated ``Ingestion`` model.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import structlog
import tiktoken
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_factory
from app.services.llm import ChatMessage, llm_router

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

SourceType = Literal["text", "url", "file"]

CHUNK_SIZE_TOKENS: int = 512
CHUNK_OVERLAP_TOKENS: int = 50
EMBEDDING_DIMENSION: int = 1536  # OpenAI-compatible default; overridden per provider
COLLECTION_PREFIX: str = "eos_kb"

_TOKENIZER_ENCODING: str = "cl100k_base"

# ── Data Models ────────────────────────────────────────────────────────


class ChunkMetadata(BaseModel):
    """Metadata stored alongside each vector point."""

    org_id: str
    domain: str
    source_type: SourceType
    chunk_index: int
    source_hash: str = ""
    ingested_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class SearchResult(BaseModel):
    """A single ranked result returned by search."""

    text: str
    score: float
    chunk_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionResult(BaseModel):
    """Summary returned after a successful ingest call."""

    job_id: uuid.UUID
    collection: str
    chunks_stored: int
    source_type: SourceType
    elapsed_ms: int


# ── BM25 Fallback Index ───────────────────────────────────────────────


class _BM25Index:
    """Minimal Okapi-BM25 index kept entirely in memory.

    This is intentionally simple -- it exists only so ``search`` can return
    *something* when the vector store is temporarily unavailable.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        # collection -> list of (doc_text, metadata_dict)
        self._docs: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        # collection -> {term: {doc_idx: freq}}
        self._index: dict[str, dict[str, dict[int, int]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self._doc_lengths: dict[str, list[int]] = defaultdict(list)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    # -- mutators ---------------------------------------------------------

    def add(
        self,
        collection: str,
        doc_text: str,
        metadata: dict[str, Any],
    ) -> None:
        tokens = self._tokenize(doc_text)
        doc_idx = len(self._docs[collection])
        self._docs[collection].append((doc_text, metadata))
        self._doc_lengths[collection].append(len(tokens))
        freq: dict[str, int] = defaultdict(int)
        for tok in tokens:
            freq[tok] += 1
        for tok, cnt in freq.items():
            self._index[collection][tok][doc_idx] = cnt

    def clear(self, collection: str) -> None:
        self._docs.pop(collection, None)
        self._index.pop(collection, None)
        self._doc_lengths.pop(collection, None)

    # -- query ------------------------------------------------------------

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = 5,
        org_id: str | None = None,
    ) -> list[SearchResult]:
        if collection not in self._docs:
            return []

        query_tokens = self._tokenize(query)
        n = len(self._docs[collection])
        if n == 0:
            return []

        avg_dl = sum(self._doc_lengths[collection]) / n
        scores: dict[int, float] = defaultdict(float)

        for term in query_tokens:
            posting = self._index[collection].get(term, {})
            df = len(posting)
            if df == 0:
                continue
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
            for doc_idx, tf in posting.items():
                dl = self._doc_lengths[collection][doc_idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / avg_dl)
                scores[doc_idx] += idf * (numerator / denominator)

        # Optional org_id filter
        candidates = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results: list[SearchResult] = []
        for doc_idx, score in candidates:
            doc_text, meta = self._docs[collection][doc_idx]
            if org_id and meta.get("org_id") != org_id:
                continue
            results.append(
                SearchResult(
                    text=doc_text,
                    score=round(score, 6),
                    chunk_index=meta.get("chunk_index", 0),
                    metadata=meta,
                )
            )
            if len(results) >= top_k:
                break

        return results


# ── Chunking Utilities ─────────────────────────────────────────────────


def _get_tokenizer() -> tiktoken.Encoding:
    return tiktoken.get_encoding(_TOKENIZER_ENCODING)


def chunk_text(
    text_body: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split *text_body* into token-bounded chunks with overlap."""
    enc = _get_tokenizer()
    tokens = enc.encode(text_body)

    if len(tokens) <= chunk_size:
        return [text_body]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        if end >= len(tokens):
            break
        start += chunk_size - overlap

    return chunks


# ── Source Loaders ─────────────────────────────────────────────────────


async def _load_text(source_config: dict[str, Any]) -> str:
    """Return raw text from the ``content`` key."""
    return str(source_config.get("content", ""))


async def _load_url(source_config: dict[str, Any]) -> str:
    """Fetch content from a URL and return as plain text."""
    url = source_config.get("url", "")
    if not url:
        raise ValueError("source_config must include a 'url' key for url source type")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def _load_file(source_config: dict[str, Any]) -> str:
    """Read file content from the ``path`` key.

    In production this would stream from S3 / object storage; for now it
    accepts a ``content`` key as a passthrough or reads a local path.
    """
    if "content" in source_config:
        return str(source_config["content"])
    path = source_config.get("path", "")
    if not path:
        raise ValueError("source_config must include 'path' or 'content' for file source type")
    # Delegate to object-store fetch in production; local read for dev
    import aiofiles  # type: ignore[import-untyped]

    async with aiofiles.open(path, mode="r", encoding="utf-8") as fh:
        return await fh.read()


_SOURCE_LOADERS: dict[SourceType, Any] = {
    "text": _load_text,
    "url": _load_url,
    "file": _load_file,
}


# ── Embedding Helper ───────────────────────────────────────────────────


async def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Generate embeddings for *chunks* via the LLM router.

    The router's ``generate`` method is repurposed: each chunk is sent as a
    user message requesting an embedding-style numeric digest.  For providers
    that expose a native ``/embeddings`` endpoint (OpenAI, Cohere, etc.) this
    should be replaced with a direct HTTP call; the current implementation is a
    portable first-pass that works across all nine supported providers.
    """
    embeddings: list[list[float]] = []
    for chunk in chunks:
        result = await llm_router.generate(
            role="worker",
            messages=[
                ChatMessage(
                    role="user",
                    content=(
                        "Generate a numerical embedding vector for the following text.  "
                        "Return ONLY a JSON array of floats with no other text.\n\n"
                        f"Text: {chunk[:2000]}"
                    ),
                )
            ],
            system_instruction=(
                "You are an embedding engine.  Output a JSON array of 64 floats "
                "between -1.0 and 1.0 that capture the semantic meaning of the input.  "
                "Output ONLY the JSON array."
            ),
            temperature=0,
            max_tokens=2048,
        )

        try:
            import json

            vec = json.loads(result.content)
            if isinstance(vec, list) and all(isinstance(v, (int, float)) for v in vec):
                embeddings.append([float(v) for v in vec])
                continue
        except Exception:
            pass

        # Deterministic fallback: hash-based pseudo-embedding
        embeddings.append(_hash_embedding(chunk))

    return embeddings


def _hash_embedding(text_body: str, dim: int = 64) -> list[float]:
    """Produce a deterministic pseudo-embedding from a SHA-256 digest.

    Not semantically meaningful -- used only when real embeddings fail so that
    ingestion can still complete.
    """
    digest = hashlib.sha256(text_body.encode("utf-8")).digest()
    # Expand to *dim* floats in [-1, 1]
    values: list[float] = []
    for i in range(dim):
        byte_val = digest[i % len(digest)]
        values.append((byte_val / 127.5) - 1.0)
    return values


# ── Knowledge Service ──────────────────────────────────────────────────


class KnowledgeService:
    """Ingest, search, and manage domain knowledge collections.

    Each organisation + domain combination maps to a dedicated Qdrant
    collection named ``{COLLECTION_PREFIX}_{org_id_short}_{domain}``.
    """

    def __init__(
        self,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ) -> None:
        self._qdrant_url = qdrant_url or settings.QDRANT_URL
        self._qdrant_api_key = qdrant_api_key or settings.QDRANT_API_KEY
        self._client: AsyncQdrantClient | None = None
        self._bm25 = _BM25Index()

    # -- Qdrant lifecycle -------------------------------------------------

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=self._qdrant_url,
                api_key=self._qdrant_api_key,
                timeout=30,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    # -- Collection naming ------------------------------------------------

    @staticmethod
    def _collection_name(org_id: uuid.UUID, domain: str) -> str:
        short_id = str(org_id).replace("-", "")[:12]
        safe_domain = re.sub(r"[^a-zA-Z0-9_]", "_", domain).lower()
        return f"{COLLECTION_PREFIX}_{short_id}_{safe_domain}"

    # -- Ensure collection ------------------------------------------------

    async def _ensure_collection(
        self,
        client: AsyncQdrantClient,
        collection: str,
        vector_size: int,
    ) -> None:
        try:
            await client.get_collection(collection)
        except (UnexpectedResponse, Exception):
            await client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", collection=collection, vector_size=vector_size)

    # -- Ingestion job tracking -------------------------------------------

    async def _record_ingestion_job(
        self,
        *,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
        domain: str,
        source_type: SourceType,
        chunks_stored: int,
        elapsed_ms: int,
        status: str = "completed",
        error: str | None = None,
    ) -> None:
        """Insert a lightweight ingestion record into the database."""
        try:
            async with async_session_factory() as db:
                await db.execute(
                    text(
                        """
                        INSERT INTO ingestion_jobs
                            (id, org_id, domain, source_type, chunks_stored,
                             elapsed_ms, status, error, created_at)
                        VALUES
                            (:id, :org_id, :domain, :source_type, :chunks_stored,
                             :elapsed_ms, :status, :error, :created_at)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "id": job_id,
                        "org_id": org_id,
                        "domain": domain,
                        "source_type": source_type,
                        "chunks_stored": chunks_stored,
                        "elapsed_ms": elapsed_ms,
                        "status": status,
                        "error": error,
                        "created_at": datetime.now(UTC),
                    },
                )
                await db.commit()
        except Exception:
            # Ingestion tracking is best-effort; never fail the main operation
            logger.warning("ingestion_job_tracking_failed", job_id=str(job_id))

    # ── Public API ──────────────────────────────────────────────────

    async def ingest(
        self,
        org_id: uuid.UUID,
        source_type: SourceType,
        source_config: dict[str, Any],
        domain: str = "general",
    ) -> IngestionResult:
        """Load, chunk, embed, and store a document.

        Args:
            org_id: Owning organisation UUID.
            source_type: One of ``"text"``, ``"url"``, ``"file"``.
            source_config: Provider-specific configuration (e.g. ``{"content": "..."}``).
            domain: Logical knowledge domain for collection partitioning.

        Returns:
            An ``IngestionResult`` summary.
        """
        job_id = uuid.uuid4()
        start = time.monotonic()
        collection = self._collection_name(org_id, domain)

        logger.info(
            "knowledge_ingest_start",
            job_id=str(job_id),
            org_id=str(org_id),
            source_type=source_type,
            domain=domain,
        )

        # 1. Load source content
        loader = _SOURCE_LOADERS.get(source_type)
        if loader is None:
            raise ValueError(f"Unsupported source_type: {source_type!r}")
        raw_text: str = await loader(source_config)

        if not raw_text.strip():
            raise ValueError("Source produced empty content; nothing to ingest")

        source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]

        # 2. Chunk
        chunks = chunk_text(raw_text)

        # 3. Embed
        embeddings = await _embed_chunks(chunks)
        vector_size = len(embeddings[0]) if embeddings else 64

        # 4. Store in Qdrant
        qdrant_ok = True
        try:
            client = await self._get_client()
            await self._ensure_collection(client, collection, vector_size)

            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload={
                        "text": chunk,
                        "org_id": str(org_id),
                        "domain": domain,
                        "source_type": source_type,
                        "chunk_index": idx,
                        "source_hash": source_hash,
                        "ingested_at": datetime.now(UTC).isoformat(),
                    },
                )
                for idx, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=True))
            ]

            await client.upsert(collection_name=collection, points=points)
        except Exception:
            qdrant_ok = False
            logger.warning(
                "qdrant_upsert_failed_falling_back_to_bm25",
                collection=collection,
                job_id=str(job_id),
            )

        # 5. Always update BM25 fallback index
        for idx, chunk in enumerate(chunks):
            meta: dict[str, Any] = {
                "org_id": str(org_id),
                "domain": domain,
                "source_type": source_type,
                "chunk_index": idx,
                "source_hash": source_hash,
            }
            self._bm25.add(collection, chunk, meta)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # 6. Record the job
        await self._record_ingestion_job(
            job_id=job_id,
            org_id=org_id,
            domain=domain,
            source_type=source_type,
            chunks_stored=len(chunks),
            elapsed_ms=elapsed_ms,
            status="completed" if qdrant_ok else "completed_bm25_only",
        )

        logger.info(
            "knowledge_ingest_complete",
            job_id=str(job_id),
            chunks=len(chunks),
            vector_size=vector_size,
            qdrant_ok=qdrant_ok,
            elapsed_ms=elapsed_ms,
        )

        return IngestionResult(
            job_id=job_id,
            collection=collection,
            chunks_stored=len(chunks),
            source_type=source_type,
            elapsed_ms=elapsed_ms,
        )

    async def search(
        self,
        org_id: uuid.UUID,
        query: str,
        domain: str = "general",
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Search for the most relevant chunks in a knowledge domain.

        Attempts Qdrant vector search first; falls back to BM25 if the vector
        store is unreachable.

        Args:
            org_id: Owning organisation UUID.
            query: Natural-language search query.
            domain: Knowledge domain to search within.
            top_k: Maximum number of results to return.

        Returns:
            A list of ``SearchResult`` objects ranked by relevance.
        """
        collection = self._collection_name(org_id, domain)

        # Attempt vector search
        try:
            client = await self._get_client()
            query_embeddings = await _embed_chunks([query])
            query_vector = query_embeddings[0]

            qdrant_results = await client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="org_id",
                            match=MatchValue(value=str(org_id)),
                        ),
                    ]
                ),
                limit=top_k,
                with_payload=True,
            )

            results: list[SearchResult] = []
            for hit in qdrant_results:
                payload = hit.payload or {}
                results.append(
                    SearchResult(
                        text=payload.get("text", ""),
                        score=round(float(hit.score), 6),
                        chunk_index=payload.get("chunk_index", 0),
                        metadata={
                            k: v
                            for k, v in payload.items()
                            if k != "text"
                        },
                    )
                )

            logger.info(
                "knowledge_search_vector",
                org_id=str(org_id),
                domain=domain,
                hits=len(results),
            )
            return results

        except Exception:
            logger.warning(
                "qdrant_search_failed_falling_back_to_bm25",
                org_id=str(org_id),
                domain=domain,
            )

        # BM25 fallback
        bm25_results = self._bm25.search(
            collection=collection,
            query=query,
            top_k=top_k,
            org_id=str(org_id),
        )
        logger.info(
            "knowledge_search_bm25_fallback",
            org_id=str(org_id),
            domain=domain,
            hits=len(bm25_results),
        )
        return bm25_results

    async def delete_collection(
        self,
        org_id: uuid.UUID,
        domain: str = "general",
    ) -> bool:
        """Delete the Qdrant collection and BM25 index for a domain.

        Returns ``True`` if the Qdrant collection was deleted, ``False`` if
        only the BM25 index was cleared (e.g. Qdrant unavailable).
        """
        collection = self._collection_name(org_id, domain)
        qdrant_deleted = False

        try:
            client = await self._get_client()
            await client.delete_collection(collection_name=collection)
            qdrant_deleted = True
            logger.info("qdrant_collection_deleted", collection=collection)
        except Exception:
            logger.warning("qdrant_collection_delete_failed", collection=collection)

        self._bm25.clear(collection)
        return qdrant_deleted


# ── Singleton ──────────────────────────────────────────────────────────

knowledge_service = KnowledgeService()
