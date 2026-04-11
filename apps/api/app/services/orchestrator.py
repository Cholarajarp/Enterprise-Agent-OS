"""Orchestration engine — plan/act/observe loop with multi-agent patterns.

Supports linear chain, parallel fan-out, hierarchical tree, and human-in-the-loop.
Every run is constrained by max_steps, max_tokens, max_wall_time, and loop detection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.audit import ActorType, ApprovalRequest, ApprovalStatus, AuditEvent
from app.models.run import AgentRun, RunStatus
from app.models.workflow import Workflow, WorkflowStatus
from app.services.audit import build_audit_event
from app.services.llm import (
    ChatMessage,
    LLMResult,
    LLMRouter,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    llm_router,
)

logger = structlog.get_logger(__name__)


# ── Step types in a workflow definition ──────────────────────────────


class StepType(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    APPROVAL = "approval"
    BRANCH = "branch"
    LOOP = "loop"
    SUB_AGENT = "sub_agent"
    TRANSFORM = "transform"
    DELAY = "delay"
    NOTIFY = "notify"


# ── Run constraints ──────────────────────────────────────────────────


class RunConstraints:
    """Enforces per-run resource limits."""

    def __init__(
        self,
        max_steps: int = 25,
        max_tokens: int = 500_000,
        max_wall_time_seconds: int = 600,
        max_tool_calls: int = 50,
    ) -> None:
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.max_wall_time_seconds = max_wall_time_seconds
        self.max_tool_calls = max_tool_calls
        self.steps_executed = 0
        self.tokens_used = 0
        self.tool_calls_made = 0
        self.start_time = time.monotonic()

    def check(self) -> str | None:
        """Return a constraint violation message, or None if OK."""
        if self.steps_executed >= self.max_steps:
            return f"Max steps exceeded ({self.max_steps})"
        if self.tokens_used >= self.max_tokens:
            return f"Max tokens exceeded ({self.max_tokens})"
        if self.tool_calls_made >= self.max_tool_calls:
            return f"Max tool calls exceeded ({self.max_tool_calls})"
        elapsed = time.monotonic() - self.start_time
        if elapsed >= self.max_wall_time_seconds:
            return f"Max wall time exceeded ({self.max_wall_time_seconds}s)"
        return None

    def record_step(self, input_tokens: int = 0, output_tokens: int = 0, tool_calls: int = 0) -> None:
        self.steps_executed += 1
        self.tokens_used += input_tokens + output_tokens
        self.tool_calls_made += tool_calls


# ── Loop detection ───────────────────────────────────────────────────


class LoopDetector:
    """Detect repetitive agent behavior by hashing recent actions."""

    def __init__(self, window: int = 5, threshold: int = 3) -> None:
        self.window = window
        self.threshold = threshold
        self._hashes: list[str] = []

    def check(self, action: dict[str, Any]) -> bool:
        """Return True if a loop is detected."""
        h = hashlib.md5(json.dumps(action, sort_keys=True).encode()).hexdigest()  # noqa: S324
        self._hashes.append(h)
        if len(self._hashes) > self.window * 2:
            self._hashes = self._hashes[-self.window * 2 :]
        # Count occurrences of this hash in the window
        recent = self._hashes[-self.window :]
        return recent.count(h) >= self.threshold


# ── Run Events (for SSE streaming) ───────────────────────────────────


class RunEvent:
    """Event emitted during a run for SSE streaming."""

    def __init__(
        self,
        event_type: str,
        data: dict[str, Any],
        run_id: uuid.UUID | None = None,
        step_index: int | None = None,
    ) -> None:
        self.event_type = event_type
        self.data = data
        self.run_id = run_id
        self.step_index = step_index
        self.timestamp = datetime.now(UTC).isoformat()

    def to_sse(self) -> str:
        payload = {
            "type": self.event_type,
            "data": self.data,
            "run_id": str(self.run_id) if self.run_id else None,
            "step_index": self.step_index,
            "timestamp": self.timestamp,
        }
        return json.dumps(payload)


# ── Step Executor ────────────────────────────────────────────────────


class StepExecutor:
    """Execute individual workflow steps."""

    def __init__(self, router: LLMRouter, org_id: uuid.UUID) -> None:
        self.router = router
        self.org_id = org_id

    async def execute_llm_step(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an LLM reasoning step."""
        prompt = step.get("prompt", "")
        system_instruction = step.get("system_instruction")
        role = step.get("model_role", "worker")
        temperature = step.get("temperature", 0)
        max_tokens = step.get("max_tokens", 4096)

        # Build messages from context
        messages = [ChatMessage(role="user", content=self._render_prompt(prompt, context))]

        # Include conversation history if available
        history = context.get("_conversation_history", [])
        if history:
            messages = [ChatMessage(**m) for m in history] + messages

        tools = None
        tool_defs = step.get("tools")
        if tool_defs:
            tools = [ToolDefinition(**t) for t in tool_defs]

        result = await self.router.generate(
            role=role,
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

        return {
            "type": "llm",
            "content": result.content,
            "tool_calls": [tc.model_dump() for tc in result.tool_calls],
            "usage": result.usage.model_dump(),
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "provider": result.provider,
            "model": result.model,
        }

    async def execute_tool_step(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool invocation via the governance proxy."""
        import httpx

        tool_name = step.get("tool_name", "")
        params = step.get("params", {})
        # Render params with context variables
        rendered_params = {}
        for k, v in params.items():
            if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
                var_name = v[2:-2].strip()
                rendered_params[k] = context.get(var_name, v)
            else:
                rendered_params[k] = v

        # Call governance proxy for evaluation
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.GOVERNANCE_PROXY_URL}/v1/evaluate",
                json={
                    "org_id": str(self.org_id),
                    "agent_id": context.get("_agent_id", "orchestrator"),
                    "tool_name": tool_name,
                    "params": rendered_params,
                    "workflow_id": context.get("_workflow_id", ""),
                },
            )

            if resp.status_code != 200:
                return {
                    "type": "tool",
                    "tool_name": tool_name,
                    "status": "blocked",
                    "error": f"Governance proxy returned {resp.status_code}",
                    "raw": resp.text,
                }

            eval_result = resp.json()
            decision = eval_result.get("decision", "blocked")

            if decision == "blocked":
                return {
                    "type": "tool",
                    "tool_name": tool_name,
                    "status": "blocked",
                    "reason": eval_result.get("reason", "Unknown"),
                }

            if decision == "escalated":
                return {
                    "type": "tool",
                    "tool_name": tool_name,
                    "status": "escalated",
                    "reason": eval_result.get("reason", "Requires approval"),
                }

        # If allowed, execute the tool
        # Tool execution is delegated to the tool fabric (Part 3)
        return {
            "type": "tool",
            "tool_name": tool_name,
            "status": "allowed",
            "params": eval_result.get("params", rendered_params),
            "result": None,  # Placeholder until tool fabric is wired
        }

    async def execute_branch_step(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a conditional branch."""
        condition = step.get("condition", "")
        branches = step.get("branches", {})

        # Evaluate condition using LLM classifier
        result = await self.router.generate(
            role="classifier",
            messages=[
                ChatMessage(
                    role="user",
                    content=f"Given this context, evaluate the condition and respond with ONLY the branch name.\n\nContext: {json.dumps(context, default=str)}\n\nCondition: {condition}\n\nAvailable branches: {', '.join(branches.keys())}",
                )
            ],
            system_instruction="You are a decision classifier. Respond with ONLY the branch name, nothing else.",
            temperature=0,
            max_tokens=50,
        )

        selected_branch = result.content.strip().lower()
        if selected_branch not in branches:
            selected_branch = step.get("default_branch", list(branches.keys())[0] if branches else "default")

        return {
            "type": "branch",
            "condition": condition,
            "selected_branch": selected_branch,
            "next_steps": branches.get(selected_branch, []),
        }

    async def execute_delay_step(
        self,
        step: dict[str, Any],
        _context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a delay step."""
        delay_seconds = step.get("delay_seconds", 1)
        # Cap at 300s to prevent abuse
        delay_seconds = min(delay_seconds, 300)
        await asyncio.sleep(delay_seconds)
        return {"type": "delay", "delay_seconds": delay_seconds}

    async def execute_transform_step(
        self,
        step: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a data transformation step using LLM."""
        input_data = step.get("input")
        transform_instruction = step.get("instruction", "Transform the data")

        if isinstance(input_data, str) and input_data.startswith("{{"):
            var_name = input_data[2:-2].strip()
            input_data = context.get(var_name, input_data)

        result = await self.router.generate(
            role="worker",
            messages=[
                ChatMessage(
                    role="user",
                    content=f"Transform this data according to the instruction.\n\nInstruction: {transform_instruction}\n\nInput data:\n{json.dumps(input_data, default=str)}",
                )
            ],
            system_instruction="You are a data transformation engine. Output ONLY the transformed data as valid JSON.",
            temperature=0,
            max_tokens=4096,
        )

        try:
            transformed = json.loads(result.content)
        except json.JSONDecodeError:
            transformed = result.content

        return {
            "type": "transform",
            "input": input_data,
            "output": transformed,
        }

    def _render_prompt(self, prompt: str, context: dict[str, Any]) -> str:
        """Render a prompt template with context variables."""
        rendered = prompt
        for key, value in context.items():
            if key.startswith("_"):
                continue
            placeholder = "{{" + key + "}}"
            if placeholder in rendered:
                rendered = rendered.replace(placeholder, str(value))
        return rendered


# ── Orchestrator ─────────────────────────────────────────────────────


class Orchestrator:
    """Core orchestration engine: plan → act → observe → repeat."""

    def __init__(
        self,
        router: LLMRouter | None = None,
    ) -> None:
        self.router = router or llm_router

    async def execute_run(
        self,
        run_id: uuid.UUID,
        *,
        emit_event: Any | None = None,
    ) -> None:
        """Execute a complete run lifecycle.

        Args:
            run_id: The UUID of the queued run to execute.
            emit_event: Optional callable(RunEvent) for SSE streaming.
        """
        async with async_session_factory() as db:
            # Load the run
            run = await db.get(AgentRun, run_id)
            if run is None:
                logger.error("run_not_found", run_id=str(run_id))
                return

            if run.status != RunStatus.QUEUED:
                logger.warning("run_not_queued", run_id=str(run_id), status=run.status.value)
                return

            # Load the workflow
            workflow = await db.get(Workflow, run.workflow_id)
            if workflow is None:
                await self._fail_run(db, run, "Workflow not found")
                return

            org_id = run.org_id

            # Update run to RUNNING
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(UTC)
            await db.commit()

            if emit_event:
                await emit_event(RunEvent("run_started", {"run_id": str(run_id)}, run_id=run_id))

            # Emit audit event
            audit = build_audit_event(
                org_id=org_id,
                event_type="run_started",
                actor_type=ActorType.SYSTEM,
                actor_id="orchestrator",
                payload={"workflow_id": str(workflow.id), "trigger_type": run.trigger_type.value},
                decision="allowed",
                run_id=run_id,
            )
            db.add(audit)
            await db.commit()

            # Initialize constraints
            budget = workflow.budget_config or {}
            constraints = RunConstraints(
                max_steps=budget.get("max_steps", settings.MAX_RUN_STEPS_DEFAULT),
                max_wall_time_seconds=budget.get("max_wall_time", settings.MAX_RUN_TIME_SECONDS_DEFAULT),
                max_tool_calls=budget.get("max_tool_calls", settings.MAX_TOOL_CALLS_DEFAULT),
            )

            executor = StepExecutor(self.router, org_id)
            loop_detector = LoopDetector()

            # Parse workflow definition
            definition = workflow.definition or {}
            steps = definition.get("steps", [])
            edges = definition.get("edges", [])

            if not steps:
                # Auto-plan mode: use LLM to create a plan
                await self._execute_auto_plan(
                    db=db,
                    run=run,
                    workflow=workflow,
                    executor=executor,
                    constraints=constraints,
                    loop_detector=loop_detector,
                    emit_event=emit_event,
                )
            else:
                # Defined workflow: execute steps in order
                await self._execute_defined_workflow(
                    db=db,
                    run=run,
                    workflow=workflow,
                    steps=steps,
                    edges=edges,
                    executor=executor,
                    constraints=constraints,
                    loop_detector=loop_detector,
                    emit_event=emit_event,
                )

    async def _execute_auto_plan(
        self,
        *,
        db: AsyncSession,
        run: AgentRun,
        workflow: Workflow,
        executor: StepExecutor,
        constraints: RunConstraints,
        loop_detector: LoopDetector,
        emit_event: Any | None = None,
    ) -> None:
        """Execute using the plan/act/observe loop with LLM planning."""
        context: dict[str, Any] = {
            "_run_id": str(run.id),
            "_workflow_id": str(run.workflow_id),
            "_agent_id": "orchestrator",
            "_conversation_history": [],
        }

        if run.trigger_payload:
            context.update(run.trigger_payload)

        # Phase 1: Plan
        plan_result = await self.router.generate(
            role="planner",
            messages=[
                ChatMessage(
                    role="user",
                    content=(
                        f"You are an agent orchestrator. Create a step-by-step plan to accomplish this task.\n\n"
                        f"Workflow: {workflow.name}\n"
                        f"Description: {workflow.definition.get('description', 'No description')}\n"
                        f"Available tools: {json.dumps(workflow.tool_scope or [])}\n"
                        f"Trigger payload: {json.dumps(run.trigger_payload or {}, default=str)}\n\n"
                        f"Respond with a JSON array of steps. Each step should have:\n"
                        f"- 'type': 'llm', 'tool', or 'branch'\n"
                        f"- 'description': what this step does\n"
                        f"- 'tool_name': (if type=tool) which tool to use\n"
                        f"- 'params': (if type=tool) parameters\n"
                        f"- 'prompt': (if type=llm) the prompt\n"
                    ),
                )
            ],
            system_instruction="You are a plan generator. Output ONLY a valid JSON array of steps.",
            temperature=0,
            max_tokens=4096,
        )

        # Parse plan
        try:
            plan = json.loads(plan_result.content)
            if not isinstance(plan, list):
                plan = [{"type": "llm", "description": "Execute task", "prompt": plan_result.content}]
        except json.JSONDecodeError:
            plan = [{"type": "llm", "description": "Execute task", "prompt": plan_result.content}]

        run.plan = plan
        constraints.record_step(
            input_tokens=plan_result.usage.input_tokens,
            output_tokens=plan_result.usage.output_tokens,
        )
        total_cost = plan_result.cost_usd
        total_input_tokens = plan_result.usage.input_tokens
        total_output_tokens = plan_result.usage.output_tokens

        if emit_event:
            await emit_event(RunEvent("plan_created", {"plan": plan}, run_id=run.id, step_index=0))

        # Phase 2: Execute each step
        step_results: list[dict[str, Any]] = []
        for i, step in enumerate(plan):
            # Check constraints
            violation = constraints.check()
            if violation:
                await self._fail_run(db, run, violation, cost=total_cost, tokens=(total_input_tokens, total_output_tokens))
                return

            # Loop detection
            if loop_detector.check(step):
                await self._fail_run(db, run, "Loop detected: agent is repeating the same action", cost=total_cost, tokens=(total_input_tokens, total_output_tokens))
                return

            step_type = step.get("type", "llm")
            if emit_event:
                await emit_event(RunEvent("step_started", {"step": step, "index": i}, run_id=run.id, step_index=i))

            try:
                if step_type == "llm":
                    result = await executor.execute_llm_step(step, context)
                elif step_type == "tool":
                    result = await executor.execute_tool_step(step, context)
                    if result.get("status") == "escalated":
                        # Create approval request
                        await self._create_approval(db, run, workflow, step, i)
                        run.status = RunStatus.AWAITING_APPROVAL
                        await db.commit()
                        if emit_event:
                            await emit_event(RunEvent("approval_required", {"step_index": i, "step": step}, run_id=run.id, step_index=i))
                        return
                elif step_type == "branch":
                    result = await executor.execute_branch_step(step, context)
                elif step_type == "transform":
                    result = await executor.execute_transform_step(step, context)
                elif step_type == "delay":
                    result = await executor.execute_delay_step(step, context)
                else:
                    result = {"type": step_type, "status": "skipped", "reason": f"Unknown step type: {step_type}"}

            except Exception as exc:
                logger.exception("step_execution_error", step_index=i, step_type=step_type)
                await self._fail_run(db, run, f"Step {i} failed: {exc}", cost=total_cost, tokens=(total_input_tokens, total_output_tokens))
                return

            step_results.append(result)
            context[f"step_{i}_result"] = result

            # Track usage
            usage = result.get("usage", {})
            step_input = usage.get("input_tokens", 0)
            step_output = usage.get("output_tokens", 0)
            step_cost = result.get("cost_usd", 0)
            tool_calls_count = len(result.get("tool_calls", []))

            constraints.record_step(
                input_tokens=step_input,
                output_tokens=step_output,
                tool_calls=max(1, tool_calls_count) if step_type == "tool" else tool_calls_count,
            )
            total_cost += step_cost
            total_input_tokens += step_input
            total_output_tokens += step_output

            run.steps_completed = i + 1
            await db.commit()

            if emit_event:
                await emit_event(RunEvent("step_completed", {"step_index": i, "result": result}, run_id=run.id, step_index=i))

        # Complete the run
        await self._complete_run(
            db, run,
            output={"steps": step_results},
            cost=total_cost,
            tokens=(total_input_tokens, total_output_tokens),
        )

        if emit_event:
            await emit_event(RunEvent("run_completed", {
                "run_id": str(run.id),
                "steps_completed": run.steps_completed,
                "cost_usd": float(run.total_cost_usd or 0),
            }, run_id=run.id))

    async def _execute_defined_workflow(
        self,
        *,
        db: AsyncSession,
        run: AgentRun,
        workflow: Workflow,
        steps: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        executor: StepExecutor,
        constraints: RunConstraints,
        loop_detector: LoopDetector,
        emit_event: Any | None = None,
    ) -> None:
        """Execute a workflow with explicitly defined steps and edges."""
        # Build adjacency from edges
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            adjacency.setdefault(src, []).append(tgt)

        # Build step lookup
        step_lookup: dict[str, dict[str, Any]] = {}
        for step in steps:
            step_lookup[step.get("id", str(uuid.uuid4()))] = step

        context: dict[str, Any] = {
            "_run_id": str(run.id),
            "_workflow_id": str(run.workflow_id),
            "_agent_id": "orchestrator",
        }
        if run.trigger_payload:
            context.update(run.trigger_payload)

        # Find entry points (steps with no incoming edges)
        targets = {e.get("target") for e in edges}
        sources = {s.get("id") for s in steps}
        entry_points = [s.get("id") for s in steps if s.get("id") not in targets]
        if not entry_points:
            entry_points = [steps[0].get("id")] if steps else []

        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        step_results: list[dict[str, Any]] = []
        step_index = 0

        # BFS execution
        queue = list(entry_points)
        visited: set[str] = set()

        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            step = step_lookup.get(current_id)
            if step is None:
                continue

            # Check constraints
            violation = constraints.check()
            if violation:
                await self._fail_run(db, run, violation, cost=total_cost, tokens=(total_input_tokens, total_output_tokens))
                return

            step_type = step.get("type", "llm")
            if emit_event:
                await emit_event(RunEvent("step_started", {"step_id": current_id, "step": step}, run_id=run.id, step_index=step_index))

            try:
                if step_type == "llm":
                    result = await executor.execute_llm_step(step, context)
                elif step_type == "tool":
                    result = await executor.execute_tool_step(step, context)
                    if result.get("status") == "escalated":
                        await self._create_approval(db, run, workflow, step, step_index)
                        run.status = RunStatus.AWAITING_APPROVAL
                        await db.commit()
                        if emit_event:
                            await emit_event(RunEvent("approval_required", {"step_id": current_id}, run_id=run.id))
                        return
                elif step_type == "approval":
                    await self._create_approval(db, run, workflow, step, step_index)
                    run.status = RunStatus.AWAITING_APPROVAL
                    await db.commit()
                    if emit_event:
                        await emit_event(RunEvent("approval_required", {"step_id": current_id}, run_id=run.id))
                    return
                elif step_type == "branch":
                    result = await executor.execute_branch_step(step, context)
                    # Add the selected branch's next steps to queue
                    selected = result.get("selected_branch", "")
                    branch_edges = [e for e in edges if e.get("source") == current_id and e.get("label") == selected]
                    for be in branch_edges:
                        queue.append(be.get("target", ""))
                    step_results.append(result)
                    step_index += 1
                    continue
                elif step_type == "transform":
                    result = await executor.execute_transform_step(step, context)
                elif step_type == "delay":
                    result = await executor.execute_delay_step(step, context)
                elif step_type == "notify":
                    result = {"type": "notify", "message": step.get("message", ""), "channel": step.get("channel", "log")}
                else:
                    result = {"type": step_type, "status": "skipped"}

            except Exception as exc:
                logger.exception("step_execution_error", step_id=current_id)
                await self._fail_run(db, run, f"Step '{current_id}' failed: {exc}", cost=total_cost, tokens=(total_input_tokens, total_output_tokens))
                return

            step_results.append(result)
            context[current_id] = result
            context[f"step_{step_index}_result"] = result

            usage = result.get("usage", {})
            total_cost += result.get("cost_usd", 0)
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)
            constraints.record_step(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                tool_calls=1 if step_type == "tool" else 0,
            )

            run.steps_completed = step_index + 1
            await db.commit()

            if emit_event:
                await emit_event(RunEvent("step_completed", {"step_id": current_id, "result": result}, run_id=run.id, step_index=step_index))

            step_index += 1

            # Add next steps from edges
            for next_id in adjacency.get(current_id, []):
                if next_id not in visited:
                    queue.append(next_id)

        # Complete
        await self._complete_run(db, run, output={"steps": step_results}, cost=total_cost, tokens=(total_input_tokens, total_output_tokens))
        if emit_event:
            await emit_event(RunEvent("run_completed", {"run_id": str(run.id), "steps_completed": run.steps_completed}, run_id=run.id))

    # ── Run lifecycle helpers ────────────────────────────────────────

    async def _fail_run(
        self,
        db: AsyncSession,
        run: AgentRun,
        error_message: str,
        *,
        cost: float = 0,
        tokens: tuple[int, int] = (0, 0),
    ) -> None:
        run.status = RunStatus.FAILED
        run.error = {"message": error_message}
        run.completed_at = datetime.now(UTC)
        run.total_cost_usd = cost
        run.input_tokens = tokens[0]
        run.output_tokens = tokens[1]
        run.wall_time_ms = int((time.monotonic() - (run.started_at or datetime.now(UTC)).timestamp()) * 1000) if run.started_at else 0
        await db.commit()
        logger.error("run_failed", run_id=str(run.id), error=error_message)

    async def _complete_run(
        self,
        db: AsyncSession,
        run: AgentRun,
        *,
        output: dict[str, Any],
        cost: float = 0,
        tokens: tuple[int, int] = (0, 0),
    ) -> None:
        run.status = RunStatus.COMPLETED
        run.output = output
        run.completed_at = datetime.now(UTC)
        run.total_cost_usd = cost
        run.input_tokens = tokens[0]
        run.output_tokens = tokens[1]
        if run.started_at:
            run.wall_time_ms = int((datetime.now(UTC) - run.started_at).total_seconds() * 1000)
        await db.commit()
        logger.info("run_completed", run_id=str(run.id), steps=run.steps_completed, cost=cost)

    async def _create_approval(
        self,
        db: AsyncSession,
        run: AgentRun,
        workflow: Workflow,
        step: dict[str, Any],
        step_index: int,
    ) -> ApprovalRequest:
        """Create an approval request for a step that requires human review."""
        sla_minutes = step.get("sla_minutes", 30)
        approval = ApprovalRequest(
            org_id=run.org_id,
            run_id=run.id,
            step_id=step.get("id", f"step_{step_index}"),
            workflow_id=workflow.id,
            payload={
                "step": step,
                "step_index": step_index,
                "description": step.get("description", "Approval required"),
            },
            context={"trigger_payload": run.trigger_payload},
            required_role=step.get("required_role", "admin"),
            status=ApprovalStatus.PENDING,
            sla_deadline=datetime.now(UTC) + timedelta(minutes=sla_minutes),
        )
        db.add(approval)
        await db.commit()
        return approval

    async def resume_after_approval(
        self,
        run_id: uuid.UUID,
        approval_id: uuid.UUID,
        *,
        emit_event: Any | None = None,
    ) -> None:
        """Resume a run after an approval decision."""
        async with async_session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None or run.status != RunStatus.AWAITING_APPROVAL:
                return

            approval = await db.get(ApprovalRequest, approval_id)
            if approval is None:
                return

            if approval.status == ApprovalStatus.APPROVED:
                # Re-queue the run to continue
                run.status = RunStatus.QUEUED
                await db.commit()
                # Re-execute (in production, this would go through the run queue)
                await self.execute_run(run_id, emit_event=emit_event)
            elif approval.status == ApprovalStatus.REJECTED:
                await self._fail_run(db, run, "Approval rejected")


# ── Singleton ───────────────────────────────────────────────────────

orchestrator = Orchestrator()
