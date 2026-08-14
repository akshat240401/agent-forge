import pytest
from pydantic import ValidationError

from src.agent.models import DiscoveryDecision, DiscoveryOutput
from src.models import ActionType


def test_type_requires_control_index_and_value():
    with pytest.raises(ValidationError):
        DiscoveryDecision(
            action=ActionType.TYPE,
            reason="Missing required fields.",
        )


def test_finish_requires_result():
    with pytest.raises(ValidationError):
        DiscoveryDecision(
            action=ActionType.FINISH,
            reason="Done.",
        )


def test_finish_accepts_typed_outputs():
    decision = DiscoveryDecision(
        action=ActionType.FINISH,
        reason="Goal verified.",
        result=[
            DiscoveryOutput(
                name="savings_balance",
                value="$4,821.37",
            )
        ],
    )

    assert decision.output_dict() == {
        "savings_balance": "$4,821.37"
    }
