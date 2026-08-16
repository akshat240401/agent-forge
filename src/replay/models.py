from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReplayStepRecord(StrictReplayModel):
    step_id: str
    action: str
    resolved_strategy: str | None = None
    resolved_value: str | None = None
    checkpoint_passed: bool | None = None


class ReplayResult(StrictReplayModel):
    status: Literal[
        "success",
        "business_outcome",
        "recoverable",
        "failure",
        "policy_blocked",
        "invalid_input",
    ]
    run_id: str
    capability_id: str
    capability_version: str
    steps: list[ReplayStepRecord] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)

    code: str | None = None
    message: str | None = None
    evidence_path: str | None = None

    # Explicit debugging contract required by the assessment.
    failed_step_id: str | None = None
    expected_state: dict[str, Any] | None = None
    observed_state: dict[str, Any] | None = None
