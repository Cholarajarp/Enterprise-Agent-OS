"""Webhook ingestion router.

Receives incoming webhooks from external services (PagerDuty, Jira, GitHub)
and generic webhook sources.  Each handler validates the request, extracts
relevant payload data, and triggers an agent run via the runs service.

Webhook endpoints use HMAC signature verification instead of JWT-based
``get_current_user`` auth.  A shared secret per source type is expected in
the ``X-Webhook-Signature`` header (or the provider-specific header).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.run import AgentRun, RunStatus, TriggerType
from app.models.workflow import Workflow, WorkflowStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Request / Response Schemas ──────────────────────────────────────


class WebhookRunResponse(BaseModel):
    """Minimal response after a webhook triggers an agent run."""

    run_id: uuid.UUID
    workflow_id: uuid.UUID
    source: str
    status: RunStatus
    message: str


class PagerDutyPayload(BaseModel):
    """Simplified PagerDuty webhook payload."""

    event: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class JiraPayload(BaseModel):
    """Simplified Jira webhook payload."""

    webhookEvent: str = Field(default="")
    issue: dict[str, Any] = Field(default_factory=dict)
    changelog: dict[str, Any] | None = None
    user: dict[str, Any] | None = None


class GitHubPayload(BaseModel):
    """Simplified GitHub webhook payload."""

    action: str = Field(default="")
    repository: dict[str, Any] = Field(default_factory=dict)
    sender: dict[str, Any] = Field(default_factory=dict)
    issue: dict[str, Any] | None = None
    pull_request: dict[str, Any] | None = None


class GenericWebhookPayload(BaseModel):
    """Generic webhook with explicit routing configuration."""

    workflow_slug: str = Field(
        ..., description="Slug of the workflow to trigger"
    )
    org_id: uuid.UUID = Field(
        ..., description="Organisation ID for scoping"
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary payload forwarded to the run"
    )


# ── Signature Verification ──────────────────────────────────────────


def _verify_hmac_signature(
    body: bytes,
    signature: str | None,
    secret: str,
    *,
    algorithm: str = "sha256",
) -> None:
    """Verify an HMAC signature against the raw request body.

    Args:
        body: Raw request body bytes.
        signature: Value from the webhook signature header.
        secret: Shared secret for HMAC computation.
        algorithm: Hash algorithm (default sha256).

    Raises:
        HTTPException: 401 if signature is missing or invalid.
    """
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "MISSING_SIGNATURE",
                "message": "Webhook signature header is required",
            },
        )

    # Strip common prefixes (e.g. "sha256=...")
    if "=" in signature:
        signature = signature.split("=", 1)[-1]

    hash_func = getattr(hashlib, algorithm, hashlib.sha256)
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hash_func,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "INVALID_SIGNATURE",
                "message": "Webhook signature verification failed",
            },
        )


async def _find_workflow_by_slug(
    db: AsyncSession,
    org_id: uuid.UUID,
    slug: str,
) -> Workflow:
    """Locate a production workflow by slug or raise 404."""
    result = await db.execute(
        select(Workflow).where(
            Workflow.org_id == org_id,
            Workflow.slug == slug,
            Workflow.status == WorkflowStatus.PRODUCTION,
        )
    )
    workflow = result.scalar_one_or_none()
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "WORKFLOW_NOT_FOUND",
                "message": f"No production workflow with slug '{slug}' found",
            },
        )
    return workflow


async def _create_webhook_run(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    workflow: Workflow,
    source: str,
    trigger_payload: dict[str, Any],
) -> AgentRun:
    """Insert a new queued agent run triggered by a webhook."""
    now = datetime.now(tz=timezone.utc)
    run = AgentRun(
        org_id=org_id,
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        trigger_type=TriggerType.WEBHOOK,
        trigger_payload={
            "source": source,
            **trigger_payload,
        },
        status=RunStatus.QUEUED,
        started_at=now,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    logger.info(
        "webhook_run_created",
        run_id=str(run.id),
        workflow_id=str(workflow.id),
        source=source,
        org_id=str(org_id),
    )

    return run


# ── Webhook Secret Helpers ──────────────────────────────────────────

_WEBHOOK_SECRET_ENV = "ENCRYPTION_KEY"  # Re-use as default webhook secret


def _get_webhook_secret() -> str:
    """Return the webhook signing secret from application settings."""
    return settings.ENCRYPTION_KEY


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/pagerduty", response_model=WebhookRunResponse, status_code=status.HTTP_201_CREATED)
async def receive_pagerduty_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
) -> WebhookRunResponse:
    """Receive a PagerDuty webhook and trigger an IT triage workflow.

    Expects an ``X-Webhook-Signature`` header for HMAC verification.
    The IT triage workflow is identified by the slug ``it-triage``.
    """
    body = await request.body()
    _verify_hmac_signature(body, x_webhook_signature, _get_webhook_secret())

    # Parse the payload after verification
    try:
        import json
        raw = json.loads(body)
        payload = PagerDutyPayload(**raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_PAYLOAD", "message": "Malformed PagerDuty payload"},
        ) from exc

    # PagerDuty webhooks require org_id in the payload or a default config
    org_id_str = payload.event.get("org_id") or raw.get("org_id")
    if not org_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "MISSING_ORG_ID",
                "message": "org_id must be provided in the webhook payload",
            },
        )

    try:
        org_id = uuid.UUID(str(org_id_str))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_ORG_ID", "message": "Invalid org_id format"},
        ) from exc

    workflow = await _find_workflow_by_slug(db, org_id, "it-triage")
    run = await _create_webhook_run(
        db,
        org_id=org_id,
        workflow=workflow,
        source="pagerduty",
        trigger_payload={"event": payload.event, "messages": payload.messages},
    )

    return WebhookRunResponse(
        run_id=run.id,
        workflow_id=workflow.id,
        source="pagerduty",
        status=run.status,
        message="PagerDuty webhook received; IT triage run queued",
    )


@router.post("/jira", response_model=WebhookRunResponse, status_code=status.HTTP_201_CREATED)
async def receive_jira_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
) -> WebhookRunResponse:
    """Receive a Jira webhook and trigger the configured Jira automation workflow.

    The workflow is identified by the slug ``jira-automation``.
    """
    body = await request.body()
    _verify_hmac_signature(body, x_webhook_signature, _get_webhook_secret())

    try:
        import json
        raw = json.loads(body)
        payload = JiraPayload(**raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_PAYLOAD", "message": "Malformed Jira payload"},
        ) from exc

    org_id_str = raw.get("org_id")
    if not org_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "MISSING_ORG_ID",
                "message": "org_id must be provided in the webhook payload",
            },
        )

    try:
        org_id = uuid.UUID(str(org_id_str))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_ORG_ID", "message": "Invalid org_id format"},
        ) from exc

    workflow = await _find_workflow_by_slug(db, org_id, "jira-automation")
    run = await _create_webhook_run(
        db,
        org_id=org_id,
        workflow=workflow,
        source="jira",
        trigger_payload={
            "webhook_event": payload.webhookEvent,
            "issue": payload.issue,
            "changelog": payload.changelog,
        },
    )

    return WebhookRunResponse(
        run_id=run.id,
        workflow_id=workflow.id,
        source="jira",
        status=run.status,
        message="Jira webhook received; automation run queued",
    )


@router.post("/github", response_model=WebhookRunResponse, status_code=status.HTTP_201_CREATED)
async def receive_github_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
) -> WebhookRunResponse:
    """Receive a GitHub webhook and trigger the configured GitHub ops workflow.

    Uses GitHub's ``X-Hub-Signature-256`` header for HMAC-SHA256 verification.
    The workflow is identified by the slug ``github-ops``.
    """
    body = await request.body()
    _verify_hmac_signature(body, x_hub_signature_256, _get_webhook_secret())

    try:
        import json
        raw = json.loads(body)
        payload = GitHubPayload(**raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_PAYLOAD", "message": "Malformed GitHub payload"},
        ) from exc

    org_id_str = raw.get("org_id")
    if not org_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "MISSING_ORG_ID",
                "message": "org_id must be provided in the webhook payload",
            },
        )

    try:
        org_id = uuid.UUID(str(org_id_str))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_ORG_ID", "message": "Invalid org_id format"},
        ) from exc

    workflow = await _find_workflow_by_slug(db, org_id, "github-ops")
    run = await _create_webhook_run(
        db,
        org_id=org_id,
        workflow=workflow,
        source="github",
        trigger_payload={
            "github_event": x_github_event or "unknown",
            "action": payload.action,
            "repository": payload.repository.get("full_name", ""),
            "sender": payload.sender.get("login", ""),
            "issue": payload.issue,
            "pull_request": payload.pull_request,
        },
    )

    return WebhookRunResponse(
        run_id=run.id,
        workflow_id=workflow.id,
        source="github",
        status=run.status,
        message="GitHub webhook received; ops run queued",
    )


@router.post("/generic", response_model=WebhookRunResponse, status_code=status.HTTP_201_CREATED)
async def receive_generic_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_webhook_signature: str | None = Header(None, alias="X-Webhook-Signature"),
) -> WebhookRunResponse:
    """Receive a generic webhook with explicit routing configuration.

    The request body must include ``workflow_slug`` and ``org_id`` to
    determine which workflow to trigger.
    """
    body = await request.body()
    _verify_hmac_signature(body, x_webhook_signature, _get_webhook_secret())

    try:
        import json
        raw = json.loads(body)
        payload = GenericWebhookPayload(**raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_PAYLOAD",
                "message": "Malformed generic webhook payload; requires workflow_slug and org_id",
            },
        ) from exc

    workflow = await _find_workflow_by_slug(db, payload.org_id, payload.workflow_slug)
    run = await _create_webhook_run(
        db,
        org_id=payload.org_id,
        workflow=workflow,
        source="generic",
        trigger_payload=payload.payload,
    )

    return WebhookRunResponse(
        run_id=run.id,
        workflow_id=workflow.id,
        source="generic",
        status=run.status,
        message=f"Generic webhook received; run queued for workflow '{payload.workflow_slug}'",
    )
