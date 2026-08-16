from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictHandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InterventionRequest(StrictHandoffModel):
    intervention_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    capability_version: str = Field(min_length=1)
    current_step: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    screenshot: str
    control_owner: Literal["human"] = "human"


class HumanAction(StrictHandoffModel):
    event: Literal["click", "input", "change"]
    tag: str
    text: str | None = None
    name: str | None = None
    input_type: str | None = None
    value: str | None = None


class HandoffResult(StrictHandoffModel):
    resumed: bool
    intervention: InterventionRequest
    human_actions: list[HumanAction] = Field(default_factory=list)
