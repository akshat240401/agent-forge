from src.models import ActionType, PolicyConfig, RiskClass
from src.policy import PolicyEngine


def policy() -> PolicyEngine:
    return PolicyEngine(
        PolicyConfig(
            allowed_origins=["http://127.0.0.1:8000"],
            allowed_actions={
                ActionType.CLICK,
                ActionType.TYPE,
                ActionType.READ,
                ActionType.WAIT,
            },
            blocked_routes=["/admin"],
        )
    )


def test_safe_allowed_action_on_allowed_origin_passes():
    decision = policy().evaluate(
        action=ActionType.READ,
        target_url="http://127.0.0.1:8000/members/12345",
        risk=RiskClass.SAFE,
    )
    assert decision.allowed is True
    assert decision.code == "allowed"


def test_unlisted_origin_is_blocked():
    decision = policy().evaluate(
        action=ActionType.READ,
        target_url="https://example.com/members/12345",
    )
    assert decision.allowed is False
    assert decision.code == "origin_not_allowed"


def test_blocked_route_and_descendants_are_denied():
    engine = policy()

    exact = engine.evaluate(
        action=ActionType.READ,
        target_url="http://127.0.0.1:8000/admin",
    )
    child = engine.evaluate(
        action=ActionType.READ,
        target_url="http://127.0.0.1:8000/admin/users",
    )

    assert exact.code == "route_blocked"
    assert child.code == "route_blocked"


def test_unlisted_action_is_blocked():
    decision = policy().evaluate(
        action=ActionType.NAVIGATE,
        target_url="http://127.0.0.1:8000/",
    )
    assert decision.allowed is False
    assert decision.code == "action_not_allowed"


def test_risky_and_irreversible_actions_are_default_denied():
    engine = policy()

    risky = engine.evaluate(
        action=ActionType.CLICK,
        target_url="http://127.0.0.1:8000/",
        risk=RiskClass.RISKY,
    )
    irreversible = engine.evaluate(
        action=ActionType.CLICK,
        target_url="http://127.0.0.1:8000/",
        risk=RiskClass.IRREVERSIBLE,
    )

    assert risky.code == "risk_blocked"
    assert irreversible.code == "risk_blocked"
