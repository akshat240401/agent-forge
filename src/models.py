from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionType(str, Enum):
    CLICK = "click"
    TYPE = "type"
    READ = "read"
    NAVIGATE = "navigate"
    WAIT = "wait"
    FINISH = "finish"
    REQUEST_HUMAN = "request_human"


class RiskClass(str, Enum):
    SAFE = "safe"
    REVERSIBLE = "reversible"
    RISKY = "risky"
    IRREVERSIBLE = "irreversible"


class RunMode(str, Enum):
    DISCOVERY = "discovery"
    REPLAY = "replay"


class RunStatus(str, Enum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    RECOVERABLE = "recoverable"
    FAILURE = "failure"


class ControlOwner(str, Enum):
    AUTOMATION = "automation"
    HUMAN = "human"


class GoalRequest(StrictModel):
    goal: str = Field(min_length=1)
    target: HttpUrl
    max_steps: int = Field(default=25, ge=1, le=200)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)


class LocatorCandidate(StrictModel):
    strategy: Literal[
        "role_name",
        "label_text",
        "visible_text",
        "structural",
        "css",
        "xpath",
    ]
    value: str = Field(min_length=1)


class TargetLocator(StrictModel):
    description: str = Field(min_length=1)
    candidates: list[LocatorCandidate] = Field(min_length=1)


class ObservationControl(StrictModel):
    role: str | None = None
    name: str | None = None
    text: str | None = None


class Observation(StrictModel):
    url: str
    title: str | None = None
    visible_text: list[str] = Field(default_factory=list)
    controls: list[ObservationControl] = Field(default_factory=list)
    screenshot_path: str | None = None


class AgentDecision(StrictModel):
    action: ActionType
    target: TargetLocator | None = None
    value: str | None = None
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_for_action(self):
        if self.action in {ActionType.CLICK, ActionType.TYPE, ActionType.READ} and self.target is None:
            raise ValueError(f"target is required for action '{self.action.value}'")
        return self


class CapabilityValueType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"


class CapabilityInput(StrictModel):
    type: CapabilityValueType
    required: bool = True
    description: str = Field(min_length=1)


class CapabilityOutput(StrictModel):
    type: CapabilityValueType
    required: bool = True
    description: str = Field(min_length=1)


class ParameterRef(StrictModel):
    parameter: str = Field(min_length=1)


class LiteralValue(StrictModel):
    literal: str | int | float | bool


StepValue = ParameterRef | LiteralValue


class CheckpointCondition(StrictModel):
    kind: Literal["text_visible", "element_visible", "url_matches", "state"]
    value: str = Field(min_length=1)


class Checkpoint(StrictModel):
    description: str = Field(min_length=1)
    any_of: list[CheckpointCondition] = Field(min_length=1)


class CapabilityStep(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    action: ActionType
    target: TargetLocator | None = None
    value: StepValue | None = None
    checkpoint: Checkpoint | None = None
    output_name: str | None = None
    risk: RiskClass = RiskClass.SAFE


class BusinessOutcomeDefinition(StrictModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    checkpoint: Checkpoint


class CapabilityIdentity(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(min_length=1)


class TargetApplication(StrictModel):
    application_family: str = Field(min_length=1)
    surface_type: Literal["web"]
    entry_point: str = Field(min_length=1)
    compatible_versions: str | None = None


class CapabilityArtifact(StrictModel):
    schema_version: str = Field(min_length=1)
    capability: CapabilityIdentity
    target: TargetApplication
    inputs: dict[str, CapabilityInput]
    outputs: dict[str, CapabilityOutput]
    steps: list[CapabilityStep] = Field(min_length=1)
    success_condition: Checkpoint
    business_outcomes: list[BusinessOutcomeDefinition] = Field(default_factory=list)


class ReplaySuccess(StrictModel):
    status: Literal["success"] = "success"
    outputs: dict[str, Any] = Field(default_factory=dict)


class ReplayBusinessOutcome(StrictModel):
    status: Literal["business_outcome"] = "business_outcome"
    code: str
    detail: str | None = None


class ReplayRecoverable(StrictModel):
    status: Literal["recoverable"] = "recoverable"
    code: str
    step_id: str
    detail: str | None = None


class ReplayFailure(StrictModel):
    status: Literal["failure"] = "failure"
    code: str
    step_id: str
    expected: str
    observed: str
    evidence_path: str | None = None


ReplayResult = ReplaySuccess | ReplayBusinessOutcome | ReplayRecoverable | ReplayFailure


class InterventionRequest(StrictModel):
    intervention_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    goal: str | None = None
    capability_id: str | None = None
    current_step: str | None = None
    reason: str = Field(min_length=1)
    screenshot_path: str | None = None
    control_owner: ControlOwner = ControlOwner.HUMAN


class PolicyConfig(StrictModel):
    allowed_origins: list[str] = Field(min_length=1)
    allowed_actions: set[ActionType] = Field(min_length=1)
    blocked_routes: list[str] = Field(default_factory=list)
    blocked_risk_classes: set[RiskClass] = Field(
        default_factory=lambda: {RiskClass.RISKY, RiskClass.IRREVERSIBLE}
    )
