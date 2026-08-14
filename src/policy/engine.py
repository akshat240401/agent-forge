\
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from src.models import ActionType, PolicyConfig, RiskClass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    reason: str


class PolicyEngine:
    """Evaluate every proposed computer-use action before execution."""

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config
        self._allowed_origins = {
            self._normalize_origin(origin)
            for origin in config.allowed_origins
        }

    @staticmethod
    def _normalize_origin(value: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid origin: {value}")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @staticmethod
    def _origin_for_url(value: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid target URL: {value}")
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @staticmethod
    def _route_for_url(value: str) -> str:
        parsed = urlparse(value)
        return parsed.path or "/"

    def evaluate(
        self,
        *,
        action: ActionType,
        target_url: str,
        risk: RiskClass = RiskClass.SAFE,
    ) -> PolicyDecision:
        try:
            origin = self._origin_for_url(target_url)
        except ValueError as exc:
            return PolicyDecision(
                allowed=False,
                code="invalid_target",
                reason=str(exc),
            )

        if origin not in self._allowed_origins:
            return PolicyDecision(
                allowed=False,
                code="origin_not_allowed",
                reason=f"Origin is outside the configured allowlist: {origin}",
            )

        route = self._route_for_url(target_url)
        if self._is_blocked_route(route):
            return PolicyDecision(
                allowed=False,
                code="route_blocked",
                reason=f"Route is blocked by policy: {route}",
            )

        if action not in self._config.allowed_actions:
            return PolicyDecision(
                allowed=False,
                code="action_not_allowed",
                reason=f"Action type is not permitted: {action.value}",
            )

        if risk in self._config.blocked_risk_classes:
            return PolicyDecision(
                allowed=False,
                code="risk_blocked",
                reason=f"Risk class requires human approval or remains blocked: {risk.value}",
            )

        return PolicyDecision(
            allowed=True,
            code="allowed",
            reason="Action satisfies configured origin, route, action, and risk policy.",
        )

    def _is_blocked_route(self, route: str) -> bool:
        for blocked in self._config.blocked_routes:
            normalized = blocked if blocked.startswith("/") else f"/{blocked}"
            if route == normalized or route.startswith(f"{normalized.rstrip('/')}/"):
                return True
        return False
