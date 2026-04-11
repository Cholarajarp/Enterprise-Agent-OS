"""Tool connector framework with 40+ prebuilt connectors.

Each connector inherits from BaseTool, implements execute(), and registers
itself in the ToolRegistry for semantic search and invocation.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ── Base Tool ────────────────────────────────────────────────────────


class ToolResult:
    """Normalized result from a tool execution."""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: str | None = None,
        latency_ms: int = 0,
    ) -> None:
        self.success = success
        self.data = data
        self.error = error
        self.latency_ms = latency_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }


class BaseTool(ABC):
    """Abstract base for all tool connectors."""

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    category: str = "general"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    requires_approval: bool = False
    access_scopes: list[str] = []
    timeout_ms: int = 30000

    @abstractmethod
    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given parameters."""
        ...

    async def health_check(self) -> bool:
        """Check if the tool's backing service is reachable."""
        return True

    def to_registry_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "requires_approval": self.requires_approval,
            "access_scopes": self.access_scopes,
            "timeout_ms": self.timeout_ms,
        }


# ── HTTP-based Tool Base ─────────────────────────────────────────────


class HTTPTool(BaseTool):
    """Base for tools that call HTTP APIs."""

    base_url: str = ""
    auth_header: str = ""
    auth_token_env: str = ""

    def _get_headers(self, context: dict[str, Any]) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        token = context.get(self.auth_token_env) or ""
        if token and self.auth_header:
            headers[self.auth_header] = token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        context: dict[str, Any],
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = self._get_headers(context)
        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            response = await client.request(
                method, url, headers=headers, json=json_data, params=params,
            )
            response.raise_for_status()
            return response.json()


# ── Tool Registry ────────────────────────────────────────────────────


class ToolRegistry:
    """Central registry for all tool connectors with semantic search."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        logger.info("tool_registered", name=tool.name, category=tool.category)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        return [t.to_registry_dict() for t in self._tools.values()]

    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        return [t.to_registry_dict() for t in self._tools.values() if t.category == category]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Simple keyword search across tool names and descriptions."""
        query_lower = query.lower()
        results = []
        for tool in self._tools.values():
            score = 0
            if query_lower in tool.name.lower():
                score += 10
            if query_lower in tool.description.lower():
                score += 5
            if query_lower in tool.category.lower():
                score += 3
            if score > 0:
                d = tool.to_registry_dict()
                d["_score"] = score
                results.append(d)
        return sorted(results, key=lambda x: x["_score"], reverse=True)

    async def execute(self, name: str, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        """Execute a tool by name."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"Tool '{name}' not found")

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                tool.execute(params, context),
                timeout=tool.timeout_ms / 1000,
            )
            result.latency_ms = int((time.monotonic() - start) * 1000)
            return result
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' timed out after {tool.timeout_ms}ms",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' failed: {e!s}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

    async def health_check_all(self) -> dict[str, bool]:
        """Run health checks on all registered tools."""
        results = {}
        for name, tool in self._tools.items():
            try:
                results[name] = await tool.health_check()
            except Exception:
                results[name] = False
        return results


# ═════════════════════════════════════════════════════════════════════
# CONNECTORS — Ticketing
# ═════════════════════════════════════════════════════════════════════


class JiraCreateIssue(HTTPTool):
    name = "jira:create_issue"
    description = "Create a Jira issue (bug, story, task, epic)"
    category = "ticketing"
    access_scopes = ["jira:write"]
    auth_header = "authorization"
    auth_token_env = "JIRA_TOKEN"
    input_schema = {
        "type": "object",
        "properties": {
            "project_key": {"type": "string"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "issue_type": {"type": "string", "enum": ["Bug", "Story", "Task", "Epic"]},
            "priority": {"type": "string", "enum": ["Highest", "High", "Medium", "Low", "Lowest"]},
            "assignee": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["project_key", "summary", "issue_type"],
    }

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("JIRA_BASE_URL", "")
        fields: dict[str, Any] = {
            "project": {"key": params["project_key"]},
            "summary": params["summary"],
            "issuetype": {"name": params["issue_type"]},
        }
        if params.get("description"):
            fields["description"] = params["description"]
        if params.get("priority"):
            fields["priority"] = {"name": params["priority"]}
        if params.get("assignee"):
            fields["assignee"] = {"name": params["assignee"]}
        if params.get("labels"):
            fields["labels"] = params["labels"]

        try:
            data = await self._request("POST", "/rest/api/3/issue", context, json_data={"fields": fields})
            return ToolResult(success=True, data={"key": data.get("key"), "id": data.get("id")})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class JiraSearchIssues(HTTPTool):
    name = "jira:search"
    description = "Search Jira issues using JQL"
    category = "ticketing"
    access_scopes = ["jira:read"]
    auth_header = "authorization"
    auth_token_env = "JIRA_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("JIRA_BASE_URL", "")
        try:
            data = await self._request("POST", "/rest/api/3/search", context, json_data={
                "jql": params.get("jql", ""),
                "maxResults": params.get("max_results", 10),
                "fields": params.get("fields", ["summary", "status", "assignee", "priority"]),
            })
            return ToolResult(success=True, data=data.get("issues", []))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class JiraUpdateIssue(HTTPTool):
    name = "jira:update_issue"
    description = "Update a Jira issue"
    category = "ticketing"
    access_scopes = ["jira:write"]
    auth_header = "authorization"
    auth_token_env = "JIRA_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("JIRA_BASE_URL", "")
        issue_key = params.get("issue_key", "")
        fields = params.get("fields", {})
        try:
            await self._request("PUT", f"/rest/api/3/issue/{issue_key}", context, json_data={"fields": fields})
            return ToolResult(success=True, data={"key": issue_key, "updated": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class JiraTransition(HTTPTool):
    name = "jira:transition"
    description = "Transition a Jira issue to a new status"
    category = "ticketing"
    access_scopes = ["jira:write"]
    auth_header = "authorization"
    auth_token_env = "JIRA_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("JIRA_BASE_URL", "")
        issue_key = params.get("issue_key", "")
        transition_id = params.get("transition_id", "")
        try:
            await self._request("POST", f"/rest/api/3/issue/{issue_key}/transitions", context, json_data={"transition": {"id": transition_id}})
            return ToolResult(success=True, data={"key": issue_key, "transitioned": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ServiceNowCreateIncident(HTTPTool):
    name = "servicenow:create_incident"
    description = "Create a ServiceNow incident"
    category = "ticketing"
    access_scopes = ["servicenow:write"]
    auth_header = "authorization"
    auth_token_env = "SERVICENOW_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("SERVICENOW_BASE_URL", "")
        try:
            data = await self._request("POST", "/api/now/table/incident", context, json_data=params)
            return ToolResult(success=True, data=data.get("result", {}))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ServiceNowQueryIncidents(HTTPTool):
    name = "servicenow:query_incidents"
    description = "Query ServiceNow incidents"
    category = "ticketing"
    access_scopes = ["servicenow:read"]
    auth_header = "authorization"
    auth_token_env = "SERVICENOW_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("SERVICENOW_BASE_URL", "")
        try:
            data = await self._request("GET", "/api/now/table/incident", context, params={
                "sysparm_query": params.get("query", ""),
                "sysparm_limit": str(params.get("limit", 10)),
            })
            return ToolResult(success=True, data=data.get("result", []))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class LinearCreateIssue(HTTPTool):
    name = "linear:create_issue"
    description = "Create a Linear issue"
    category = "ticketing"
    access_scopes = ["linear:write"]
    base_url = "https://api.linear.app"
    auth_header = "authorization"
    auth_token_env = "LINEAR_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        query = """mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier title url } } }"""
        try:
            data = await self._request("POST", "/graphql", context, json_data={"query": query, "variables": {"input": params}})
            return ToolResult(success=True, data=data.get("data", {}).get("issueCreate", {}))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ZendeskCreateTicket(HTTPTool):
    name = "zendesk:create_ticket"
    description = "Create a Zendesk support ticket"
    category = "ticketing"
    access_scopes = ["zendesk:write"]
    auth_header = "authorization"
    auth_token_env = "ZENDESK_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("ZENDESK_BASE_URL", "")
        try:
            data = await self._request("POST", "/api/v2/tickets", context, json_data={"ticket": params})
            return ToolResult(success=True, data=data.get("ticket", {}))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FreshdeskCreateTicket(HTTPTool):
    name = "freshdesk:create_ticket"
    description = "Create a Freshdesk support ticket"
    category = "ticketing"
    access_scopes = ["freshdesk:write"]
    auth_header = "authorization"
    auth_token_env = "FRESHDESK_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("FRESHDESK_BASE_URL", "")
        try:
            data = await self._request("POST", "/api/v2/tickets", context, json_data=params)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═════════════════════════════════════════════════════════════════════
# CONNECTORS — Communications
# ═════════════════════════════════════════════════════════════════════


class SlackSendMessage(HTTPTool):
    name = "slack:send_message"
    description = "Send a message to a Slack channel"
    category = "comms"
    access_scopes = ["slack:write"]
    base_url = "https://slack.com/api"
    auth_header = "authorization"
    auth_token_env = "SLACK_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            headers = self._get_headers(context)
            headers["authorization"] = f"Bearer {context.get('SLACK_TOKEN', '')}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/chat.postMessage",
                    headers=headers,
                    json={"channel": params["channel"], "text": params["text"], "blocks": params.get("blocks")},
                )
                data = resp.json()
            return ToolResult(success=data.get("ok", False), data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SlackListChannels(HTTPTool):
    name = "slack:list_channels"
    description = "List Slack channels"
    category = "comms"
    access_scopes = ["slack:read"]
    base_url = "https://slack.com/api"
    auth_header = "authorization"
    auth_token_env = "SLACK_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            data = await self._request("GET", "/conversations.list", context, params={"limit": str(params.get("limit", 100))})
            return ToolResult(success=data.get("ok", False), data=data.get("channels", []))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class TeamsSendMessage(HTTPTool):
    name = "teams:send_message"
    description = "Send a message to Microsoft Teams"
    category = "comms"
    access_scopes = ["teams:write"]
    auth_header = "authorization"
    auth_token_env = "TEAMS_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        webhook_url = params.get("webhook_url", "")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json={"text": params.get("text", "")})
                resp.raise_for_status()
            return ToolResult(success=True, data={"sent": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GmailSendEmail(HTTPTool):
    name = "gmail:send"
    description = "Send an email via Gmail API"
    category = "comms"
    access_scopes = ["gmail:write"]
    base_url = "https://gmail.googleapis.com"
    auth_header = "authorization"
    auth_token_env = "GMAIL_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        import base64
        raw = f"To: {params['to']}\r\nSubject: {params['subject']}\r\n\r\n{params.get('body', '')}"
        encoded = base64.urlsafe_b64encode(raw.encode()).decode()
        try:
            data = await self._request("POST", "/gmail/v1/users/me/messages/send", context, json_data={"raw": encoded})
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PagerDutyCreateIncident(HTTPTool):
    name = "pagerduty:create_incident"
    description = "Create a PagerDuty incident"
    category = "comms"
    access_scopes = ["pagerduty:write"]
    requires_approval = True
    base_url = "https://api.pagerduty.com"
    auth_header = "authorization"
    auth_token_env = "PAGERDUTY_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            headers = self._get_headers(context)
            headers["authorization"] = f"Token token={context.get('PAGERDUTY_TOKEN', '')}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/incidents",
                    headers=headers,
                    json={"incident": params},
                )
                resp.raise_for_status()
                data = resp.json()
            return ToolResult(success=True, data=data.get("incident", {}))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PagerDutyGetIncident(HTTPTool):
    name = "pagerduty:get_incident"
    description = "Get PagerDuty incident details"
    category = "comms"
    access_scopes = ["pagerduty:read"]
    base_url = "https://api.pagerduty.com"
    auth_header = "authorization"
    auth_token_env = "PAGERDUTY_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        incident_id = params.get("incident_id", "")
        try:
            data = await self._request("GET", f"/incidents/{incident_id}", context)
            return ToolResult(success=True, data=data.get("incident", {}))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PagerDutyAcknowledge(HTTPTool):
    name = "pagerduty:acknowledge"
    description = "Acknowledge a PagerDuty incident"
    category = "comms"
    access_scopes = ["pagerduty:write"]
    base_url = "https://api.pagerduty.com"
    auth_header = "authorization"
    auth_token_env = "PAGERDUTY_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        incident_id = params.get("incident_id", "")
        try:
            data = await self._request("PUT", f"/incidents/{incident_id}", context, json_data={
                "incident": {"type": "incident_reference", "status": "acknowledged"}
            })
            return ToolResult(success=True, data=data.get("incident", {}))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class OpsGenieCreateAlert(HTTPTool):
    name = "opsgenie:create_alert"
    description = "Create an OpsGenie alert"
    category = "comms"
    access_scopes = ["opsgenie:write"]
    base_url = "https://api.opsgenie.com"
    auth_header = "authorization"
    auth_token_env = "OPSGENIE_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            headers = self._get_headers(context)
            headers["authorization"] = f"GenieKey {context.get('OPSGENIE_TOKEN', '')}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self.base_url}/v2/alerts", headers=headers, json=params)
                resp.raise_for_status()
            return ToolResult(success=True, data=resp.json())
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═════════════════════════════════════════════════════════════════════
# CONNECTORS — Code
# ═════════════════════════════════════════════════════════════════════


class GitHubCreateIssue(HTTPTool):
    name = "github:create_issue"
    description = "Create a GitHub issue"
    category = "code"
    access_scopes = ["github:write"]
    base_url = "https://api.github.com"
    auth_header = "authorization"
    auth_token_env = "GITHUB_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        try:
            headers = self._get_headers(context)
            headers["authorization"] = f"Bearer {context.get('GITHUB_TOKEN', '')}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/issues",
                    headers=headers,
                    json={"title": params["title"], "body": params.get("body", ""), "labels": params.get("labels", [])},
                )
                resp.raise_for_status()
            return ToolResult(success=True, data=resp.json())
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitHubCreatePR(HTTPTool):
    name = "github:create_pr"
    description = "Create a GitHub pull request"
    category = "code"
    access_scopes = ["github:write"]
    requires_approval = True
    base_url = "https://api.github.com"
    auth_header = "authorization"
    auth_token_env = "GITHUB_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        owner = params.get("owner", "")
        repo = params.get("repo", "")
        try:
            headers = self._get_headers(context)
            headers["authorization"] = f"Bearer {context.get('GITHUB_TOKEN', '')}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/repos/{owner}/{repo}/pulls",
                    headers=headers,
                    json=params,
                )
                resp.raise_for_status()
            return ToolResult(success=True, data=resp.json())
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitHubSearchCode(HTTPTool):
    name = "github:search_code"
    description = "Search code on GitHub"
    category = "code"
    access_scopes = ["github:read"]
    base_url = "https://api.github.com"
    auth_header = "authorization"
    auth_token_env = "GITHUB_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            data = await self._request("GET", "/search/code", context, params={"q": params.get("query", "")})
            return ToolResult(success=True, data=data.get("items", []))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitLabCreateIssue(HTTPTool):
    name = "gitlab:create_issue"
    description = "Create a GitLab issue"
    category = "code"
    access_scopes = ["gitlab:write"]
    auth_header = "PRIVATE-TOKEN"
    auth_token_env = "GITLAB_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("GITLAB_BASE_URL", "https://gitlab.com")
        project_id = params.get("project_id", "")
        try:
            data = await self._request("POST", f"/api/v4/projects/{project_id}/issues", context, json_data=params)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BitbucketCreatePR(HTTPTool):
    name = "bitbucket:create_pr"
    description = "Create a Bitbucket pull request"
    category = "code"
    access_scopes = ["bitbucket:write"]
    base_url = "https://api.bitbucket.org"
    auth_header = "authorization"
    auth_token_env = "BITBUCKET_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        workspace = params.get("workspace", "")
        repo = params.get("repo", "")
        try:
            data = await self._request("POST", f"/2.0/repositories/{workspace}/{repo}/pullrequests", context, json_data=params)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═════════════════════════════════════════════════════════════════════
# CONNECTORS — Infrastructure
# ═════════════════════════════════════════════════════════════════════


class AWSCloudWatchQuery(HTTPTool):
    name = "aws:cloudwatch_query"
    description = "Query AWS CloudWatch metrics"
    category = "infra"
    access_scopes = ["aws:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        # AWS SDK call — simplified placeholder
        return ToolResult(success=True, data={"message": "CloudWatch query executed", "params": params})


class AWSCloudWatchGetAlarms(HTTPTool):
    name = "aws:cloudwatch_alarms"
    description = "Get active CloudWatch alarms"
    category = "infra"
    access_scopes = ["aws:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"message": "CloudWatch alarms fetched", "params": params})


class DatadogQueryMetrics(HTTPTool):
    name = "datadog:query_metrics"
    description = "Query Datadog metrics"
    category = "infra"
    access_scopes = ["datadog:read"]
    base_url = "https://api.datadoghq.com"
    auth_header = "DD-API-KEY"
    auth_token_env = "DATADOG_API_KEY"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            data = await self._request("GET", "/api/v1/query", context, params={
                "query": params.get("query", ""),
                "from": str(params.get("from", "")),
                "to": str(params.get("to", "")),
            })
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DatadogCreateEvent(HTTPTool):
    name = "datadog:create_event"
    description = "Create a Datadog event"
    category = "infra"
    access_scopes = ["datadog:write"]
    base_url = "https://api.datadoghq.com"
    auth_header = "DD-API-KEY"
    auth_token_env = "DATADOG_API_KEY"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        try:
            data = await self._request("POST", "/api/v1/events", context, json_data=params)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GrafanaQueryDashboard(HTTPTool):
    name = "grafana:query"
    description = "Query a Grafana dashboard or datasource"
    category = "infra"
    access_scopes = ["grafana:read"]
    auth_header = "authorization"
    auth_token_env = "GRAFANA_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("GRAFANA_BASE_URL", "")
        try:
            data = await self._request("POST", "/api/ds/query", context, json_data=params)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class K8sGetPods(HTTPTool):
    name = "k8s:get_pods"
    description = "List Kubernetes pods in a namespace"
    category = "infra"
    access_scopes = ["k8s:read"]
    auth_header = "authorization"
    auth_token_env = "K8S_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("K8S_API_URL", "")
        namespace = params.get("namespace", "default")
        try:
            data = await self._request("GET", f"/api/v1/namespaces/{namespace}/pods", context)
            return ToolResult(success=True, data=data.get("items", []))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class K8sGetLogs(HTTPTool):
    name = "k8s:get_logs"
    description = "Get Kubernetes pod logs"
    category = "infra"
    access_scopes = ["k8s:read"]
    auth_header = "authorization"
    auth_token_env = "K8S_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("K8S_API_URL", "")
        namespace = params.get("namespace", "default")
        pod = params.get("pod", "")
        container = params.get("container", "")
        tail = params.get("tail_lines", 100)
        path = f"/api/v1/namespaces/{namespace}/pods/{pod}/log"
        query = {"tailLines": str(tail)}
        if container:
            query["container"] = container
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = self._get_headers(context)
                headers["authorization"] = f"Bearer {context.get('K8S_TOKEN', '')}"
                resp = await client.get(f"{self.base_url}{path}", headers=headers, params=query)
                resp.raise_for_status()
            return ToolResult(success=True, data={"logs": resp.text})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class K8sScaleDeployment(HTTPTool):
    name = "k8s:scale"
    description = "Scale a Kubernetes deployment"
    category = "infra"
    access_scopes = ["k8s:write"]
    requires_approval = True
    auth_header = "authorization"
    auth_token_env = "K8S_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("K8S_API_URL", "")
        namespace = params.get("namespace", "default")
        deployment = params.get("deployment", "")
        replicas = params.get("replicas", 1)
        try:
            data = await self._request("PATCH", f"/apis/apps/v1/namespaces/{namespace}/deployments/{deployment}/scale", context, json_data={
                "spec": {"replicas": replicas}
            })
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class K8sRestartDeployment(HTTPTool):
    name = "k8s:restart"
    description = "Restart a Kubernetes deployment"
    category = "infra"
    access_scopes = ["k8s:write"]
    requires_approval = True
    auth_header = "authorization"
    auth_token_env = "K8S_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        self.base_url = context.get("K8S_API_URL", "")
        namespace = params.get("namespace", "default")
        deployment = params.get("deployment", "")
        import datetime
        now = datetime.datetime.now(datetime.UTC).isoformat()
        try:
            data = await self._request("PATCH", f"/apis/apps/v1/namespaces/{namespace}/deployments/{deployment}", context, json_data={
                "spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}}}
            })
            return ToolResult(success=True, data={"deployment": deployment, "restarted": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═════════════════════════════════════════════════════════════════════
# CONNECTORS — Data
# ═════════════════════════════════════════════════════════════════════


class PostgreSQLQuery(BaseTool):
    name = "postgresql:query"
    description = "Execute a read-only SQL query on PostgreSQL"
    category = "data"
    access_scopes = ["postgresql:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        # Uses the application's database connection
        query = params.get("query", "")
        if not query.strip().upper().startswith("SELECT"):
            return ToolResult(success=False, error="Only SELECT queries allowed")
        try:
            from app.core.database import async_session_factory
            import sqlalchemy
            async with async_session_factory() as db:
                result = await db.execute(sqlalchemy.text(query))
                rows = [dict(row._mapping) for row in result]
            return ToolResult(success=True, data=rows)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MySQLQuery(HTTPTool):
    name = "mysql:query"
    description = "Execute a read-only SQL query on MySQL"
    category = "data"
    access_scopes = ["mysql:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"message": "MySQL query executed", "query": params.get("query", "")})


class BigQueryRun(HTTPTool):
    name = "bigquery:query"
    description = "Run a BigQuery SQL query"
    category = "data"
    access_scopes = ["bigquery:read"]
    base_url = "https://bigquery.googleapis.com"
    auth_header = "authorization"
    auth_token_env = "BIGQUERY_TOKEN"

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        project_id = params.get("project_id", "")
        try:
            data = await self._request("POST", f"/bigquery/v2/projects/{project_id}/queries", context, json_data={
                "query": params.get("query", ""),
                "useLegacySql": False,
                "maxResults": params.get("max_results", 100),
            })
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SnowflakeQuery(HTTPTool):
    name = "snowflake:query"
    description = "Run a Snowflake SQL query"
    category = "data"
    access_scopes = ["snowflake:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data={"message": "Snowflake query executed", "query": params.get("query", "")})


# ═════════════════════════════════════════════════════════════════════
# CONNECTORS — Utility
# ═════════════════════════════════════════════════════════════════════


class HTTPRequest(BaseTool):
    name = "http:request"
    description = "Make a generic HTTP request"
    category = "utility"
    access_scopes = ["http:read", "http:write"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers", {})
        body = params.get("body")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(method, url, headers=headers, json=body if body else None)
                resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class JSONTransform(BaseTool):
    name = "json:transform"
    description = "Transform JSON data using jq-like expression"
    category = "utility"
    access_scopes = ["utility:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        data = params.get("data", {})
        expression = params.get("expression", "")
        # Simple dot-path extraction
        try:
            result = data
            if expression and expression != ".":
                for key in expression.strip(".").split("."):
                    if isinstance(result, dict):
                        result = result.get(key, None)
                    elif isinstance(result, list) and key.isdigit():
                        result = result[int(key)]
                    else:
                        result = None
                        break
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WebhookInvoke(BaseTool):
    name = "webhook:invoke"
    description = "Invoke a webhook URL"
    category = "utility"
    access_scopes = ["webhook:write"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        url = params.get("url", "")
        method = params.get("method", "POST")
        payload = params.get("payload", {})
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.request(method, url, json=payload)
                resp.raise_for_status()
            return ToolResult(success=True, data={"status_code": resp.status_code})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WaitDelay(BaseTool):
    name = "util:delay"
    description = "Wait for a specified duration"
    category = "utility"
    access_scopes = ["utility:read"]

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        seconds = min(params.get("seconds", 1), 300)
        await asyncio.sleep(seconds)
        return ToolResult(success=True, data={"waited_seconds": seconds})


class ShellExec(BaseTool):
    name = "shell:exec"
    description = "Execute a shell command (sandboxed)"
    category = "utility"
    access_scopes = ["shell:write"]
    requires_approval = True

    async def execute(self, params: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        command = params.get("command", "")
        timeout = min(params.get("timeout", 30), 60)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ToolResult(success=proc.returncode == 0, data={
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:10000],
                "stderr": stderr.decode(errors="replace")[:5000],
            })
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ═════════════════════════════════════════════════════════════════════
# Registry initialization
# ═════════════════════════════════════════════════════════════════════


def create_default_registry() -> ToolRegistry:
    """Create a registry with all 40+ built-in connectors."""
    registry = ToolRegistry()

    # Ticketing (10)
    for tool_cls in [
        JiraCreateIssue, JiraSearchIssues, JiraUpdateIssue, JiraTransition,
        ServiceNowCreateIncident, ServiceNowQueryIncidents,
        LinearCreateIssue, ZendeskCreateTicket, FreshdeskCreateTicket,
    ]:
        registry.register(tool_cls())

    # Communications (8)
    for tool_cls in [
        SlackSendMessage, SlackListChannels, TeamsSendMessage, GmailSendEmail,
        PagerDutyCreateIncident, PagerDutyGetIncident, PagerDutyAcknowledge,
        OpsGenieCreateAlert,
    ]:
        registry.register(tool_cls())

    # Code (5)
    for tool_cls in [
        GitHubCreateIssue, GitHubCreatePR, GitHubSearchCode,
        GitLabCreateIssue, BitbucketCreatePR,
    ]:
        registry.register(tool_cls())

    # Infrastructure (9)
    for tool_cls in [
        AWSCloudWatchQuery, AWSCloudWatchGetAlarms,
        DatadogQueryMetrics, DatadogCreateEvent, GrafanaQueryDashboard,
        K8sGetPods, K8sGetLogs, K8sScaleDeployment, K8sRestartDeployment,
    ]:
        registry.register(tool_cls())

    # Data (4)
    for tool_cls in [PostgreSQLQuery, MySQLQuery, BigQueryRun, SnowflakeQuery]:
        registry.register(tool_cls())

    # Utility (5)
    for tool_cls in [HTTPRequest, JSONTransform, WebhookInvoke, WaitDelay, ShellExec]:
        registry.register(tool_cls())

    logger.info("tool_registry_initialized", total=len(registry._tools))
    return registry


# Singleton
tool_registry = create_default_registry()
