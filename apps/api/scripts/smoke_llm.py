"""Simple provider smoke-test for local model configuration."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.services.llm import ChatMessage, LLMRouter


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the LLM smoke test."""

    parser = argparse.ArgumentParser(description="Run a smoke test against the configured LLM provider")
    parser.add_argument("--role", choices=["planner", "worker", "classifier"], default="worker")
    parser.add_argument("--prompt", required=True, help="Prompt to send to the selected model role")
    parser.add_argument("--system", default=None, help="Optional system instruction")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--max-tokens", type=int, default=512)
    return parser.parse_args()


async def main() -> None:
    """Run a single provider invocation and print normalized output."""

    args = parse_args()
    router = LLMRouter()
    result = await router.generate(
        role=args.role,
        messages=[ChatMessage(role="user", content=args.prompt)],
        system_instruction=args.system,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
