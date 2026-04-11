"""IT Incident Triage workflow definition tests."""
import pytest

from app.workflows.it_triage import create_it_triage_workflow, get_seed_workflow_sql


def test_workflow_name_and_slug():
    wf = create_it_triage_workflow()
    assert wf["name"] == "IT Incident Triage"
    assert wf["slug"] == "it-triage"
    assert wf["status"] == "production"
    assert wf["version"] == 1


def test_workflow_has_required_steps():
    wf = create_it_triage_workflow()
    step_ids = [s["id"] for s in wf["definition"]["steps"]]
    required = [
        "receive_alert", "acknowledge_pd", "enrich_metrics",
        "enrich_pods", "enrich_logs", "diagnose", "branch_decision",
        "approval_gate", "execute_resolution", "verify_resolution",
        "close_incident", "notify_resolution", "create_jira",
        "notify_engineer", "kpi_update",
    ]
    for sid in required:
        assert sid in step_ids, f"Missing step: {sid}"


def test_workflow_step_count():
    wf = create_it_triage_workflow()
    assert len(wf["definition"]["steps"]) >= 15


def test_workflow_edge_count():
    wf = create_it_triage_workflow()
    assert len(wf["definition"]["edges"]) >= 17


def test_branch_has_both_paths():
    wf = create_it_triage_workflow()
    branch = next(
        s for s in wf["definition"]["steps"] if s["id"] == "branch_decision"
    )
    assert "auto_resolve" in branch["branches"]
    assert "escalate" in branch["branches"]
    assert branch["default_branch"] == "escalate"


def test_budget_config():
    wf = create_it_triage_workflow()
    b = wf["budget_config"]
    assert b["max_steps"] == 15
    assert b["max_cost_usd"] == 2.0
    assert b["max_tool_calls"] == 20
    assert b["max_wall_time"] == 300


def test_kpi_config():
    wf = create_it_triage_workflow()
    k = wf["kpi_config"]
    assert k["track_mttr"] is True
    assert k["sla_target_minutes"] == 15
    assert k["track_auto_resolve_rate"] is True


def test_tool_scope():
    wf = create_it_triage_workflow()
    scope = wf["tool_scope"]
    assert "pagerduty:*" in scope
    assert "slack:send_message" in scope
    assert "k8s:restart" in scope
    assert "jira:create_issue" in scope


def test_trigger_config():
    wf = create_it_triage_workflow()
    t = wf["trigger_config"]
    assert t["type"] == "webhook"
    assert t["source"] == "pagerduty"
    assert "incident.trigger" in t["events"]


def test_seed_sql_is_valid():
    sql = get_seed_workflow_sql()
    assert "INSERT INTO workflows" in sql
    assert "it-triage" in sql
    assert "ON CONFLICT (org_id, slug, version) DO NOTHING" in sql
    assert "019690a1-0000-7000-8000-000000000100" in sql


def test_edges_reference_valid_steps():
    wf = create_it_triage_workflow()
    step_ids = {s["id"] for s in wf["definition"]["steps"]}
    for edge in wf["definition"]["edges"]:
        assert edge["source"] in step_ids, f"Unknown source: {edge['source']}"
        assert edge["target"] in step_ids, f"Unknown target: {edge['target']}"


def test_approval_gate_config():
    wf = create_it_triage_workflow()
    gate = next(s for s in wf["definition"]["steps"] if s["id"] == "approval_gate")
    assert gate["type"] == "approval"
    assert gate["required_role"] == "sre"
    assert gate["sla_minutes"] == 10
