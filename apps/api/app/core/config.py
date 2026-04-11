"""Application configuration loaded from environment variables.

Uses pydantic-settings to validate and type-check all configuration at startup.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelProvider = Literal["anthropic", "gemini", "ollama"]
RoutingMode = Literal["single", "hybrid"]


class Settings(BaseSettings):
    """Central configuration for the Enterprise Agent OS API.

    All values are read from environment variables (or an .env file).
    Secrets should be injected via the runtime environment, **never** committed.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Infrastructure ──────────────────────────────────────────────
    DATABASE_URL: str = Field(..., description="PostgreSQL asyncpg connection string")
    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    REDIS_POOL_SIZE: int = Field(default=50)
    NATS_URL: str = Field(default="nats://localhost:4222", description="NATS server URL")
    NATS_CREDENTIALS: str | None = None
    QDRANT_URL: str = Field(default="http://localhost:6333")
    QDRANT_API_KEY: str | None = None

    # ── Secrets ──────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Anthropic API key for Claude models")
    GEMINI_API_KEY: str | None = Field(default=None, description="Google Gemini API key")
    OLLAMA_API_KEY: str | None = Field(default=None, description="Optional auth token for remote Ollama gateways")
    VAULT_ADDR: str = Field(default="http://localhost:8200", description="HashiCorp Vault address")
    JWT_PUBLIC_KEY: str = Field(..., description="RS256 public key (PEM) for JWT verification")
    ENCRYPTION_KEY: str = Field(..., description="Field-level encryption key for sensitive payloads")

    # ── Runtime ──────────────────────────────────────────────────────
    ENVIRONMENT: str = Field(default="development", description="Runtime environment")
    LOG_LEVEL: str = Field(default="INFO")
    DEBUG: bool = Field(default=False)
    GOVERNANCE_PROXY_URL: str = Field(default="http://localhost:8090")
    TOOL_REGISTRY_URL: str = Field(default="http://localhost:8000/v1/tools")

    # ── Governance Defaults ──────────────────────────────────────────
    INJECTION_DETECTION_THRESHOLD: float = Field(default=0.6)
    MAX_RUN_STEPS_DEFAULT: int = Field(default=25)
    MAX_RUN_TIME_SECONDS_DEFAULT: int = Field(default=600)
    MAX_TOOL_CALLS_DEFAULT: int = Field(default=50)

    # ── Model Routing ────────────────────────────────────────────────
    MODEL_ROUTING_MODE: RoutingMode = Field(
        default="single",
        description="single = one provider per role, hybrid = per-role provider + fallback",
    )
    MODEL_FALLBACK_PROVIDER: ModelProvider | None = Field(
        default=None,
        description="Fallback provider for recoverable model invocation failures",
    )
    MODEL_PLANNER_PROVIDER: ModelProvider = Field(default="anthropic")
    MODEL_WORKER_PROVIDER: ModelProvider = Field(default="anthropic")
    MODEL_CLASSIFIER_PROVIDER: ModelProvider = Field(default="anthropic")

    # ── Anthropic ────────────────────────────────────────────────────
    ANTHROPIC_BASE_URL: str = Field(default="https://api.anthropic.com")
    ANTHROPIC_API_VERSION: str = Field(default="2023-06-01")
    ANTHROPIC_MODEL_PLANNER: str = Field(default="claude-opus-4-5-20250514")
    ANTHROPIC_MODEL_WORKER: str = Field(default="claude-sonnet-4-5-20250514")
    ANTHROPIC_MODEL_CLASSIFIER: str = Field(default="claude-haiku-4-5-20251001")

    # ── Gemini ───────────────────────────────────────────────────────
    GEMINI_BASE_URL: str = Field(default="https://generativelanguage.googleapis.com")
    GEMINI_MODEL_PLANNER: str = Field(default="gemini-2.5-pro")
    GEMINI_MODEL_WORKER: str = Field(default="gemini-2.5-flash")
    GEMINI_MODEL_CLASSIFIER: str = Field(default="gemini-2.5-flash-lite")

    # ── Ollama ───────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL_PLANNER: str = Field(default="qwen3-coder")
    OLLAMA_MODEL_WORKER: str = Field(default="qwen3-coder")
    OLLAMA_MODEL_CLASSIFIER: str = Field(default="gemma3")

    # ── S3 / Object Storage ──────────────────────────────────────────
    S3_BUCKET_ARTIFACTS: str = Field(default="enterprise-os-artifacts")
    S3_BUCKET_AUDIT_ARCHIVE: str = Field(default="enterprise-os-audit")
    AWS_REGION: str = Field(default="us-east-1")

    # ── Observability ────────────────────────────────────────────────
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="http://localhost:4317")
    SENTRY_DSN: str = Field(default="", description="Sentry DSN (empty disables Sentry)")

    # ── CORS ─────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])

    @field_validator(
        "MODEL_ROUTING_MODE",
        "MODEL_PLANNER_PROVIDER",
        "MODEL_WORKER_PROVIDER",
        "MODEL_CLASSIFIER_PROVIDER",
        "MODEL_FALLBACK_PROVIDER",
        mode="before",
    )
    @classmethod
    def normalize_model_fields(cls, value: object) -> object:
        """Normalize provider and routing strings from environment variables."""

        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: object) -> bool:
        """Coerce common string env formats into a stable boolean."""

        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
                return False
        return bool(value)

    def model_provider_for_role(self, role: Literal["planner", "worker", "classifier"]) -> ModelProvider:
        """Return the selected provider for a logical model role."""

        return {
            "planner": self.MODEL_PLANNER_PROVIDER,
            "worker": self.MODEL_WORKER_PROVIDER,
            "classifier": self.MODEL_CLASSIFIER_PROVIDER,
        }[role]

    def model_name_for_role(self, role: Literal["planner", "worker", "classifier"]) -> str:
        """Return the concrete model name for a logical role and provider."""

        provider = self.model_provider_for_role(role)
        return {
            ("anthropic", "planner"): self.ANTHROPIC_MODEL_PLANNER,
            ("anthropic", "worker"): self.ANTHROPIC_MODEL_WORKER,
            ("anthropic", "classifier"): self.ANTHROPIC_MODEL_CLASSIFIER,
            ("gemini", "planner"): self.GEMINI_MODEL_PLANNER,
            ("gemini", "worker"): self.GEMINI_MODEL_WORKER,
            ("gemini", "classifier"): self.GEMINI_MODEL_CLASSIFIER,
            ("ollama", "planner"): self.OLLAMA_MODEL_PLANNER,
            ("ollama", "worker"): self.OLLAMA_MODEL_WORKER,
            ("ollama", "classifier"): self.OLLAMA_MODEL_CLASSIFIER,
        }[(provider, role)]


# Singleton — import this throughout the application.
settings = Settings()  # type: ignore[call-arg]
