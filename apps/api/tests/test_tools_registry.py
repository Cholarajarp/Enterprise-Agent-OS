"""Tool registry tests."""
import pytest

from app.services.tools import create_default_registry


def test_registry_has_tools():
    registry = create_default_registry()
    tools = registry.list_all()
    assert len(tools) >= 30


def test_registry_has_ticketing_tools():
    registry = create_default_registry()
    tools = registry.list_all()
    names = {t["name"] for t in tools}
    assert any("jira" in n or "servicenow" in n or "linear" in n for n in names)


def test_registry_has_comms_tools():
    registry = create_default_registry()
    tools = registry.list_all()
    names = {t["name"] for t in tools}
    assert any("slack" in n or "teams" in n for n in names)


def test_registry_has_infra_tools():
    registry = create_default_registry()
    tools = registry.list_all()
    names = {t["name"] for t in tools}
    assert any("k8s" in n or "aws" in n or "gcp" in n for n in names)


def test_registry_search_returns_results():
    registry = create_default_registry()
    results = registry.search("slack")
    assert len(results) > 0


def test_registry_search_no_results_for_garbage():
    registry = create_default_registry()
    results = registry.search("xyzzy_nonexistent_tool_12345")
    assert len(results) == 0


def test_registry_get_returns_none_for_unknown():
    registry = create_default_registry()
    tool = registry.get("nonexistent:tool")
    assert tool is None


def test_registry_get_known_tool():
    registry = create_default_registry()
    tools = registry.list_all()
    if tools:
        first_name = tools[0]["name"]
        tool = registry.get(first_name)
        assert tool is not None


def test_registry_tools_have_required_fields():
    registry = create_default_registry()
    tools = registry.list_all()
    for tool in tools:
        assert "name" in tool, f"Tool missing 'name': {tool}"
        assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
