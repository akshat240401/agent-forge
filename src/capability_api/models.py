from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictAPIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityInvocationRequest(StrictAPIModel):
    arguments: dict[str, str] = Field(
        default_factory=dict,
        description="Typed runtime arguments for the capability.",
    )


class CapabilitySummary(StrictAPIModel):
    id: str
    name: str
    description: str
    version: str
    surface_type: str
    application_family: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    tool_schema: dict[str, Any]


class CapabilityCatalogResponse(StrictAPIModel):
    capabilities: list[CapabilitySummary]
