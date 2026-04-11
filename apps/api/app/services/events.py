"""SSE event streaming service backed by Redis pub/sub.

Provides a publish/subscribe mechanism for real-time run events using
Server-Sent Events (SSE).  The architecture is:

1. **EventEmitter** publishes structured events to a Redis channel
   scoped by ``run_id``.  Any component (orchestrator, workers, API
   handlers) can call :meth:`EventEmitter.emit` to broadcast state
   changes.

2. **EventStream** subscribes to the Redis channel for a single
   ``run_id`` and yields SSE-formatted strings suitable for returning
   from a Starlette ``StreamingResponse``.  A built-in heartbeat
   keeps the connection alive when no events are flowing.

Channel naming convention::

    run:{run_id}:events

SSE wire format::

    event: {type}
    data: {json}

"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────

HEARTBEAT_INTERVAL_SECONDS = 15
CHANNEL_PREFIX = "run"
CHANNEL_SUFFIX = "events"

# Global broadcast channel for cross-run notifications (e.g. system
# alerts, deployment events).
BROADCAST_CHANNEL = "system:events"


def _channel_name(run_id: uuid.UUID | str) -> str:
    """Build the canonical Redis channel name for a run.

    Returns:
        A string of the form ``run:<run_id>:events``.
    """
    return f"{CHANNEL_PREFIX}:{run_id}:{CHANNEL_SUFFIX}"


def _format_sse(event_type: str, data: str) -> str:
    """Format a payload as a valid SSE frame.

    The output conforms to the `EventSource`_ specification:
    each field on its own line, terminated by a blank line.

    .. _EventSource: https://html.spec.whatwg.org/multipage/server-sent-events.html
    """
    return f"event: {event_type}\ndata: {data}\n\n"


# ── Redis connection pool ──────────────────────────────────────────


def _build_redis_pool() -> aioredis.Redis:
    """Create a shared async Redis client from application settings."""
    return aioredis.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_POOL_SIZE,
        decode_responses=True,
        health_check_interval=30,
    )


# Lazily initialised module-level pool.  Call :func:`get_redis` to
# obtain the shared instance.
_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the module-level Redis connection, creating it on first call."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is None:
        _redis_pool = _build_redis_pool()
    return _redis_pool


async def close_redis() -> None:
    """Cleanly shut down the Redis connection pool."""
    global _redis_pool  # noqa: PLW0603
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("redis_pool_closed")


# ── EventEmitter ───────────────────────────────────────────────────


class EventEmitter:
    """Publishes run-scoped events to Redis pub/sub.

    Typical usage inside the orchestrator or worker::

        emitter = EventEmitter()
        await emitter.emit(run_id, "step_completed", {"index": 3})
    """

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client
        self._log = logger.bind(component="EventEmitter")

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is not None:
            return self._redis
        return await get_redis()

    async def emit(
        self,
        run_id: uuid.UUID | str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> int:
        """Publish an event to the run's Redis channel.

        Args:
            run_id: UUID of the run this event belongs to.
            event_type: Logical event name (e.g. ``step_started``,
                ``run_completed``).
            data: Arbitrary JSON-serialisable payload.

        Returns:
            The number of Redis subscribers that received the message.
        """
        channel = _channel_name(run_id)
        payload = json.dumps(
            {
                "type": event_type,
                "run_id": str(run_id),
                "data": data or {},
                "timestamp": datetime.now(UTC).isoformat(),
            },
            default=str,
        )

        r = await self._get_redis()
        receivers: int = await r.publish(channel, payload)

        self._log.debug(
            "event_emitted",
            run_id=str(run_id),
            event_type=event_type,
            receivers=receivers,
        )
        return receivers

    async def broadcast(
        self,
        channel: str,
        data: dict[str, Any],
    ) -> int:
        """Publish a message to an arbitrary Redis channel.

        This is useful for system-wide broadcasts that are not tied to a
        specific run (e.g. deployment notifications, maintenance alerts).

        Args:
            channel: Full Redis channel name.
            data: JSON-serialisable payload.

        Returns:
            The number of Redis subscribers that received the message.
        """
        payload = json.dumps(
            {
                "channel": channel,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            default=str,
        )
        r = await self._get_redis()
        receivers: int = await r.publish(channel, payload)

        self._log.debug(
            "broadcast_sent",
            channel=channel,
            receivers=receivers,
        )
        return receivers


# ── EventStream ────────────────────────────────────────────────────


class EventStream:
    """Subscribes to a run's Redis channel and yields SSE-formatted strings.

    Designed to be used as the body of a ``StreamingResponse``::

        from starlette.responses import StreamingResponse

        stream = EventStream()
        return StreamingResponse(
            stream.subscribe(run_id),
            media_type="text/event-stream",
        )

    The stream automatically sends a heartbeat comment (``": ping"``)
    every :data:`HEARTBEAT_INTERVAL_SECONDS` to prevent proxies and
    browsers from closing idle connections.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._heartbeat_interval = heartbeat_interval
        self._log = logger.bind(component="EventStream")

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is not None:
            return self._redis
        return await get_redis()

    async def subscribe(
        self,
        run_id: uuid.UUID | str,
    ) -> AsyncIterator[str]:
        """Yield SSE frames for every event published to the run's channel.

        The iterator terminates when:

        - A ``run_completed``, ``run_failed``, or ``run_cancelled`` event
          is received (terminal states).
        - The Redis subscription encounters an unrecoverable error.
        - The consuming HTTP connection is closed (raises
          ``asyncio.CancelledError``).

        Yields:
            SSE-formatted strings ready for the wire.
        """
        channel = _channel_name(run_id)
        r = await self._get_redis()
        pubsub = r.pubsub()

        try:
            await pubsub.subscribe(channel)
            self._log.info("sse_subscribed", run_id=str(run_id), channel=channel)

            # Send an initial connection event
            yield _format_sse(
                "connected",
                json.dumps({
                    "run_id": str(run_id),
                    "timestamp": datetime.now(UTC).isoformat(),
                }),
            )

            terminal_events = frozenset({
                "run_completed",
                "run_failed",
                "run_cancelled",
            })

            while True:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=self._heartbeat_interval,
                        ),
                        timeout=self._heartbeat_interval + 1,
                    )
                except asyncio.TimeoutError:
                    # No message within the heartbeat window — send keep-alive
                    yield ": ping\n\n"
                    continue

                if message is None:
                    # Timeout from get_message (returned None); send heartbeat
                    yield ": ping\n\n"
                    continue

                if message["type"] != "message":
                    continue

                raw_data = message["data"]
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")

                # Parse the JSON envelope to extract the event type
                try:
                    envelope: dict[str, Any] = json.loads(raw_data)
                    event_type = envelope.get("type", "message")
                except (json.JSONDecodeError, TypeError):
                    event_type = "message"
                    envelope = {"data": raw_data}

                yield _format_sse(event_type, json.dumps(envelope, default=str))

                # Terminate on run-final events
                if event_type in terminal_events:
                    self._log.info(
                        "sse_terminal_event",
                        run_id=str(run_id),
                        event_type=event_type,
                    )
                    break

        except asyncio.CancelledError:
            self._log.info("sse_client_disconnected", run_id=str(run_id))
        except Exception:
            self._log.exception("sse_stream_error", run_id=str(run_id))
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                self._log.debug("pubsub_cleanup_error", run_id=str(run_id))
            self._log.info("sse_stream_closed", run_id=str(run_id))

    async def subscribe_broadcast(
        self,
        channel: str = BROADCAST_CHANNEL,
    ) -> AsyncIterator[str]:
        """Yield SSE frames from an arbitrary broadcast channel.

        Unlike :meth:`subscribe`, this does **not** terminate on
        run-specific events — it streams indefinitely until the client
        disconnects.

        Args:
            channel: Redis channel name to subscribe to.

        Yields:
            SSE-formatted strings.
        """
        r = await self._get_redis()
        pubsub = r.pubsub()

        try:
            await pubsub.subscribe(channel)
            self._log.info("broadcast_subscribed", channel=channel)

            yield _format_sse(
                "connected",
                json.dumps({
                    "channel": channel,
                    "timestamp": datetime.now(UTC).isoformat(),
                }),
            )

            while True:
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(
                            ignore_subscribe_messages=True,
                            timeout=self._heartbeat_interval,
                        ),
                        timeout=self._heartbeat_interval + 1,
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if message is None:
                    yield ": ping\n\n"
                    continue

                if message["type"] != "message":
                    continue

                raw_data = message["data"]
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8")

                try:
                    envelope = json.loads(raw_data)
                    event_type = envelope.get("type", "broadcast")
                except (json.JSONDecodeError, TypeError):
                    event_type = "broadcast"
                    envelope = {"data": raw_data}

                yield _format_sse(event_type, json.dumps(envelope, default=str))

        except asyncio.CancelledError:
            self._log.info("broadcast_client_disconnected", channel=channel)
        except Exception:
            self._log.exception("broadcast_stream_error", channel=channel)
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                self._log.debug("pubsub_cleanup_error", channel=channel)

    # ── Convenience: one-shot subscribe as list ─────────────────────

    async def collect(
        self,
        run_id: uuid.UUID | str,
        *,
        timeout_seconds: float = 300,
    ) -> list[dict[str, Any]]:
        """Subscribe and collect all events until the run terminates.

        Primarily intended for integration tests and CLI tooling rather
        than production SSE streaming.

        Args:
            run_id: UUID of the run to watch.
            timeout_seconds: Maximum time to wait before giving up.

        Returns:
            A list of parsed event dictionaries.
        """
        events: list[dict[str, Any]] = []

        async def _drain() -> None:
            async for frame in self.subscribe(run_id):
                # Skip heartbeat comments
                if frame.startswith(":"):
                    continue
                # Extract the JSON data line from the SSE frame
                for line in frame.strip().split("\n"):
                    if line.startswith("data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            pass

        try:
            await asyncio.wait_for(_drain(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            self._log.warning(
                "collect_timeout",
                run_id=str(run_id),
                events_collected=len(events),
            )
        return events


# ── Module-level singletons ────────────────────────────────────────

event_emitter = EventEmitter()
event_stream = EventStream()
