"""Multi-provider LLM routing for Anthropic, Gemini, and Ollama.

This module provides a thin abstraction over provider-specific REST APIs so the
future orchestration engine can choose a provider per role while keeping the
execution contract stable.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config import ModelProvider, settings

MessageRole = Literal["system", "user", "assistant"]
ModelRole = Literal["planner", "worker", "classifier"]


class LLMInvocationError(RuntimeError):
    """Raised when a provider call cannot be completed successfully."""


class ChatMessage(BaseModel):
    """Normalized chat message format used across providers."""

    role: MessageRole
    content: str = Field(min_length=1)


class LLMUsage(BaseModel):
    """Normalized token usage data returned by a provider."""

    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMResult(BaseModel):
    """Normalized provider response."""

    provider: ModelProvider
    model: str
    content: str
    finish_reason: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    raw: dict[str, Any] = Field(default_factory=dict)


class ProviderProfile(BaseModel):
    """Resolved concrete provider configuration for a model role."""

    role: ModelRole
    provider: ModelProvider
    model: str
    base_url: str
    api_key: str | None = None


class LLMRouter:
    """Route model requests to the configured provider profile."""

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    def profile_for_role(self, role: ModelRole) -> ProviderProfile:
        """Resolve the concrete provider profile for a model role."""

        provider = settings.model_provider_for_role(role)
        return ProviderProfile(
            role=role,
            provider=provider,
            model=settings.model_name_for_role(role),
            base_url=self._base_url_for_provider(provider),
            api_key=self._api_key_for_provider(provider),
        )

    def fallback_profile(self, role: ModelRole) -> ProviderProfile | None:
        """Return the fallback provider profile when hybrid routing is enabled."""

        if settings.MODEL_ROUTING_MODE != "hybrid" or settings.MODEL_FALLBACK_PROVIDER is None:
            return None

        fallback_provider = settings.MODEL_FALLBACK_PROVIDER
        primary_provider = settings.model_provider_for_role(role)
        if fallback_provider == primary_provider:
            return None

        model = {
            ("anthropic", "planner"): settings.ANTHROPIC_MODEL_PLANNER,
            ("anthropic", "worker"): settings.ANTHROPIC_MODEL_WORKER,
            ("anthropic", "classifier"): settings.ANTHROPIC_MODEL_CLASSIFIER,
            ("gemini", "planner"): settings.GEMINI_MODEL_PLANNER,
            ("gemini", "worker"): settings.GEMINI_MODEL_WORKER,
            ("gemini", "classifier"): settings.GEMINI_MODEL_CLASSIFIER,
            ("ollama", "planner"): settings.OLLAMA_MODEL_PLANNER,
            ("ollama", "worker"): settings.OLLAMA_MODEL_WORKER,
            ("ollama", "classifier"): settings.OLLAMA_MODEL_CLASSIFIER,
        }[(fallback_provider, role)]

        return ProviderProfile(
            role=role,
            provider=fallback_provider,
            model=model,
            base_url=self._base_url_for_provider(fallback_provider),
            api_key=self._api_key_for_provider(fallback_provider),
        )

    async def generate(
        self,
        *,
        role: ModelRole,
        messages: list[ChatMessage],
        system_instruction: str | None = None,
        temperature: float = 0,
        max_tokens: int = 1024,
    ) -> LLMResult:
        """Invoke the configured provider, falling back when hybrid mode is enabled."""

        profiles = [self.profile_for_role(role)]
        fallback = self.fallback_profile(role)
        if fallback is not None:
            profiles.append(fallback)

        last_error: Exception | None = None
        for profile in profiles:
            try:
                return await self._invoke_profile(
                    profile=profile,
                    messages=messages,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                last_error = exc

        raise LLMInvocationError(f"All provider attempts failed for role '{role}'") from last_error

    async def _invoke_profile(
        self,
        *,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResult:
        """Dispatch the request to a provider-specific implementation."""

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            if profile.provider == "anthropic":
                return await self._invoke_anthropic(
                    client=client,
                    profile=profile,
                    messages=messages,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            if profile.provider == "gemini":
                return await self._invoke_gemini(
                    client=client,
                    profile=profile,
                    messages=messages,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            if profile.provider == "ollama":
                return await self._invoke_ollama(
                    client=client,
                    profile=profile,
                    messages=messages,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

        raise LLMInvocationError(f"Unsupported provider '{profile.provider}'")

    async def _invoke_anthropic(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResult:
        """Call Anthropic's Messages API."""

        api_key = self._require_api_key(profile)
        payload = {
            "model": profile.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in messages
                if msg.role in {"user", "assistant"}
            ],
        }
        if system_instruction:
            payload["system"] = system_instruction

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
        text = "\n".join(block.get("text", "") for block in content_blocks if isinstance(block, dict)).strip()

        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=text,
            finish_reason=data.get("stop_reason"),
            usage=LLMUsage(
                input_tokens=data.get("usage", {}).get("input_tokens"),
                output_tokens=data.get("usage", {}).get("output_tokens"),
            ),
            raw=data,
        )

    async def _invoke_gemini(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResult:
        """Call Gemini's generateContent REST API."""

        api_key = self._require_api_key(profile)
        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if msg.role == "assistant" else "user",
                    "parts": [{"text": msg.content}],
                }
                for msg in messages
                if msg.role != "system"
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

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
        text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()

        usage = data.get("usageMetadata", {})
        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=text,
            finish_reason=candidate.get("finishReason"),
            usage=LLMUsage(
                input_tokens=usage.get("promptTokenCount"),
                output_tokens=usage.get("candidatesTokenCount"),
            ),
            raw=data,
        )

    async def _invoke_ollama(
        self,
        *,
        client: httpx.AsyncClient,
        profile: ProviderProfile,
        messages: list[ChatMessage],
        system_instruction: str | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResult:
        """Call Ollama's local chat endpoint."""

        payload_messages = []
        if system_instruction:
            payload_messages.append({"role": "system", "content": system_instruction})
        payload_messages.extend({"role": msg.role, "content": msg.content} for msg in messages if msg.role != "system")

        headers = {"content-type": "application/json"}
        if profile.api_key:
            headers["authorization"] = f"Bearer {profile.api_key}"

        response = await client.post(
            f"{profile.base_url.rstrip('/')}/api/chat",
            headers=headers,
            json={
                "model": profile.model,
                "messages": payload_messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {})

        return LLMResult(
            provider=profile.provider,
            model=profile.model,
            content=message.get("content", "").strip(),
            finish_reason=data.get("done_reason"),
            usage=LLMUsage(
                input_tokens=data.get("prompt_eval_count"),
                output_tokens=data.get("eval_count"),
            ),
            raw=data,
        )

    def _base_url_for_provider(self, provider: ModelProvider) -> str:
        """Resolve the base URL for a provider."""

        return {
            "anthropic": settings.ANTHROPIC_BASE_URL,
            "gemini": settings.GEMINI_BASE_URL,
            "ollama": settings.OLLAMA_BASE_URL,
        }[provider]

    def _api_key_for_provider(self, provider: ModelProvider) -> str | None:
        """Resolve the configured credential for a provider."""

        return {
            "anthropic": settings.ANTHROPIC_API_KEY,
            "gemini": settings.GEMINI_API_KEY,
            "ollama": settings.OLLAMA_API_KEY,
        }[provider]

    def _require_api_key(self, profile: ProviderProfile) -> str:
        """Require an API key for hosted providers."""

        if profile.api_key:
            return profile.api_key
        raise LLMInvocationError(
            f"Provider '{profile.provider}' is selected for role '{profile.role}' but its API key is not configured"
        )
