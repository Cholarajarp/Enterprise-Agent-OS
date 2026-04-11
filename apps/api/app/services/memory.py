"""Short-term and long-term memory service for agent runs.

Short-term (session) memory is stored in Redis with a configurable TTL so it
expires automatically when a run finishes or idles out.  Long-term memory is
persisted in a JSONB column on the ``agent_runs`` table so it survives across
sessions and can be queried by the orchestrator on subsequent invocations.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_factory

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

_REDIS_KEY_PREFIX: str = "eos:mem"
DEFAULT_TTL_SECONDS: int = 3600  # 1 hour


# ── Data Models ────────────────────────────────────────────────────────


class MemoryEntry(BaseModel):
    """Single memory key/value record returned to callers."""

    key: str
    value: Any
    stored_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    ttl_remaining: int | None = None


class MemoryStoreResult(BaseModel):
    """Acknowledgement returned after a successful ``store`` call."""

    key: str
    short_term: bool
    long_term: bool


# ── Helpers ────────────────────────────────────────────────────────────


def _redis_key(org_id: uuid.UUID, run_id: uuid.UUID, key: str) -> str:
    """Build a namespaced Redis key.

    Format: ``eos:mem:{org_id_short}:{run_id_short}:{key}``
    """
    org_short = str(org_id).replace("-", "")[:12]
    run_short = str(run_id).replace("-", "")[:12]
    return f"{_REDIS_KEY_PREFIX}:{org_short}:{run_short}:{key}"


def _redis_pattern(org_id: uuid.UUID, run_id: uuid.UUID) -> str:
    """Build a glob pattern that matches all keys for a given run."""
    org_short = str(org_id).replace("-", "")[:12]
    run_short = str(run_id).replace("-", "")[:12]
    return f"{_REDIS_KEY_PREFIX}:{org_short}:{run_short}:*"


def _serialize(value: Any) -> str:
    """JSON-encode a value for Redis storage."""
    return json.dumps(value, default=str, separators=(",", ":"))


def _deserialize(raw: str | bytes | None) -> Any:
    """Decode a raw Redis value back to its Python representation."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


# ── Memory Service ─────────────────────────────────────────────────────


class MemoryService:
    """Dual-layer memory: Redis for short-term, PostgreSQL for long-term.

    Every ``store`` writes to both layers.  ``retrieve`` checks Redis first
    (fast, session-scoped) and falls back to PostgreSQL (durable).

    The long-term store uses the ``agent_runs.output`` JSONB column under a
    ``_memory`` namespace key so it coexists with regular run output without
    requiring a schema migration.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        redis_pool_size: int | None = None,
    ) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis_pool_size = redis_pool_size or settings.REDIS_POOL_SIZE
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    # -- Redis lifecycle --------------------------------------------------

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._pool = ConnectionPool.from_url(
                self._redis_url,
                max_connections=self._redis_pool_size,
                decode_responses=False,
            )
            self._redis = Redis(connection_pool=self._pool)
        return self._redis

    async def close(self) -> None:
        """Shut down the Redis connection pool gracefully."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None

    # -- Long-term (PostgreSQL) helpers -----------------------------------

    @staticmethod
    async def _pg_read_memory(
        org_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Read the full ``_memory`` namespace from the run's JSONB output."""
        async with async_session_factory() as db:
            row = await db.execute(
                text(
                    """
                    SELECT COALESCE(output -> '_memory', '{}'::jsonb) AS mem
                    FROM agent_runs
                    WHERE id = :run_id AND org_id = :org_id
                    """
                ),
                {"run_id": run_id, "org_id": org_id},
            )
            result = row.scalar_one_or_none()
            if result is None:
                return {}
            if isinstance(result, str):
                return json.loads(result)
            return dict(result)

    @staticmethod
    async def _pg_write_key(
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        key: str,
        value: Any,
    ) -> bool:
        """Upsert a single key into the ``_memory`` JSONB namespace."""
        try:
            async with async_session_factory() as db:
                await db.execute(
                    text(
                        """
                        UPDATE agent_runs
                        SET output = jsonb_set(
                            COALESCE(output, '{}'::jsonb),
                            ARRAY['_memory', :key],
                            :value::jsonb,
                            true
                        )
                        WHERE id = :run_id AND org_id = :org_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "org_id": org_id,
                        "key": key,
                        "value": _serialize(value),
                    },
                )
                await db.commit()
            return True
        except Exception:
            logger.warning(
                "pg_memory_write_failed",
                org_id=str(org_id),
                run_id=str(run_id),
                key=key,
            )
            return False

    @staticmethod
    async def _pg_delete_key(
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        key: str,
    ) -> bool:
        """Remove a single key from the ``_memory`` JSONB namespace."""
        try:
            async with async_session_factory() as db:
                await db.execute(
                    text(
                        """
                        UPDATE agent_runs
                        SET output = output #- ARRAY['_memory', :key]
                        WHERE id = :run_id AND org_id = :org_id
                          AND output ? '_memory'
                        """
                    ),
                    {
                        "run_id": run_id,
                        "org_id": org_id,
                        "key": key,
                    },
                )
                await db.commit()
            return True
        except Exception:
            logger.warning(
                "pg_memory_delete_failed",
                org_id=str(org_id),
                run_id=str(run_id),
                key=key,
            )
            return False

    # ── Public API ──────────────────────────────────────────────────

    async def store(
        self,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        key: str,
        value: Any,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> MemoryStoreResult:
        """Persist a key/value pair in both short-term and long-term memory.

        Args:
            org_id: Owning organisation UUID.
            run_id: The agent run this memory belongs to.
            key: Arbitrary string key (must not be empty).
            value: Any JSON-serialisable value.
            ttl_seconds: TTL for the Redis (short-term) entry.

        Returns:
            A ``MemoryStoreResult`` indicating which layers succeeded.
        """
        if not key:
            raise ValueError("Memory key must not be empty")

        redis_key = _redis_key(org_id, run_id, key)
        serialized = _serialize(value)

        # Short-term: Redis
        short_term_ok = False
        try:
            redis = await self._get_redis()
            await redis.set(redis_key, serialized, ex=ttl_seconds)
            short_term_ok = True
        except Exception:
            logger.warning(
                "redis_memory_store_failed",
                org_id=str(org_id),
                run_id=str(run_id),
                key=key,
            )

        # Long-term: PostgreSQL
        long_term_ok = await self._pg_write_key(org_id, run_id, key, value)

        logger.info(
            "memory_stored",
            org_id=str(org_id),
            run_id=str(run_id),
            key=key,
            short_term=short_term_ok,
            long_term=long_term_ok,
            ttl=ttl_seconds,
        )

        return MemoryStoreResult(
            key=key,
            short_term=short_term_ok,
            long_term=long_term_ok,
        )

    async def retrieve(
        self,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        key: str,
    ) -> MemoryEntry | None:
        """Fetch a value by key, checking Redis first then PostgreSQL.

        Args:
            org_id: Owning organisation UUID.
            run_id: The agent run this memory belongs to.
            key: The memory key to look up.

        Returns:
            A ``MemoryEntry`` if found, else ``None``.
        """
        redis_key = _redis_key(org_id, run_id, key)

        # Try short-term first
        try:
            redis = await self._get_redis()
            raw = await redis.get(redis_key)
            if raw is not None:
                ttl = await redis.ttl(redis_key)
                value = _deserialize(raw)
                logger.debug(
                    "memory_retrieved_redis",
                    org_id=str(org_id),
                    run_id=str(run_id),
                    key=key,
                )
                return MemoryEntry(
                    key=key,
                    value=value,
                    ttl_remaining=max(ttl, 0) if ttl >= 0 else None,
                )
        except Exception:
            logger.warning(
                "redis_memory_retrieve_failed",
                org_id=str(org_id),
                run_id=str(run_id),
                key=key,
            )

        # Fallback to long-term
        memory_data = await self._pg_read_memory(org_id, run_id)
        if key in memory_data:
            logger.debug(
                "memory_retrieved_pg",
                org_id=str(org_id),
                run_id=str(run_id),
                key=key,
            )
            return MemoryEntry(
                key=key,
                value=memory_data[key],
                ttl_remaining=None,  # long-term has no TTL
            )

        return None

    async def list_keys(
        self,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> list[str]:
        """Return all memory keys for a given run.

        Merges keys from both Redis and PostgreSQL (de-duplicated).

        Args:
            org_id: Owning organisation UUID.
            run_id: The agent run to list keys for.

        Returns:
            A sorted list of unique key strings.
        """
        keys: set[str] = set()

        # Redis keys
        pattern = _redis_pattern(org_id, run_id)
        prefix_len = len(pattern) - 1  # strip the trailing '*'
        try:
            redis = await self._get_redis()
            cursor: int = 0
            while True:
                cursor, batch = await redis.scan(
                    cursor=cursor, match=pattern, count=200
                )
                for raw_key in batch:
                    decoded = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
                    # Extract the user key after the prefix
                    keys.add(decoded[prefix_len:])
                if cursor == 0:
                    break
        except Exception:
            logger.warning(
                "redis_list_keys_failed",
                org_id=str(org_id),
                run_id=str(run_id),
            )

        # PostgreSQL keys
        try:
            memory_data = await self._pg_read_memory(org_id, run_id)
            keys.update(memory_data.keys())
        except Exception:
            logger.warning(
                "pg_list_keys_failed",
                org_id=str(org_id),
                run_id=str(run_id),
            )

        return sorted(keys)

    async def delete(
        self,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        key: str,
    ) -> bool:
        """Remove a key from both short-term and long-term memory.

        Args:
            org_id: Owning organisation UUID.
            run_id: The agent run this memory belongs to.
            key: The memory key to delete.

        Returns:
            ``True`` if the key was deleted from at least one layer.
        """
        redis_key = _redis_key(org_id, run_id, key)
        deleted_any = False

        # Redis
        try:
            redis = await self._get_redis()
            removed = await redis.delete(redis_key)
            if removed > 0:
                deleted_any = True
        except Exception:
            logger.warning(
                "redis_memory_delete_failed",
                org_id=str(org_id),
                run_id=str(run_id),
                key=key,
            )

        # PostgreSQL
        pg_ok = await self._pg_delete_key(org_id, run_id, key)
        if pg_ok:
            deleted_any = True

        logger.info(
            "memory_deleted",
            org_id=str(org_id),
            run_id=str(run_id),
            key=key,
            deleted=deleted_any,
        )
        return deleted_any


# ── Singleton ──────────────────────────────────────────────────────────

memory_service = MemoryService()
