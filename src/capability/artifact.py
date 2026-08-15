
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.models import ActionType, CapabilityValueType, RiskClass, TargetLocator

class StrictArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ParameterValue(StrictArtifactModel):
    kind: Literal["parameter"] = "parameter"
    name: str = Field(min_length=1)

class LiteralValue(StrictArtifactModel):
    kind: Literal["literal"] = "literal"
    value: str

StepValue = ParameterValue | LiteralValue

class CapabilityInputSpec(StrictArtifactModel):
    type: CapabilityValueType
    required: bool = True
    description: str = Field(min_length=1)

class TableCellExtractor(StrictArtifactModel):
    strategy: Literal["table_cell"] = "table_cell"
    row_text: str = Field(min_length=1)
    column_header: str = Field(min_length=1)

class CapabilityOutputSpec(StrictArtifactModel):
    type: CapabilityValueType
    required: bool = True
    description: str = Field(min_length=1)
    extractor: TableCellExtractor

class CheckpointSpec(StrictArtifactModel):
    page_title: str | None = None
    required_text: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_assertion(self):
        if self.page_title is None and not self.required_text:
            raise ValueError("checkpoint requires page_title or required_text")
        return self

class CapabilityStepSpec(StrictArtifactModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    action: ActionType
    target: TargetLocator | None = None
    value: StepValue | None = None
    checkpoint: CheckpointSpec | None = None
    risk: RiskClass = RiskClass.SAFE

class BusinessOutcomeSpec(StrictArtifactModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    checkpoint: CheckpointSpec

class CapabilityIdentitySpec(StrictArtifactModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(min_length=1)

class TargetApplicationSpec(StrictArtifactModel):
    application_family: str = Field(min_length=1)
    surface_type: Literal["web"] = "web"
    entry_point: str = Field(min_length=1)
    compatible_versions: str | None = None

class CapabilityArtifactV1(StrictArtifactModel):
    schema_version: Literal["1.0"] = "1.0"
    capability: CapabilityIdentitySpec
    target: TargetApplicationSpec
    inputs: dict[str, CapabilityInputSpec]
    outputs: dict[str, CapabilityOutputSpec]
    steps: list[CapabilityStepSpec] = Field(min_length=1)
    success_checkpoint: CheckpointSpec
    business_outcomes: list[BusinessOutcomeSpec] = Field(default_factory=list)
