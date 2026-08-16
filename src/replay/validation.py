from __future__ import annotations

import re

from src.capability.artifact import CapabilityArtifactV1
from src.models import CapabilityValueType


_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


class CapabilityValidationError(ValueError):
    pass


def validate_capability_for_replay(
    artifact: CapabilityArtifactV1,
) -> None:
    # Artifact schema_version is already constrained by Pydantic to "1.0".
    # Validate the independently versioned capability contract as well.
    if not _SEMVER.fullmatch(artifact.capability.version):
        raise CapabilityValidationError(
            "Capability version must be semantic versioning, "
            f"got {artifact.capability.version!r}."
        )

    step_ids = [step.id for step in artifact.steps]
    if len(step_ids) != len(set(step_ids)):
        raise CapabilityValidationError(
            "Capability contains duplicate step IDs."
        )

    for step in artifact.steps:
        if step.action.value in {"click", "type", "read"}:
            if step.target is None or not step.target.candidates:
                raise CapabilityValidationError(
                    f"Step {step.id} requires at least one target candidate."
                )


def validate_runtime_inputs(
    artifact: CapabilityArtifactV1,
    inputs: dict[str, object],
) -> str | None:
    for name, spec in artifact.inputs.items():
        if spec.required and name not in inputs:
            return f"Missing required input: {name}"

        if name not in inputs:
            continue

        value = inputs[name]

        if spec.type == CapabilityValueType.STRING:
            if not isinstance(value, str):
                return f"Input {name} must be a string"
            if spec.required and not value.strip():
                return f"Input {name} must not be empty"

    unknown = sorted(set(inputs) - set(artifact.inputs))
    if unknown:
        return f"Unknown input(s): {', '.join(unknown)}"

    return None
