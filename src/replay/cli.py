
from __future__ import annotations
import argparse, asyncio, json
from src.replay.engine import ReplayEngine, default_replay_policy, load_artifact

async def run(args):
    artifact = load_artifact(args.artifact)
    result = await ReplayEngine(
        artifact=artifact,
        policy=default_replay_policy(artifact),
        evidence_root=args.evidence_root,
        headless=not args.headed,
    ).run({"member_id": args.member_id})
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.status == "success" else 1

def main():
    parser = argparse.ArgumentParser(description="Deterministically replay an AgentForge capability.")
    parser.add_argument("--artifact", default="artifacts/member_savings_balance.json")
    parser.add_argument("--member-id", required=True)
    parser.add_argument("--evidence-root", default="evidence")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))

if __name__ == "__main__":
    main()
