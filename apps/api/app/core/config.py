"""Application configuration loaded from environment variables.

Uses pydantic-settings to validate and type-check all configuration at startup.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ModelProvider = Literal[
    "anthropic", "openai", "gemini", "mistral", "cohere", "groq", "together", "azure_openai", "ollama"
]
RoutingMode = Literal["single", "hybrid", "cost", "latency"]


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

    # ── OpenAI ───────────────────────────────────────────────────────
    OPENAI_API_KEY: str | None = Field(default=None)
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com")
    OPENAI_MODEL_PLANNER: str = Field(default="gpt-4o")
    OPENAI_MODEL_WORKER: str = Field(default="gpt-4o-mini")
    OPENAI_MODEL_CLASSIFIER: str = Field(default="gpt-4o-mini")

    # ── Mistral ──────────────────────────────────────────────────────
    MISTRAL_API_KEY: str | None = Field(default=None)
    MISTRAL_BASE_URL: str = Field(default="https://api.mistral.ai")
    MISTRAL_MODEL_PLANNER: str = Field(default="mistral-large-latest")
    MISTRAL_MODEL_WORKER: str = Field(default="mistral-medium-latest")
    MISTRAL_MODEL_CLASSIFIER: str = Field(default="mistral-small-latest")

    # ── Cohere ───────────────────────────────────────────────────────
    COHERE_API_KEY: str | None = Field(default=None)
    COHERE_BASE_URL: str = Field(default="https://api.cohere.com")
    COHERE_MODEL_PLANNER: str = Field(default="command-r-plus")
    COHERE_MODEL_WORKER: str = Field(default="command-r")
    COHERE_MODEL_CLASSIFIER: str = Field(default="command-r")

    # ── Groq ─────────────────────────────────────────────────────────
    GROQ_API_KEY: str | None = Field(default=None)
    GROQ_BASE_URL: str = Field(default="https://api.groq.com/openai")
    GROQ_MODEL_PLANNER: str = Field(default="llama-3.3-70b-versatile")
    GROQ_MODEL_WORKER: str = Field(default="llama-3.1-8b-instant")
    GROQ_MODEL_CLASSIFIER: str = Field(default="llama-3.1-8b-instant")

    # ── Together ─────────────────────────────────────────────────────
    TOGETHER_API_KEY: str | None = Field(default=None)
    TOGETHER_BASE_URL: str = Field(default="https://api.together.xyz")
    TOGETHER_MODEL_PLANNER: str = Field(default="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
    TOGETHER_MODEL_WORKER: str = Field(default="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")
    TOGETHER_MODEL_CLASSIFIER: str = Field(default="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")

    # ── Azure OpenAI ─────────────────────────────────────────────────
    AZURE_OPENAI_API_KEY: str | None = Field(default=None)
    AZURE_OPENAI_ENDPOINT: str = Field(default="")
    AZURE_OPENAI_API_VERSION: str = Field(default="2024-06-01")
    AZURE_OPENAI_DEPLOYMENT_PLANNER: str = Field(default="gpt-4o")
    AZURE_OPENAI_DEPLOYMENT_WORKER: str = Field(default="gpt-4o-mini")
    AZURE_OPENAI_DEPLOYMENT_CLASSIFIER: str = Field(default="gpt-4o-mini")

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
        mapping: dict[tuple[str, str], str] = {
            ("anthropic", "planner"): self.ANTHROPIC_MODEL_PLANNER,
            ("anthropic", "worker"): self.ANTHROPIC_MODEL_WORKER,
            ("anthropic", "classifier"): self.ANTHROPIC_MODEL_CLASSIFIER,
            ("openai", "planner"): self.OPENAI_MODEL_PLANNER,
            ("openai", "worker"): self.OPENAI_MODEL_WORKER,
            ("openai", "classifier"): self.OPENAI_MODEL_CLASSIFIER,
            ("gemini", "planner"): self.GEMINI_MODEL_PLANNER,
            ("gemini", "worker"): self.GEMINI_MODEL_WORKER,
            ("gemini", "classifier"): self.GEMINI_MODEL_CLASSIFIER,
            ("mistral", "planner"): self.MISTRAL_MODEL_PLANNER,
            ("mistral", "worker"): self.MISTRAL_MODEL_WORKER,
            ("mistral", "classifier"): self.MISTRAL_MODEL_CLASSIFIER,
            ("cohere", "planner"): self.COHERE_MODEL_PLANNER,
            ("cohere", "worker"): self.COHERE_MODEL_WORKER,
            ("cohere", "classifier"): self.COHERE_MODEL_CLASSIFIER,
            ("groq", "planner"): self.GROQ_MODEL_PLANNER,
            ("groq", "worker"): self.GROQ_MODEL_WORKER,
            ("groq", "classifier"): self.GROQ_MODEL_CLASSIFIER,
            ("together", "planner"): self.TOGETHER_MODEL_PLANNER,
            ("together", "worker"): self.TOGETHER_MODEL_WORKER,
            ("together", "classifier"): self.TOGETHER_MODEL_CLASSIFIER,
            ("azure_openai", "planner"): self.AZURE_OPENAI_DEPLOYMENT_PLANNER,
            ("azure_openai", "worker"): self.AZURE_OPENAI_DEPLOYMENT_WORKER,
            ("azure_openai", "classifier"): self.AZURE_OPENAI_DEPLOYMENT_CLASSIFIER,
            ("ollama", "planner"): self.OLLAMA_MODEL_PLANNER,
            ("ollama", "worker"): self.OLLAMA_MODEL_WORKER,
            ("ollama", "classifier"): self.OLLAMA_MODEL_CLASSIFIER,
        }
        return mapping[(provider, role)]

    def base_url_for_provider(self, provider: ModelProvider) -> str:
        """Resolve the base URL for a provider."""

        urls: dict[str, str] = {
            "anthropic": self.ANTHROPIC_BASE_URL,
            "openai": self.OPENAI_BASE_URL,
            "gemini": self.GEMINI_BASE_URL,
            "mistral": self.MISTRAL_BASE_URL,
            "cohere": self.COHERE_BASE_URL,
            "groq": self.GROQ_BASE_URL,
            "together": self.TOGETHER_BASE_URL,
            "azure_openai": self.AZURE_OPENAI_ENDPOINT,
            "ollama": self.OLLAMA_BASE_URL,
        }
        return urls[provider]

    def api_key_for_provider(self, provider: ModelProvider) -> str | None:
        """Resolve the configured credential for a provider."""

        keys: dict[str, str | None] = {
            "anthropic": self.ANTHROPIC_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "gemini": self.GEMINI_API_KEY,
            "mistral": self.MISTRAL_API_KEY,
            "cohere": self.COHERE_API_KEY,
            "groq": self.GROQ_API_KEY,
            "together": self.TOGETHER_API_KEY,
            "azure_openai": self.AZURE_OPENAI_API_KEY,
            "ollama": self.OLLAMA_API_KEY,
        }
        return keys[provider]


# Singleton — import this throughout the application.
settings = Settings()  # type: ignore[call-arg]
