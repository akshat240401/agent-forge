
from __future__ import annotations
import argparse, json
from src.capability.compiler import (
    CapabilityCompiler, CompilerConfig, InputBinding, TableOutputRule,
    load_discovery_result, save_artifact,
)
from src.models import CapabilityValueType

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--output", default="artifacts/member_savings_balance.json")
    parser.add_argument("--sample-member-id", default="12345")
    args = parser.parse_args()

    discovery = load_discovery_result(args.discovery)
    config = CompilerConfig(
        capability_id="member_savings_balance",
        capability_name="Read Member Savings Balance",
        description="Look up a member in the legacy servicing UI and return their current savings balance.",
        version="1.0.0",
        application_family="legacy_member_servicing",
        entry_point="http://127.0.0.1:8000/",
        inputs=(InputBinding(
            name="member_id", sample_value=args.sample_member_id,
            value_type=CapabilityValueType.STRING,
            description="Member identifier to look up.",
        ),),
        outputs=(TableOutputRule(
            name="savings_balance", row_text="Savings", column_header="Balance",
            value_type=CapabilityValueType.STRING,
            description="Current balance of the member's savings account.",
        ),),
    )
    artifact = CapabilityCompiler().compile(discovery, config)
    path = save_artifact(artifact, args.output)
    print(f"Saved capability artifact: {path}")
    print(json.dumps(artifact.model_dump(mode="json"), indent=2))

if __name__ == "__main__":
    main()
