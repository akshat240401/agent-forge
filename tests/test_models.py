import pytest
from pydantic import ValidationError

from src.models import (
    ActionType,
    AgentDecision,
    BusinessOutcomeDefinition,
    CapabilityArtifact,
    CapabilityIdentity,
    CapabilityInput,
    CapabilityOutput,
    CapabilityStep,
    CapabilityValueType,
    Checkpoint,
    CheckpointCondition,
    GoalRequest,
    LocatorCandidate,
    ParameterRef,
    PolicyConfig,
    RiskClass,
    TargetApplication,
    TargetLocator,
)


def locator() -> TargetLocator:
    return TargetLocator(
        description="Member ID field",
        candidates=[
            LocatorCandidate(strategy="role_name", value="textbox|Member ID"),
            LocatorCandidate(strategy="label_text", value="Member ID"),
        ],
    )


def checkpoint(text: str) -> Checkpoint:
    return Checkpoint(
        description=f"Verify {text}",
        any_of=[CheckpointCondition(kind="text_visible", value=text)],
    )


def test_goal_request_requires_goal_and_target():
    req = GoalRequest(
        goal="Look up member 12345 and return savings balance",
        target="http://localhost:8000",
    )
    assert req.max_steps == 25
    assert str(req.target).startswith("http://localhost:8000")


def test_agent_decision_requires_target_for_type():
    with pytest.raises(ValidationError):
        AgentDecision(action=ActionType.TYPE, value="12345", reason="Enter member ID")


def test_capability_artifact_is_typed_versioned_and_parameterized():
    artifact = CapabilityArtifact(
        schema_version="1.0",
        capability=CapabilityIdentity(
            id="member_savings_balance",
            name="Read Member Savings Balance",
            description="Look up a member and return the savings balance.",
            version="1.0.0",
        ),
        target=TargetApplication(
            application_family="legacy_member_servicing",
            surface_type="web",
            entry_point="/members",
            compatible_versions="1.x",
        ),
        inputs={
            "member_id": CapabilityInput(
                type=CapabilityValueType.STRING,
                description="Member identifier",
            )
        },
        outputs={
            "savings_balance": CapabilityOutput(
                type=CapabilityValueType.DECIMAL,
                description="Current savings balance",
            )
        },
        steps=[
            CapabilityStep(
                id="enter_member_id",
                action=ActionType.TYPE,
                target=locator(),
                value=ParameterRef(parameter="member_id"),
                checkpoint=checkpoint("Member ID"),
                risk=RiskClass.SAFE,
            )
        ],
        success_condition=checkpoint("Savings"),
        business_outcomes=[
            BusinessOutcomeDefinition(
                code="member_not_found",
                description="No matching member exists.",
                checkpoint=checkpoint("No member found"),
            )
        ],
    )

    payload = artifact.model_dump(mode="json")
    assert payload["schema_version"] == "1.0"
    assert payload["steps"][0]["value"]["parameter"] == "member_id"
    assert payload["business_outcomes"][0]["code"] == "member_not_found"


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        CapabilityInput(
            type=CapabilityValueType.STRING,
            description="Member identifier",
            unexpected=True,
        )


def test_policy_defaults_block_risky_and_irreversible():
    policy = PolicyConfig(
        allowed_origins=["http://localhost:8000"],
        allowed_actions={ActionType.CLICK, ActionType.TYPE, ActionType.READ},
    )
    assert RiskClass.RISKY in policy.blocked_risk_classes
    assert RiskClass.IRREVERSIBLE in policy.blocked_risk_classes
