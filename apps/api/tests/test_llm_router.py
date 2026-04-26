"""LLM Router unit tests."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.llm import LLMRouter, LLMResult
from app.services.llm import COST_TABLE


def test_cost_table_has_entries():
    assert len(COST_TABLE) > 0


def test_cost_table_covers_anthropic():
    anthropic_keys = [k for k in COST_TABLE if "claude" in k or "anthropic" in k]
    assert len(anthropic_keys) > 0


def test_cost_table_covers_openai():
    openai_keys = [k for k in COST_TABLE if "gpt" in k]
    assert len(openai_keys) > 0


def test_cost_table_covers_gemini():
    gemini_keys = [k for k in COST_TABLE if "gemini" in k]
    assert len(gemini_keys) > 0


def test_llm_result_fields():
    result = LLMResult(
        provider="anthropic",
        content="Hello world",
        model="claude-opus-4-6",
        usage={"input_tokens": 10, "output_tokens": 5},
        tool_calls=[],
        cost_usd=0.0012,
        latency_ms=250,
    )
    assert result.content == "Hello world"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.cost_usd == 0.0012
    assert result.latency_ms == 250
    assert result.tool_calls == []


def test_llm_router_instantiates():
    router = LLMRouter()
    assert router is not None


def test_cost_values_are_positive():
    for model, (input_cost, output_cost) in COST_TABLE.items():
        assert input_cost >= 0, f"Negative input cost for {model}"
        assert output_cost >= 0, f"Negative output cost for {model}"
