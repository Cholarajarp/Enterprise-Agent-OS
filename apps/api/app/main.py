"""Enterprise Agent OS API — Application entry point.

Configures the FastAPI application with lifespan management, middleware,
routers, error handlers, and observability instrumentation.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import engine
from app.middleware.org_scope import OrgScopeMiddleware
from app.routers import approvals, audit, knowledge, kpi, runs, tools, webhooks, workflows

logger = structlog.get_logger(__name__)


# ── Structured Error ─────────────────────────────────────────────────


class APIError(Exception):
    """Application-level error that maps to RFC 7807 Problem Details."""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)


# ── Lifespan ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown resources.

    On startup:
      - Verify database connectivity
      - Connect to Redis (if configured)
      - Initialize OpenTelemetry instrumentation

    On shutdown:
      - Dispose the database engine connection pool
    """
    # ── Startup ──────────────────────────────────────────────────────
    logger.info(
        "starting_api",
        environment=settings.ENVIRONMENT,
        otel_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
    )

    # Verify DB connectivity
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("database_connected")

    # Optional: Redis connection
    _redis = None
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await _redis.ping()
        logger.info("redis_connected", url=settings.REDIS_URL)
        app.state.redis = _redis
    except Exception as exc:
        logger.warning("redis_unavailable", error=str(exc))
        app.state.redis = None

    # OpenTelemetry instrumentation
    _setup_otel(app)

    # Sentry
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
        )
        logger.info("sentry_initialized")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("shutting_down")
    if _redis is not None:
        await _redis.aclose()
    await engine.dispose()
    logger.info("shutdown_complete")


# ── App Factory ──────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Enterprise Agent OS",
        description="Governed multi-agent runtime platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware (order matters: outermost first) ───────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(OrgScopeMiddleware)

    # ── Routers ──────────────────────────────────────────────────────
    app.include_router(workflows.router, prefix="/v1")
    app.include_router(runs.router, prefix="/v1")
    app.include_router(approvals.router, prefix="/v1")
    app.include_router(audit.router, prefix="/v1")
    app.include_router(tools.router, prefix="/v1")
    app.include_router(knowledge.router, prefix="/v1")
    app.include_router(kpi.router, prefix="/v1")
    app.include_router(webhooks.router, prefix="/v1")

    # ── Error Handlers ───────────────────────────────────────────────

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        """RFC 7807 Problem Details response for APIError.

        Args:
            request: The failed request.
            exc: The raised APIError.

        Returns:
            Structured JSON error response.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": f"https://enterprise-os.dev/errors/{exc.error_code}",
                "title": exc.error_code,
                "status": exc.status_code,
                "detail": exc.message,
                "instance": str(request.url),
                **exc.details,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Normalise FastAPI HTTPExceptions to RFC 7807 format.

        Args:
            request: The failed request.
            exc: The raised HTTPException.

        Returns:
            Structured JSON error response.
        """
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        error_code = detail.get("error_code", "HTTP_ERROR")
        message = detail.get("message", str(exc.detail))

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": f"https://enterprise-os.dev/errors/{error_code}",
                "title": error_code,
                "status": exc.status_code,
                "detail": message,
                "instance": str(request.url),
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled exceptions -- never leak internals.

        Args:
            request: The failed request.
            exc: The unhandled exception.

        Returns:
            Generic 500 error response.
        """
        logger.exception("unhandled_exception", path=str(request.url))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "https://enterprise-os.dev/errors/INTERNAL_ERROR",
                "title": "INTERNAL_ERROR",
                "status": 500,
                "detail": "An unexpected error occurred",
                "instance": str(request.url),
            },
        )

    # ── Health Check ─────────────────────────────────────────────────

    @app.get("/health", tags=["system"])
    async def health_check(request: Request) -> dict[str, Any]:
        """Liveness and readiness health check.

        Verifies database and Redis connectivity.

        Args:
            request: Incoming HTTP request.

        Returns:
            Health status with component details.
        """
        checks: dict[str, str] = {}

        # Database
        try:
            async with engine.begin() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            checks["database"] = "healthy"
        except Exception:
            checks["database"] = "unhealthy"

        # Redis
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is not None:
            try:
                await redis_client.ping()
                checks["redis"] = "healthy"
            except Exception:
                checks["redis"] = "unhealthy"
        else:
            checks["redis"] = "not_configured"

        overall = "healthy" if all(v == "healthy" for v in checks.values() if v != "not_configured") else "degraded"

        return {
            "status": overall,
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0",
            "checks": checks,
        }

    return app


# ── OpenTelemetry Setup ──────────────────────────────────────────────


def _setup_otel(app: FastAPI) -> None:
    """Initialize OpenTelemetry tracing and instrumentation.

    Args:
        app: The FastAPI application instance.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        resource = Resource.create(
            {
                "service.name": "enterprise-agent-os-api",
                "service.version": "0.1.0",
                "deployment.environment": settings.ENVIRONMENT,
            }
        )
        provider = TracerProvider(resource=resource)

        # Only add OTLP exporter if endpoint is configured and non-default in prod
        if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(
                    endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT
                )
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except ImportError:
                logger.info("otlp_exporter_not_available")

        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.info("otel_initialized")
    except ImportError:
        logger.info("otel_packages_not_installed")


# ── Application Instance ─────────────────────────────────────────────

app = create_app()
