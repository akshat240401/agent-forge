from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models import ActionType


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoveryOutput(StrictAgentModel):
    """One caller-facing output produced when discovery reaches the goal."""

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)


class DiscoveryDecision(StrictAgentModel):
    """One model-selected action in the observe -> decide -> act loop."""

    action: ActionType
    control_index: int | None = Field(default=None, ge=0)
    value: str | None = None
    reason: str = Field(min_length=1)
    result: list[DiscoveryOutput] | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if self.action in {ActionType.CLICK, ActionType.TYPE, ActionType.READ}:
            if self.control_index is None:
                raise ValueError(
                    f"control_index is required for {self.action.value}"
                )

        if self.action == ActionType.TYPE and self.value is None:
            raise ValueError("value is required for type")

        if self.action == ActionType.FINISH and not self.result:
            raise ValueError("result is required for finish")

        return self

    def output_dict(self) -> dict[str, str]:
        return {
            item.name: item.value
            for item in (self.result or [])
        }


class DiscoveryStatus(str):
    SUCCESS = "success"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    DEAD_END = "dead_end"
    HUMAN_REQUIRED = "human_required"
    POLICY_BLOCKED = "policy_blocked"
    MODEL_ERROR = "model_error"


class DiscoveryStep(StrictAgentModel):
    step_number: int = Field(ge=1)
    page_url: str
    page_title: str
    decision: DiscoveryDecision
    target: dict | None = None
    observed_text: list[str] = Field(default_factory=list)


class DiscoveryResult(StrictAgentModel):
    status: Literal[
        "success",
        "max_steps",
        "timeout",
        "dead_end",
        "human_required",
        "policy_blocked",
        "model_error",
    ]
    run_id: str
    steps: list[DiscoveryStep] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    message: str | None = None
