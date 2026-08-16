from __future__ import annotations

import argparse
import asyncio
import json

from src.replay.engine import (
    ReplayEngine,
    default_replay_policy,
    load_artifact,
)


async def run(args: argparse.Namespace) -> int:
    artifact = load_artifact(args.artifact)

    engine = ReplayEngine(
        artifact=artifact,
        policy=default_replay_policy(artifact),
        evidence_root=args.evidence_root,
        headless=not args.headed,
        enable_handoff=args.handoff,
    )

    result = await engine.run(
        {
            "member_id": args.member_id,
        }
    )

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.status == "success" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically replay an AgentForge capability "
            "with optional same-session human handoff."
        )
    )
    parser.add_argument(
        "--artifact",
        default="artifacts/member_savings_balance.json",
    )
    parser.add_argument("--member-id", required=True)
    parser.add_argument("--evidence-root", default="evidence")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--handoff",
        action="store_true",
        help=(
            "Pause on a supported blocked state, let a human operate "
            "the same live browser, then revalidate and resume."
        ),
    )
    args = parser.parse_args()

    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
