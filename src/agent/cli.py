from __future__ import annotations

import argparse
import asyncio
import json
import os

from src.agent.discovery import DiscoveryRunner
from src.agent.provider import OpenAIDecisionProvider
from src.models import ActionType, PolicyConfig
from src.policy import PolicyEngine


def build_policy(target: str) -> PolicyEngine:
    from urllib.parse import urlparse

    parsed = urlparse(target)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    return PolicyEngine(
        PolicyConfig(
            allowed_origins=[origin],
            allowed_actions={
                ActionType.NAVIGATE,
                ActionType.CLICK,
                ActionType.TYPE,
                ActionType.READ,
                ActionType.WAIT,
            },
            blocked_routes=["/admin"],
        )
    )


async def run(args: argparse.Namespace) -> int:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Put it in the environment; do not commit it."
        )

    provider = OpenAIDecisionProvider(
        model=args.model,
        api_key=api_key,
    )
    runner = DiscoveryRunner(
        provider=provider,
        policy=build_policy(args.target),
        evidence_root=args.evidence_root,
        headless=not args.headed,
    )

    result = await runner.run(
        goal=args.goal,
        target=args.target,
        max_steps=args.max_steps,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.status == "success" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a genuine LLM-driven AgentForge discovery session."
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument(
        "--target",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-5"),
    )
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--evidence-root", default="evidence")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
