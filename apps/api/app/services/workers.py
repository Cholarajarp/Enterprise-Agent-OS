"""NATS JetStream background workers for run execution and health monitoring.

Provides three worker types that subscribe to NATS JetStream subjects:

- **RunWorker**: Picks up queued runs from ``runs.execute`` and delegates
  to the orchestrator for plan/act/observe execution.
- **KPIWorker**: Listens on ``runs.completed`` to compute real-time KPI
  snapshots (success rate, latency percentiles, cost aggregates).
- **HealthWorker**: Periodically probes registered tool connectors and
  persists health status back to the database.

All workers run as managed ``asyncio.Task`` instances under a single
``WorkerManager``, which owns the NATS connection lifecycle and
provides coordinated graceful shutdown.
"""

from __future__ import annotations

import asyncio
import json
import signal
import uuid
from datetime import UTC, datetime
from typing import Any

import nats
import structlog
from nats.aio.client import Client as NATSClient
from nats.js import JetStreamContext
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    RetentionPolicy,
    StreamConfig,
)

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.run import AgentRun, RunStatus
from app.services.orchestrator import Orchestrator, orchestrator

logger = structlog.get_logger(__name__)

# ── Stream / subject constants ─────────────────────────────────────

STREAM_NAME = "RUNS"
SUBJECT_EXECUTE = "runs.execute"
SUBJECT_COMPLETED = "runs.completed"

CONSUMER_EXECUTE = "run-executor"
CONSUMER_KPI = "kpi-aggregator"

HEALTH_CHECK_INTERVAL_SECONDS = 60


# ── RunWorker ──────────────────────────────────────────────────────


class RunWorker:
    """Subscribes to ``runs.execute``, picks up queued runs, and calls
    :pymethod:`Orchestrator.execute_run`.

    Each message payload is a JSON object with at least ``{"run_id": "<uuid>"}``.
    Messages are individually acknowledged after the orchestrator completes
    (or fails) the run so that NATS can redeliver on crash.
    """

    def __init__(
        self,
        js: JetStreamContext,
        engine: Orchestrator | None = None,
    ) -> None:
        self._js = js
        self._orchestrator = engine or orchestrator
        self._sub: Any = None
        self._log = logger.bind(worker="RunWorker")

    async def start(self) -> None:
        """Create a pull subscription and begin consuming messages."""
        consumer_cfg = ConsumerConfig(
            durable_name=CONSUMER_EXECUTE,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            max_deliver=5,
            ack_wait=600,  # 10-minute ack window for long runs
            filter_subject=SUBJECT_EXECUTE,
        )
        self._sub = await self._js.pull_subscribe(
            SUBJECT_EXECUTE,
            durable=CONSUMER_EXECUTE,
            config=consumer_cfg,
        )
        self._log.info("subscribed", subject=SUBJECT_EXECUTE)

    async def poll(self) -> None:
        """Fetch and process a single batch of messages.

        Designed to be called repeatedly inside the worker loop managed
        by :class:`WorkerManager`.
        """
        if self._sub is None:
            return

        try:
            messages = await self._sub.fetch(batch=1, timeout=5)
        except nats.errors.TimeoutError:
            return

        for msg in messages:
            await self._handle_message(msg)

    async def _handle_message(self, msg: Any) -> None:
        """Decode a single NATS message, execute the run, and ack/nak."""
        try:
            payload: dict[str, Any] = json.loads(msg.data.decode())
            run_id_raw = payload.get("run_id")
            if run_id_raw is None:
                self._log.warning("missing_run_id", payload=payload)
                await msg.ack()
                return

            run_id = uuid.UUID(str(run_id_raw))
            self._log.info("run_picked_up", run_id=str(run_id))

            await self._orchestrator.execute_run(run_id)
            await msg.ack()

            # Publish completion event for KPI aggregation
            completion_payload = json.dumps({
                "run_id": str(run_id),
                "completed_at": datetime.now(UTC).isoformat(),
            }).encode()
            await self._js.publish(SUBJECT_COMPLETED, completion_payload)

            self._log.info("run_finished", run_id=str(run_id))

        except Exception:
            self._log.exception("run_execution_error")
            try:
                await msg.nak()
            except Exception:
                self._log.exception("nak_failed")

    async def stop(self) -> None:
        """Unsubscribe from the NATS subject."""
        if self._sub is not None:
            try:
                await self._sub.unsubscribe()
            except Exception:
                self._log.exception("unsubscribe_error")
            self._sub = None
        self._log.info("stopped")


# ── KPIWorker ──────────────────────────────────────────────────────


class KPIWorker:
    """Subscribes to ``runs.completed`` and computes KPI snapshots.

    For each completed run, the worker loads the run record from the
    database and aggregates workflow-level performance indicators:

    - **success_rate**: rolling ratio of completed vs. failed runs.
    - **p50 / p95 / p99 latency**: wall-time percentiles in milliseconds.
    - **total_cost_usd**: cumulative cost for the workflow.
    - **avg_steps**: average step count per run.

    KPI snapshots are stored in the workflow's ``kpi_config`` JSONB column
    so that the dashboard can query them without recomputation.
    """

    def __init__(self, js: JetStreamContext) -> None:
        self._js = js
        self._sub: Any = None
        self._log = logger.bind(worker="KPIWorker")

    async def start(self) -> None:
        """Create a pull subscription for completed-run events."""
        consumer_cfg = ConsumerConfig(
            durable_name=CONSUMER_KPI,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            max_deliver=3,
            ack_wait=30,
            filter_subject=SUBJECT_COMPLETED,
        )
        self._sub = await self._js.pull_subscribe(
            SUBJECT_COMPLETED,
            durable=CONSUMER_KPI,
            config=consumer_cfg,
        )
        self._log.info("subscribed", subject=SUBJECT_COMPLETED)

    async def poll(self) -> None:
        """Fetch and process a single batch of completion events."""
        if self._sub is None:
            return

        try:
            messages = await self._sub.fetch(batch=5, timeout=5)
        except nats.errors.TimeoutError:
            return

        for msg in messages:
            await self._handle_message(msg)

    async def _handle_message(self, msg: Any) -> None:
        """Compute a KPI snapshot for the workflow that owns this run."""
        try:
            payload: dict[str, Any] = json.loads(msg.data.decode())
            run_id_raw = payload.get("run_id")
            if run_id_raw is None:
                await msg.ack()
                return

            run_id = uuid.UUID(str(run_id_raw))
            await self._compute_kpi_snapshot(run_id)
            await msg.ack()

        except Exception:
            self._log.exception("kpi_computation_error")
            try:
                await msg.nak()
            except Exception:
                self._log.exception("nak_failed")

    async def _compute_kpi_snapshot(self, run_id: uuid.UUID) -> None:
        """Load recent runs for the same workflow and aggregate KPIs."""
        from sqlalchemy import func, select

        from app.models.workflow import Workflow

        async with async_session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None:
                self._log.warning("run_not_found_for_kpi", run_id=str(run_id))
                return

            workflow_id = run.workflow_id

            # Aggregate over the last 100 runs for this workflow
            stmt = (
                select(
                    func.count().label("total"),
                    func.count()
                    .filter(AgentRun.status == RunStatus.COMPLETED)
                    .label("completed"),
                    func.count()
                    .filter(AgentRun.status == RunStatus.FAILED)
                    .label("failed"),
                    func.avg(AgentRun.wall_time_ms).label("avg_latency_ms"),
                    func.percentile_cont(0.5)
                    .within_group(AgentRun.wall_time_ms)
                    .label("p50_latency_ms"),
                    func.percentile_cont(0.95)
                    .within_group(AgentRun.wall_time_ms)
                    .label("p95_latency_ms"),
                    func.percentile_cont(0.99)
                    .within_group(AgentRun.wall_time_ms)
                    .label("p99_latency_ms"),
                    func.sum(AgentRun.total_cost_usd).label("total_cost_usd"),
                    func.avg(AgentRun.steps_completed).label("avg_steps"),
                )
                .where(AgentRun.workflow_id == workflow_id)
                .where(
                    AgentRun.status.in_([RunStatus.COMPLETED, RunStatus.FAILED])
                )
                .limit(100)
            )

            result = await db.execute(stmt)
            row = result.one_or_none()
            if row is None:
                return

            total = row.total or 0
            completed = row.completed or 0
            success_rate = (completed / total * 100) if total > 0 else 0.0

            kpi_snapshot: dict[str, Any] = {
                "computed_at": datetime.now(UTC).isoformat(),
                "sample_size": total,
                "success_rate_pct": round(success_rate, 2),
                "avg_latency_ms": round(float(row.avg_latency_ms or 0), 1),
                "p50_latency_ms": round(float(row.p50_latency_ms or 0), 1),
                "p95_latency_ms": round(float(row.p95_latency_ms or 0), 1),
                "p99_latency_ms": round(float(row.p99_latency_ms or 0), 1),
                "total_cost_usd": round(float(row.total_cost_usd or 0), 6),
                "avg_steps": round(float(row.avg_steps or 0), 1),
            }

            # Persist to the workflow record
            workflow = await db.get(Workflow, workflow_id)
            if workflow is not None:
                workflow.kpi_config = kpi_snapshot
                await db.commit()

            self._log.info(
                "kpi_snapshot_computed",
                workflow_id=str(workflow_id),
                success_rate=kpi_snapshot["success_rate_pct"],
                sample_size=total,
            )

    async def stop(self) -> None:
        """Unsubscribe from the NATS subject."""
        if self._sub is not None:
            try:
                await self._sub.unsubscribe()
            except Exception:
                self._log.exception("unsubscribe_error")
            self._sub = None
        self._log.info("stopped")


# ── HealthWorker ───────────────────────────────────────────────────


class HealthWorker:
    """Periodically checks health status of all registered tool connectors.

    Runs on a fixed interval (default 60 s).  For each tool in the
    :class:`ToolRegistry`, the worker calls ``health_check()`` and
    persists the result to the ``tools`` metadata table so that
    dashboards and governance policies have up-to-date availability data.
    """

    def __init__(
        self,
        interval_seconds: int = HEALTH_CHECK_INTERVAL_SECONDS,
    ) -> None:
        self._interval = interval_seconds
        self._log = logger.bind(worker="HealthWorker")

    async def poll(self) -> None:
        """Run one cycle of health checks, then sleep for the configured interval."""
        from app.services.tools import tool_registry

        self._log.debug("health_check_cycle_start")

        results = await tool_registry.health_check_all()
        healthy_count = sum(1 for v in results.values() if v)
        total_count = len(results)

        # Persist per-tool health status to the database
        try:
            await self._persist_health(results)
        except Exception:
            self._log.exception("health_persist_error")

        self._log.info(
            "health_check_cycle_complete",
            healthy=healthy_count,
            total=total_count,
        )

        await asyncio.sleep(self._interval)

    async def _persist_health(self, results: dict[str, bool]) -> None:
        """Write health check results to the database.

        Each tool's status is stored as a JSON column on the tools
        metadata table. If the table does not exist yet, the results
        are logged only.
        """
        from sqlalchemy import text

        async with async_session_factory() as db:
            for tool_name, is_healthy in results.items():
                try:
                    await db.execute(
                        text(
                            """
                            INSERT INTO tools (name, is_healthy, last_health_check)
                            VALUES (:name, :is_healthy, :checked_at)
                            ON CONFLICT (name)
                            DO UPDATE SET
                                is_healthy = EXCLUDED.is_healthy,
                                last_health_check = EXCLUDED.last_health_check
                            """
                        ),
                        {
                            "name": tool_name,
                            "is_healthy": is_healthy,
                            "checked_at": datetime.now(UTC),
                        },
                    )
                except Exception:
                    self._log.debug(
                        "tool_health_upsert_skipped",
                        tool=tool_name,
                        reason="table may not exist yet",
                    )
            await db.commit()

    async def stop(self) -> None:
        """No persistent subscriptions to clean up."""
        self._log.info("stopped")


# ── WorkerManager ──────────────────────────────────────────────────


class WorkerManager:
    """Starts, supervises, and gracefully shuts down all background workers.

    Owns the NATS client connection and JetStream context.  Call
    :meth:`start` to connect and launch worker loops, and :meth:`stop`
    (or send ``SIGINT`` / ``SIGTERM``) for coordinated teardown.

    Usage::

        manager = WorkerManager()
        await manager.start()       # connects to NATS, launches tasks
        ...
        await manager.stop()        # cancels tasks, drains NATS, disconnects
    """

    def __init__(self, nats_url: str | None = None) -> None:
        self._nats_url = nats_url or settings.NATS_URL
        self._nc: NATSClient | None = None
        self._js: JetStreamContext | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._shutdown_event = asyncio.Event()
        self._log = logger.bind(component="WorkerManager")

        # Worker instances (created during start)
        self._run_worker: RunWorker | None = None
        self._kpi_worker: KPIWorker | None = None
        self._health_worker: HealthWorker | None = None

    # ── Connection lifecycle ────────────────────────────────────────

    async def _connect(self) -> None:
        """Establish the NATS connection and obtain a JetStream context."""
        connect_opts: dict[str, Any] = {
            "servers": [self._nats_url],
            "reconnect_time_wait": 2,
            "max_reconnect_attempts": -1,  # retry forever
            "error_cb": self._on_error,
            "disconnected_cb": self._on_disconnect,
            "reconnected_cb": self._on_reconnect,
            "closed_cb": self._on_closed,
        }
        if settings.NATS_CREDENTIALS:
            connect_opts["credentials"] = settings.NATS_CREDENTIALS

        self._nc = await nats.connect(**connect_opts)
        self._js = self._nc.jetstream()
        self._log.info("nats_connected", url=self._nats_url)

    async def _ensure_streams(self) -> None:
        """Create (or update) the JetStream streams used by workers."""
        if self._js is None:
            return

        stream_cfg = StreamConfig(
            name=STREAM_NAME,
            subjects=[f"{STREAM_NAME.lower()}.*"],
            retention=RetentionPolicy.WORK_QUEUE,
            max_msgs=1_000_000,
            max_age=86_400 * 7,  # 7 days
            storage="file",
            num_replicas=1,
        )
        try:
            await self._js.add_stream(stream_cfg)
            self._log.info("stream_ensured", stream=STREAM_NAME)
        except Exception:
            # Stream may already exist; try update instead
            try:
                await self._js.update_stream(stream_cfg)
                self._log.info("stream_updated", stream=STREAM_NAME)
            except Exception:
                self._log.exception("stream_setup_error", stream=STREAM_NAME)

    # ── NATS callbacks ──────────────────────────────────────────────

    async def _on_error(self, exc: Exception) -> None:
        self._log.error("nats_error", error=str(exc))

    async def _on_disconnect(self) -> None:
        self._log.warning("nats_disconnected")

    async def _on_reconnect(self) -> None:
        self._log.info("nats_reconnected")

    async def _on_closed(self) -> None:
        self._log.info("nats_connection_closed")

    # ── Worker loops ────────────────────────────────────────────────

    async def _run_loop(self, name: str, poll_fn: Any) -> None:
        """Generic poll loop that runs until the shutdown event is set."""
        self._log.info("worker_loop_started", worker=name)
        try:
            while not self._shutdown_event.is_set():
                try:
                    await poll_fn()
                except asyncio.CancelledError:
                    break
                except Exception:
                    self._log.exception("worker_loop_error", worker=name)
                    # Back off before retrying to avoid tight error loops
                    await asyncio.sleep(2)
        finally:
            self._log.info("worker_loop_exited", worker=name)

    # ── Public interface ────────────────────────────────────────────

    async def start(self) -> None:
        """Connect to NATS, ensure streams exist, and launch all worker tasks."""
        await self._connect()
        await self._ensure_streams()

        if self._js is None:
            raise RuntimeError("JetStream context not initialised after connect")

        # Instantiate workers
        self._run_worker = RunWorker(self._js)
        self._kpi_worker = KPIWorker(self._js)
        self._health_worker = HealthWorker()

        # Start subscriptions for JetStream-based workers
        await self._run_worker.start()
        await self._kpi_worker.start()

        # Launch long-running poll loops as tasks
        self._tasks = [
            asyncio.create_task(
                self._run_loop("RunWorker", self._run_worker.poll),
                name="worker-run",
            ),
            asyncio.create_task(
                self._run_loop("KPIWorker", self._kpi_worker.poll),
                name="worker-kpi",
            ),
            asyncio.create_task(
                self._run_loop("HealthWorker", self._health_worker.poll),
                name="worker-health",
            ),
        ]

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Signal handlers are not supported on Windows in some
                # asyncio event loop implementations.  Fall back to
                # manual shutdown via ``await manager.stop()``.
                pass

        self._log.info(
            "all_workers_started",
            worker_count=len(self._tasks),
        )

    async def stop(self) -> None:
        """Gracefully shut down all workers and close the NATS connection."""
        if self._shutdown_event.is_set():
            return
        self._shutdown_event.set()
        self._log.info("shutdown_initiated")

        # Stop individual workers (unsubscribe, clean up)
        for worker in (self._run_worker, self._kpi_worker, self._health_worker):
            if worker is not None:
                try:
                    await worker.stop()
                except Exception:
                    self._log.exception("worker_stop_error")

        # Cancel all asyncio tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Drain and close NATS
        if self._nc is not None and self._nc.is_connected:
            try:
                await self._nc.drain()
            except Exception:
                self._log.exception("nats_drain_error")
            try:
                await self._nc.close()
            except Exception:
                self._log.exception("nats_close_error")
            self._nc = None
            self._js = None

        self._log.info("shutdown_complete")

    # ── Convenience: publish a run for execution ────────────────────

    async def enqueue_run(self, run_id: uuid.UUID) -> None:
        """Publish a run-execution request to the ``runs.execute`` subject.

        Intended to be called by API route handlers after persisting a
        new :class:`AgentRun` with status ``QUEUED``.
        """
        if self._js is None:
            raise RuntimeError("WorkerManager is not started")

        payload = json.dumps({"run_id": str(run_id)}).encode()
        ack = await self._js.publish(SUBJECT_EXECUTE, payload)
        self._log.info(
            "run_enqueued",
            run_id=str(run_id),
            stream=ack.stream,
            seq=ack.seq,
        )


# ── Module-level singleton ─────────────────────────────────────────

worker_manager = WorkerManager()
