
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from src.agent.models import DiscoveryResult
from src.capability.artifact import (
    BusinessOutcomeSpec, CapabilityArtifactV1, CapabilityIdentitySpec,
    CapabilityInputSpec, CapabilityOutputSpec, CapabilityStepSpec,
    CheckpointSpec, LiteralValue, ParameterValue, TableCellExtractor,
    TargetApplicationSpec,
)
from src.models import ActionType, CapabilityValueType, RiskClass, TargetLocator

@dataclass(frozen=True)
class InputBinding:
    name: str
    sample_value: str
    value_type: CapabilityValueType = CapabilityValueType.STRING
    description: str = "Runtime capability input."

@dataclass(frozen=True)
class TableOutputRule:
    name: str
    row_text: str
    column_header: str
    value_type: CapabilityValueType = CapabilityValueType.STRING
    description: str = "Caller-facing capability output."

@dataclass(frozen=True)
class CompilerConfig:
    capability_id: str
    capability_name: str
    description: str
    version: str
    application_family: str
    entry_point: str
    inputs: tuple[InputBinding, ...]
    outputs: tuple[TableOutputRule, ...]

class CapabilityCompiler:
    def compile(self, discovery: DiscoveryResult, config: CompilerConfig) -> CapabilityArtifactV1:
        if discovery.status != "success":
            raise ValueError("Only successful discovery runs can become capabilities.")
        executable_steps = [s for s in discovery.steps if s.decision.action != ActionType.FINISH]
        if not executable_steps:
            raise ValueError("Discovery run contains no executable steps.")

        input_map = {b.sample_value: b for b in config.inputs}
        steps = []

        for index, step in enumerate(executable_steps):
            decision = step.decision
            target = TargetLocator.model_validate(step.target) if step.target else None
            value = None
            if decision.value is not None:
                binding = input_map.get(decision.value)
                value = ParameterValue(name=binding.name) if binding else LiteralValue(value=decision.value)

            next_step = discovery.steps[index + 1] if index + 1 < len(discovery.steps) else step
            required_text = []
            if next_step.page_title != step.page_title:
                for marker in ("Member Record", "Search Result", "Session Confirmation"):
                    if marker in next_step.observed_text:
                        required_text.append(marker)
                        break

            steps.append(CapabilityStepSpec(
                id=f"step_{index+1}_{decision.action.value}",
                action=decision.action,
                target=target,
                value=value,
                checkpoint=CheckpointSpec(page_title=next_step.page_title, required_text=required_text),
                risk=RiskClass.SAFE,
            ))

        final_step = discovery.steps[-1]
        success_text = [m for m in ("Member Record", "Accounts", "Savings") if m in final_step.observed_text]

        return CapabilityArtifactV1(
            capability=CapabilityIdentitySpec(
                id=config.capability_id, name=config.capability_name,
                description=config.description, version=config.version,
            ),
            target=TargetApplicationSpec(
                application_family=config.application_family,
                surface_type="web", entry_point=config.entry_point,
            ),
            inputs={
                b.name: CapabilityInputSpec(
                    type=b.value_type, required=True, description=b.description
                ) for b in config.inputs
            },
            outputs={
                r.name: CapabilityOutputSpec(
                    type=r.value_type, required=True, description=r.description,
                    extractor=TableCellExtractor(row_text=r.row_text, column_header=r.column_header),
                ) for r in config.outputs
            },
            steps=steps,
            success_checkpoint=CheckpointSpec(
                page_title=final_step.page_title,
                required_text=success_text or final_step.observed_text[:1],
            ),
            business_outcomes=[
                BusinessOutcomeSpec(
                    code="member_not_found",
                    description="No matching member exists for the supplied member ID.",
                    checkpoint=CheckpointSpec(
                        page_title="Member Not Found",
                        required_text=["No member found"],
                    ),
                )
            ],
        )

def load_discovery_result(path: str | Path) -> DiscoveryResult:
    return DiscoveryResult.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )

def save_artifact(artifact: CapabilityArtifactV1, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    return output
