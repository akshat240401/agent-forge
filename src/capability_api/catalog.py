from __future__ import annotations

from pathlib import Path
from typing import Any

from src.capability.artifact import CapabilityArtifactV1
from src.replay import load_artifact

from .models import CapabilitySummary


class CapabilityCatalog:
    """Loads reviewable AgentForge artifacts and exposes them as callable tools."""

    def __init__(self, artifact_dir: str | Path = "artifacts") -> None:
        self.artifact_dir = Path(artifact_dir)

    def _artifact_paths(self) -> list[Path]:
        if not self.artifact_dir.exists():
            return []
        return sorted(self.artifact_dir.glob("*.json"))

    def load_all(self) -> dict[str, CapabilityArtifactV1]:
        capabilities: dict[str, CapabilityArtifactV1] = {}

        for path in self._artifact_paths():
            artifact = load_artifact(path)
            capability_id = artifact.capability.id

            if capability_id in capabilities:
                raise ValueError(
                    f"Duplicate capability id {capability_id!r} "
                    f"in {self.artifact_dir}."
                )

            capabilities[capability_id] = artifact

        return capabilities

    def get(self, capability_id: str) -> CapabilityArtifactV1:
        capabilities = self.load_all()
        try:
            return capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown capability: {capability_id}"
            ) from exc

    def list_summaries(self) -> list[CapabilitySummary]:
        return [
            self.summary(artifact)
            for artifact in self.load_all().values()
        ]

    @staticmethod
    def _json_type(value_type: Any) -> str:
        value = getattr(value_type, "value", value_type)
        mapping = {
            "string": "string",
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
        }
        return mapping.get(str(value), "string")

    @classmethod
    def summary(
        cls,
        artifact: CapabilityArtifactV1,
    ) -> CapabilitySummary:
        input_properties: dict[str, Any] = {}
        required_inputs: list[str] = []

        for name, spec in artifact.inputs.items():
            input_properties[name] = {
                "type": cls._json_type(spec.type),
                "description": spec.description,
            }
            if spec.required:
                required_inputs.append(name)

        output_properties: dict[str, Any] = {}
        required_outputs: list[str] = []

        for name, spec in artifact.outputs.items():
            output_properties[name] = {
                "type": cls._json_type(spec.type),
                "description": spec.description,
            }
            if spec.required:
                required_outputs.append(name)

        input_schema = {
            "type": "object",
            "properties": input_properties,
            "required": required_inputs,
            "additionalProperties": False,
        }
        output_schema = {
            "type": "object",
            "properties": output_properties,
            "required": required_outputs,
            "additionalProperties": False,
        }

        # Tool schema is intentionally provider-neutral while matching the
        # shape commonly consumed by function/tool-calling agents.
        tool_schema = {
            "type": "function",
            "name": artifact.capability.id,
            "description": artifact.capability.description,
            "parameters": input_schema,
        }

        return CapabilitySummary(
            id=artifact.capability.id,
            name=artifact.capability.name,
            description=artifact.capability.description,
            version=artifact.capability.version,
            surface_type=artifact.target.surface_type,
            application_family=artifact.target.application_family,
            input_schema=input_schema,
            output_schema=output_schema,
            tool_schema=tool_schema,
        )
