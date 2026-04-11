"""Helpers for constructing immutable audit events."""

from __future__ import annotations

import hashlib
import json
import uuid

from app.models.audit import ActorType, AuditEvent


def build_audit_event(
    *,
    org_id: uuid.UUID,
    event_type: str,
    actor_type: ActorType,
    actor_id: str,
    payload: dict,
    decision: str,
    run_id: uuid.UUID | None = None,
    agent_id: str | None = None,
    prev_hash: str | None = None,
    latency_ms: int = 0,
) -> AuditEvent:
    """Create an audit event with a deterministic payload hash."""

    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    return AuditEvent(
        org_id=org_id,
        run_id=run_id,
        agent_id=agent_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        payload_hash=payload_hash,
        payload=payload,
        decision=decision,
        prev_hash=prev_hash,
        latency_ms=latency_ms,
    )
