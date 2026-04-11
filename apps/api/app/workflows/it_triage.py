"""IT Incident Triage — seed workflow definition and factory.

This is the flagship workflow: PagerDuty Alert → Enrich → Diagnose →
Branch (auto-resolve vs route to engineer) → Execute → Verify → Close.

Target: MTTR from ~45 min to ~8 min.
"""

from __future__ import annotations

import uuid
from typing import Any


TRIAGE_WORKFLOW_ID = uuid.UUID("019690a1-0000-7000-8000-000000000100")
TRIAGE_ORG_ID = uuid.UUID("019690a1-0000-7000-8000-000000000001")


def create_it_triage_workflow() -> dict[str, Any]:
    """Return the full workflow definition for IT Incident Triage."""
    return {
        "id": str(TRIAGE_WORKFLOW_ID),
        "name": "IT Incident Triage",
        "slug": "it-triage",
        "version": 1,
        "status": "production",
        "description": (
            "Automated IT incident triage pipeline. Receives PagerDuty alerts, "
            "enriches with context from Datadog/K8s, diagnoses root cause via LLM, "
            "and either auto-resolves (with approval gate) or routes to an engineer "
            "with a pre-built briefing."
        ),
        "tool_scope": [
            "pagerduty:*",
            "datadog:query_metrics",
            "k8s:get_pods",
            "k8s:get_logs",
            "k8s:restart",
            "k8s:scale",
            "slack:send_message",
            "jira:create_issue",
            "jira:transition",
        ],
        "budget_config": {
            "max_steps": 15,
            "max_wall_time": 300,
            "max_tool_calls": 20,
            "max_cost_usd": 2.0,
        },
        "kpi_config": {
            "track_mttr": True,
            "track_auto_resolve_rate": True,
            "track_cost_per_incident": True,
            "sla_target_minutes": 15,
        },
        "trigger_config": {
            "type": "webhook",
            "source": "pagerduty",
            "events": ["incident.trigger", "incident.acknowledge"],
        },
        "definition": {
            "steps": [
                {
                    "id": "receive_alert",
                    "type": "transform",
                    "description": "Parse PagerDuty webhook payload",
                    "instruction": "Extract incident_id, title, severity, service, trigger_time from the PagerDuty webhook payload. Output as a flat JSON object.",
                    "input": "{{trigger_payload}}",
                },
                {
                    "id": "acknowledge_pd",
                    "type": "tool",
                    "description": "Acknowledge the PagerDuty incident",
                    "tool_name": "pagerduty:acknowledge",
                    "params": {
                        "incident_id": "{{receive_alert.output.incident_id}}",
                    },
                },
                {
                    "id": "enrich_metrics",
                    "type": "tool",
                    "description": "Pull recent metrics from Datadog for the affected service",
                    "tool_name": "datadog:query_metrics",
                    "params": {
                        "query": "avg:system.cpu.user{service:{{receive_alert.output.service}}}",
                        "from": "{{receive_alert.output.trigger_time_minus_15m}}",
                        "to": "{{receive_alert.output.trigger_time}}",
                    },
                },
                {
                    "id": "enrich_pods",
                    "type": "tool",
                    "description": "Get pod status from Kubernetes",
                    "tool_name": "k8s:get_pods",
                    "params": {
                        "namespace": "{{receive_alert.output.service}}",
                    },
                },
                {
                    "id": "enrich_logs",
                    "type": "tool",
                    "description": "Pull recent error logs from affected pods",
                    "tool_name": "k8s:get_logs",
                    "params": {
                        "namespace": "{{receive_alert.output.service}}",
                        "pod": "{{enrich_pods.result.0.name}}",
                        "tail_lines": 200,
                    },
                },
                {
                    "id": "diagnose",
                    "type": "llm",
                    "description": "Analyze all enrichment data and diagnose root cause",
                    "model_role": "planner",
                    "system_instruction": (
                        "You are a senior SRE diagnosing an IT incident. "
                        "Analyze the alert, metrics, pod status, and logs. "
                        "Determine the root cause and recommend an action. "
                        "Output a JSON object with: root_cause, confidence (0-1), "
                        "recommended_action (auto_resolve or escalate), "
                        "resolution_steps (array of strings), and briefing (summary for engineer)."
                    ),
                    "prompt": (
                        "Incident: {{receive_alert.output}}\n\n"
                        "Metrics: {{enrich_metrics.result}}\n\n"
                        "Pod Status: {{enrich_pods.result}}\n\n"
                        "Recent Logs: {{enrich_logs.result}}"
                    ),
                    "temperature": 0,
                    "max_tokens": 2048,
                },
                {
                    "id": "branch_decision",
                    "type": "branch",
                    "description": "Route based on diagnosis confidence and recommended action",
                    "condition": "If diagnosis confidence > 0.8 AND recommended_action is auto_resolve, go to auto_resolve. Otherwise, go to escalate.",
                    "branches": {
                        "auto_resolve": ["approval_gate"],
                        "escalate": ["create_jira", "notify_engineer"],
                    },
                    "default_branch": "escalate",
                },
                # ── Auto-resolve branch ──
                {
                    "id": "approval_gate",
                    "type": "approval",
                    "description": "Human approval required before auto-resolution",
                    "required_role": "sre",
                    "sla_minutes": 10,
                    "payload_description": "Automated resolution of incident",
                },
                {
                    "id": "execute_resolution",
                    "type": "tool",
                    "description": "Execute the resolution (restart deployment, scale up, etc.)",
                    "tool_name": "k8s:restart",
                    "params": {
                        "namespace": "{{receive_alert.output.service}}",
                        "deployment": "{{receive_alert.output.service}}",
                    },
                    "requires_approval": False,
                },
                {
                    "id": "verify_resolution",
                    "type": "tool",
                    "description": "Verify the service recovered after resolution",
                    "tool_name": "k8s:get_pods",
                    "params": {
                        "namespace": "{{receive_alert.output.service}}",
                    },
                },
                {
                    "id": "close_incident",
                    "type": "llm",
                    "description": "Generate incident summary and close PagerDuty incident",
                    "model_role": "worker",
                    "system_instruction": "Write a concise incident postmortem summary. Include: timeline, root cause, resolution, and prevention recommendations.",
                    "prompt": "Incident: {{receive_alert.output}}\nDiagnosis: {{diagnose}}\nResolution: {{execute_resolution}}\nVerification: {{verify_resolution}}",
                },
                {
                    "id": "notify_resolution",
                    "type": "tool",
                    "description": "Post resolution summary to Slack",
                    "tool_name": "slack:send_message",
                    "params": {
                        "channel": "#incidents",
                        "text": "Incident {{receive_alert.output.incident_id}} auto-resolved.\n\nRoot cause: {{diagnose.root_cause}}\nResolution: {{close_incident.content}}",
                    },
                },
                # ── Escalation branch ──
                {
                    "id": "create_jira",
                    "type": "tool",
                    "description": "Create a Jira ticket for the incident",
                    "tool_name": "jira:create_issue",
                    "params": {
                        "project_key": "OPS",
                        "summary": "[AUTO] {{receive_alert.output.title}}",
                        "description": "{{diagnose.briefing}}",
                        "issue_type": "Bug",
                        "priority": "{{receive_alert.output.severity}}",
                        "labels": ["auto-triage", "incident"],
                    },
                },
                {
                    "id": "notify_engineer",
                    "type": "tool",
                    "description": "Send briefing to on-call engineer via Slack",
                    "tool_name": "slack:send_message",
                    "params": {
                        "channel": "#oncall",
                        "text": "🚨 Incident escalated: {{receive_alert.output.title}}\n\nSeverity: {{receive_alert.output.severity}}\nRoot Cause: {{diagnose.root_cause}}\nConfidence: {{diagnose.confidence}}\nJira: {{create_jira.data.key}}\n\nRecommended steps:\n{{diagnose.resolution_steps}}",
                    },
                },
                # ── Final KPI update ──
                {
                    "id": "kpi_update",
                    "type": "notify",
                    "description": "Update KPI metrics for this incident",
                    "message": "Incident triage complete",
                    "channel": "kpi",
                },
            ],
            "edges": [
                {"source": "receive_alert", "target": "acknowledge_pd"},
                {"source": "acknowledge_pd", "target": "enrich_metrics"},
                {"source": "acknowledge_pd", "target": "enrich_pods"},
                {"source": "enrich_pods", "target": "enrich_logs"},
                {"source": "enrich_metrics", "target": "diagnose"},
                {"source": "enrich_logs", "target": "diagnose"},
                {"source": "diagnose", "target": "branch_decision"},
                # Auto-resolve path
                {"source": "branch_decision", "target": "approval_gate", "label": "auto_resolve"},
                {"source": "approval_gate", "target": "execute_resolution"},
                {"source": "execute_resolution", "target": "verify_resolution"},
                {"source": "verify_resolution", "target": "close_incident"},
                {"source": "close_incident", "target": "notify_resolution"},
                {"source": "notify_resolution", "target": "kpi_update"},
                # Escalate path
                {"source": "branch_decision", "target": "create_jira", "label": "escalate"},
                {"source": "branch_decision", "target": "notify_engineer", "label": "escalate"},
                {"source": "create_jira", "target": "kpi_update"},
                {"source": "notify_engineer", "target": "kpi_update"},
            ],
        },
    }


def get_seed_workflow_sql() -> str:
    """Return SQL to seed the IT triage workflow into the database."""
    import json
    wf = create_it_triage_workflow()
    definition_json = json.dumps(wf["definition"]).replace("'", "''")
    budget_json = json.dumps(wf["budget_config"]).replace("'", "''")
    kpi_json = json.dumps(wf["kpi_config"]).replace("'", "''")
    trigger_json = json.dumps(wf["trigger_config"]).replace("'", "''")
    tool_scope = "{" + ",".join(wf["tool_scope"]) + "}"

    return f"""
INSERT INTO workflows (id, org_id, name, slug, version, status, definition, trigger_config, tool_scope, budget_config, kpi_config)
VALUES (
    '{wf["id"]}',
    '{str(TRIAGE_ORG_ID)}',
    '{wf["name"]}',
    '{wf["slug"]}',
    {wf["version"]},
    'production',
    '{definition_json}',
    '{trigger_json}',
    '{tool_scope}',
    '{budget_json}',
    '{kpi_json}'
) ON CONFLICT (org_id, slug, version) DO NOTHING;
"""
