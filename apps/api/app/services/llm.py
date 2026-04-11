"""Multi-provider LLM routing for 9 providers with streaming, tool calls, and cost tracking.

Providers: Anthropic, OpenAI, Gemini, Mistral, Cohere, Groq, Together, Azure OpenAI, Ollama.

Supports routing modes: single, hybrid (with fallback), cost-optimized, latency-optimized.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx
import structlog
from pydantic import BaseModel, Field

from app.core.config import ModelProvider, settings

logger = structlog.get_logger(__name__)

MessageRole = Literal["system", "user", "assistant", "tool"]
ModelRole = Literal["planner", "worker", "classifier"]


class LLMInvocationError(RuntimeError):
    """Raised when a provider call cannot be completed successfully."""


# ── Normalized Types ────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """Normalized chat message format used across providers."""

    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolCall(BaseModel):
    """Normalized tool call representation."""

    id: str
    function_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    """Tool definition for providers that support function calling."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    """Normalized token usage data returned by a provider."""

    input_tokens: int = 0
    output_tokens: int = 0


class LLMResult(BaseModel):
    """Normalized provider response."""

    provider: str
    model: str
    content: str = ""
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: LLMUsage = Field(default_factory=LLMUsage)
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)


class StreamChunk(BaseModel):
    """A single chunk in a streaming response."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: LLMUsage | None = None


class ProviderProfile(BaseModel):
    """Resolved concrete provider configuration for a model role."""

    role: ModelRole
    provider: str
    model: str
    base_url: str
    api_key: str | None = None


# ── Cost Table (USD per 1M tokens) ──────────────────────────────────

COST_TABLE: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "claude-opus-4-5-20250514": (15.0, 75.0),
    "claude-sonnet-4-5-20250514": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 5.0),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-2.5-flash-lite": (0.015, 0.06),
    "mistral-large-latest": (2.0, 6.0),
    "mistral-medium-latest": (2.7, 8.1),
    "mistral-small-latest": (0.2, 0.6),
    "command-r-plus": (2.5, 10.0),
    "command-r": (0.15, 0.60),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": (0.88, 0.88),
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": (0.18, 0.18),
}


def _estimate_cost(model: str, usage: LLMUsage) -> float:
    """Estimate cost in USD using the cost table."""
    rates = COST_TABLE.get(model)
    if rates is None:
        return 0.0
    input_cost = (usage.input_tokens / 1_000_000) * rates[0]
    output_cost = (usage.output_tokens / 1_000_000) * rates[1]
    return round(input_cost + output_cost, 8)


# ── OpenAI-compatible provider helper ────────────────────────────────


def _openai_compatible_payload(
    *,
    model: str,
    messages: list[ChatMessage],
    system_instruction: str | None,
    temperature: float,
    max_tokens: int,
    tools: list[ToolDefinition] | None,
    stream: bool,
) -> dict[str, Any]:
    """Build a payload for OpenAI-compatible chat/completions endpoints."""
    payload_messages: list[dict[str, Any]] = []

    if system_instruction:
        payload_messages.append({"role": "system", "content": system_instruction})

    for msg in messages:
        if msg.role == "system":
            continue
        m: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_call_id:
            m["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            m["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function_name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
        if msg.name:
            m["name"] = msg.name
        payload_messages.append(m)

    payload: dict[str, Any] = {
        "model": model,
        "messages": payload_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    return payload


def _parse_openai_response(data: dict[str, Any]) -> tuple[str, list[ToolCall], str | None, LLMUsage]:
    """Parse a standard OpenAI-format response into normalized parts."""
    choices = data.get("choices", [])
    choice = choices[0] if choices else {}
    message = choice.get("message", {})

    content = message.get("content") or ""
    finish_reason = choice.get("finish_reason")

    tool_calls: list[ToolCall] = []
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            args = {}
        tool_calls.append(
            ToolCall(id=tc.get("id", ""), function_name=fn.get("name", ""), arguments=args)
        )

    raw_usage = data.get("usage", {})
    usage = LLMUsage(
        input_tokens=raw_usage.get("prompt_tokens", 0),
        output_tokens=raw_usage.get("completion_tokens", 0),
    )

    return content, tool_calls, finish_reason, usage


# ── LLM Router ──────────────────────────────────────────────────────


class LLMRouter:
    """Route model requests to configured providers with fallback and cost tracking."""

    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self.timeout_seconds = timeout_seconds

    def profile_for_role(self, role: ModelRole) -> ProviderProfile:
        """Resolve the concrete provider profile for a model role."""
        provider = settings.model_provider_for_role(role)
        return ProviderProfile(
            role=role,
            provider=provider,
            model=settings.model_name_for_role(role),
            base_url=settings.base_url_for_provider(provider),
            api_key=settings.api_key_for_provider(provider),
        )

    def fallback_profile(self, role: ModelRole) -> ProviderProfile | None:
        """Return the fallback provider profile when hybrid routing is enabled."""
        if settings.MODEL_ROUTING_MODE not in ("hybrid", "cost", "latency"):
            return None
        if settings.MODEL_FALLBACK_PROVIDER is None:
            return None

        fallback_provider = settings.MODEL_FALLBACK_PROVIDER
        primary_provider = settings.model_provider_for_role(role)
        if fallback_provider == primary_provider:
            return None

        model = settings.model_name_for_role.__func__(settings, role)  # type: ignore[attr-defined]
        # Override: use fallback provider's model for the role
        _orig = getattr(settings, f"MODEL_{role.upper()}_PROVIDER")
        try:
            object.__setattr__(settings, f"MODEL_{role.upper()}_PROVIDER", fallback_provider)
            model = settings.model_name_for_role(role)
        finally:
            object.__setattr__(settings, f"MODEL_{role.upper()}_PROVIDER", _orig)

        return ProviderProfile(
            role=role,
            provider=fallback_provider,
            model=model,
            base_url=settings.base_url_for_provider(fallback_provider),
            api_key=settings.api_key_for_provider(fallback_provider),
        )

    # ── Main generate entry point ────────────────────────────────

    async def generate(
        self,
        *,
        role: ModelRole,
        messages: list[ChatMessage],
        system_instruction: str | None = None,
        temperature: float = 0,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResult:
        """Invoke the configured provider, falling back when hybrid mode is enabled."""
        profiles = [self.profile_for_role(role)]
        fallback = self.fallback_profile(role)
        if fallback is not None:
            profiles.append(fallback)

        last_error: Exception | None = None
        for profile in profiles:
            try:
                start = time.monotonic()
                result = await self._invoke_profile(
                    profile=profile,
                    messages=messages,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )
                result.latency_ms = int((time.monotonic() - start) * 1000)
                result.cost_usd = _estimate_cost(profile.model, result.usage)
                logger.info(
                    "llm_invoke_success",
                    provider=profile.provider,
                    model=profile.model,
                    role=role,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    cost_usd=result.cost_usd,
                    latency_ms=result.latency_ms,
                )
                return result
            except Exception as exc:
                logger.warning(
                    "llm_invoke_failed",
                    provider=profile.provider,
                    model=profile.model,
                    role=role,
                    error=str(exc),
                )
                last_error = exc

        raise LLMInvocationError(f"All provider attempts failed for role '{role}'") from last_error

    # ── Streaming entry point ────────────────────────────────────

    async def generate_stream(
        self,
        *,
        role: ModelRole,
        messages: list[ChatMessage],
        system_instruction: str | None = None,
        temperature: float = 0,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream tokens from the configured provider."""
        profile = self.profile_for_role(role)
        async for chunk in self._stream_profile(
            profile=profile,
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        ):
            yield chunk

    # ── Dispatch ─────────────────────────────────────────────────

    async def _invoke_profile(
        self,
        *,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        """Dispatch the request to a provider-specific implementation."""
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            dispatch = {
                "anthropic": self._invoke_anthropic,
                "openai": self._invoke_openai_compat,
                "gemini": self._invoke_gemini,
                "mistral": self._invoke_openai_compat,
                "cohere": self._invoke_cohere,
                "groq": self._invoke_openai_compat,
                "together": self._invoke_openai_compat,
                "azure_openai": self._invoke_azure_openai,
                "ollama": self._invoke_ollama,
            }
            handler = dispatch.get(profile.provider)
            if handler is None:
                raise LLMInvocationError(f"Unsupported provider '{profile.provider}'")
            return await handler(
                client=client,
                profile=profile,
                messages=messages,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )

    async def _stream_profile(
        self,
        *,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream from an OpenAI-compatible endpoint (works for OpenAI, Groq, Together, Mistral)."""
        # For non-OpenAI-compat providers, fall back to non-streaming
        openai_compat_providers = {"openai", "groq", "together", "mistral", "azure_openai"}

        if profile.provider == "anthropic":
            async for chunk in self._stream_anthropic(
                profile=profile,
                messages=messages,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            ):
                yield chunk
            return

        if profile.provider in openai_compat_providers:
            url = self._openai_compat_url(profile)
            headers = self._openai_compat_headers(profile)
            payload = _openai_compatible_payload(
                model=profile.model,
                messages=messages,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                stream=True,
            )

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        yield StreamChunk(
                            content=delta.get("content") or "",
                            finish_reason=choices[0].get("finish_reason"),
                        )
            return

        # Fallback: non-streaming generate, yield as a single chunk
        result = await self._invoke_profile(
            profile=profile,
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )
        yield StreamChunk(
            content=result.content,
            tool_calls=result.tool_calls,
            finish_reason=result.finish_reason,
            usage=result.usage,
        )

    # ── Anthropic ────────────────────────────────────────────────

    async def _invoke_anthropic(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        api_key = self._require_api_key(profile)
        payload: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [],
        }

        for msg in messages:
            if msg.role == "system":
                continue
            m: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.role == "tool" and msg.tool_call_id:
                m = {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": msg.tool_call_id, "content": msg.content}
                    ],
                }
            payload["messages"].append(m)

        if system_instruction:
            payload["system"] = system_instruction

        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        response = await client.post(
            f"{profile.base_url.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": settings.ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        content_blocks = data.get("content", [])
        text_parts: list[str] = []
        tool_calls_out: list[ToolCall] = []

        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls_out.append(
                    ToolCall(
                        id=block.get("id", ""),
                        function_name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content="\n".join(text_parts).strip(),
            finish_reason=data.get("stop_reason"),
            tool_calls=tool_calls_out,
            usage=LLMUsage(
                input_tokens=data.get("usage", {}).get("input_tokens", 0),
                output_tokens=data.get("usage", {}).get("output_tokens", 0),
            ),
            raw=data,
        )

    async def _stream_anthropic(
        self,
        *,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> AsyncIterator[StreamChunk]:
        api_key = self._require_api_key(profile)
        payload: dict[str, Any] = {
            "model": profile.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in messages
                if msg.role in ("user", "assistant")
            ],
        }
        if system_instruction:
            payload["system"] = system_instruction

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{profile.base_url.rstrip('/')}/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": settings.ANTHROPIC_API_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    event_type = data.get("type")
                    if event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        yield StreamChunk(content=delta.get("text", ""))
                    elif event_type == "message_delta":
                        yield StreamChunk(
                            finish_reason=data.get("delta", {}).get("stop_reason"),
                            usage=LLMUsage(
                                output_tokens=data.get("usage", {}).get("output_tokens", 0),
                            ),
                        )

    # ── OpenAI-Compatible (OpenAI, Groq, Together, Mistral) ──────

    def _openai_compat_url(self, profile: ProviderProfile) -> str:
        base = profile.base_url.rstrip("/")
        return f"{base}/v1/chat/completions"

    def _openai_compat_headers(self, profile: ProviderProfile) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if profile.api_key:
            headers["authorization"] = f"Bearer {profile.api_key}"
        return headers

    async def _invoke_openai_compat(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        """Call any OpenAI-compatible chat/completions endpoint."""
        api_key = self._require_api_key(profile)
        url = self._openai_compat_url(profile)
        headers = self._openai_compat_headers(profile)
        payload = _openai_compatible_payload(
            model=profile.model,
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=False,
        )

        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        content, tool_calls_out, finish_reason, usage = _parse_openai_response(data)
        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=content,
            finish_reason=finish_reason,
            tool_calls=tool_calls_out,
            usage=usage,
            raw=data,
        )

    # ── Gemini ───────────────────────────────────────────────────

    async def _invoke_gemini(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        api_key = self._require_api_key(profile)
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if msg.role == "assistant" else "user",
                    "parts": [{"text": msg.content}],
                }
                for msg in messages
                if msg.role not in ("system", "tool")
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        if tools:
            payload["tools"] = [
                {
                    "function_declarations": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }
                        for t in tools
                    ]
                }
            ]

        response = await client.post(
            f"{profile.base_url.rstrip('/')}/v1beta/models/{profile.model}:generateContent",
            headers={"x-goog-api-key": api_key, "content-type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        candidate = candidates[0] if candidates else {}
        parts = candidate.get("content", {}).get("parts", [])
        text_parts: list[str] = []
        tool_calls_out: list[ToolCall] = []

        for part in parts:
            if not isinstance(part, dict):
                continue
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls_out.append(
                    ToolCall(
                        id=fc.get("name", ""),
                        function_name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                    )
                )

        raw_usage = data.get("usageMetadata", {})
        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content="\n".join(text_parts).strip(),
            finish_reason=candidate.get("finishReason"),
            tool_calls=tool_calls_out,
            usage=LLMUsage(
                input_tokens=raw_usage.get("promptTokenCount", 0),
                output_tokens=raw_usage.get("candidatesTokenCount", 0),
            ),
            raw=data,
        )

    # ── Cohere ───────────────────────────────────────────────────

    async def _invoke_cohere(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        api_key = self._require_api_key(profile)

        # Cohere v2 chat API uses OpenAI-compat message format
        api_messages: list[dict[str, Any]] = []
        if system_instruction:
            api_messages.append({"role": "system", "content": system_instruction})
        for msg in messages:
            if msg.role == "system":
                continue
            api_messages.append({"role": msg.role, "content": msg.content})

        payload: dict[str, Any] = {
            "model": profile.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        response = await client.post(
            f"{profile.base_url.rstrip('/')}/v2/chat",
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        content = data.get("message", {}).get("content", [])
        text = ""
        if content and isinstance(content, list):
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict)).strip()
        elif isinstance(content, str):
            text = content

        tool_calls_out: list[ToolCall] = []
        for tc in data.get("message", {}).get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls_out.append(
                ToolCall(id=tc.get("id", ""), function_name=fn.get("name", ""), arguments=args)
            )

        raw_usage = data.get("usage", {})
        billed = raw_usage.get("billed_units", {})
        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=text,
            finish_reason=data.get("finish_reason"),
            tool_calls=tool_calls_out,
            usage=LLMUsage(
                input_tokens=billed.get("input_tokens", 0),
                output_tokens=billed.get("output_tokens", 0),
            ),
            raw=data,
        )

    # ── Azure OpenAI ─────────────────────────────────────────────

    async def _invoke_azure_openai(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        api_key = self._require_api_key(profile)
        endpoint = profile.base_url.rstrip("/")
        url = (
            f"{endpoint}/openai/deployments/{profile.model}"
            f"/chat/completions?api-version={settings.AZURE_OPENAI_API_VERSION}"
        )
        payload = _openai_compatible_payload(
            model=profile.model,
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=False,
        )
        # Azure doesn't use the model field in the body
        payload.pop("model", None)

        response = await client.post(
            url,
            headers={"api-key": api_key, "content-type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        content, tool_calls_out, finish_reason, usage = _parse_openai_response(data)
        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=content,
            finish_reason=finish_reason,
            tool_calls=tool_calls_out,
            usage=usage,
            raw=data,
        )

    # ── Ollama ───────────────────────────────────────────────────

    async def _invoke_ollama(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
    ) -> LLMResult:
        payload_messages: list[dict[str, Any]] = []
        if system_instruction:
            payload_messages.append({"role": "system", "content": system_instruction})
        payload_messages.extend(
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.role != "system"
        )

        headers: dict[str, str] = {"content-type": "application/json"}
        if profile.api_key:
            headers["authorization"] = f"Bearer {profile.api_key}"

        payload: dict[str, Any] = {
            "model": profile.model,
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        response = await client.post(
            f"{profile.base_url.rstrip('/')}/api/chat",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {})

        tool_calls_out: list[ToolCall] = []
        for tc in message.get("tool_calls", []):
            fn = tc.get("function", {})
            tool_calls_out.append(
                ToolCall(
                    id=fn.get("name", ""),
                    function_name=fn.get("name", ""),
                    arguments=fn.get("arguments", {}),
                )
            )

        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=message.get("content", "").strip(),
            finish_reason=data.get("done_reason"),
            tool_calls=tool_calls_out,
            usage=LLMUsage(
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            ),
            raw=data,
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _require_api_key(self, profile: ProviderProfile) -> str:
        if profile.api_key:
            return profile.api_key
        # Ollama doesn't require an API key
        if profile.provider == "ollama":
            return ""
        raise LLMInvocationError(
            f"Provider '{profile.provider}' is selected for role '{profile.role}' "
            f"but its API key is not configured"
        )


# ── Singleton ───────────────────────────────────────────────────────

llm_router = LLMRouter()
