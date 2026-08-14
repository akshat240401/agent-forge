from __future__ import annotations

import asyncio
import time
from typing import Any

from src.agent.models import (
    DiscoveryDecision,
    DiscoveryResult,
    DiscoveryStep,
)
from src.agent.provider import DecisionProvider
from src.models import ActionType, PolicyConfig, RiskClass, RunMode
from src.observability import EvidenceManager, RunRecorder
from src.policy import PolicyEngine
from src.surface import (
    BrowserObserver,
    BrowserSurface,
    first_matching_locator,
)


class DiscoveryRunner:
    """Real LLM-driven observe -> decide -> policy-check -> act loop."""

    def __init__(
        self,
        *,
        provider: DecisionProvider,
        policy: PolicyEngine,
        evidence_root: str = "evidence",
        headless: bool = False,
    ) -> None:
        self.provider = provider
        self.policy = policy
        self.evidence_root = evidence_root
        self.headless = headless
        self.observer = BrowserObserver()

    async def run(
        self,
        *,
        goal: str,
        target: str,
        max_steps: int = 20,
        timeout_seconds: int = 120,
    ) -> DiscoveryResult:
        recorder = RunRecorder(
            evidence_root=self.evidence_root,
            mode=RunMode.DISCOVERY,
        )
        evidence = EvidenceManager(recorder.run_dir)
        steps: list[DiscoveryStep] = []
        model_history: list[dict[str, Any]] = []
        started_at = time.monotonic()

        navigation_policy = self.policy.evaluate(
            action=ActionType.NAVIGATE,
            target_url=target,
            risk=RiskClass.SAFE,
        )
        recorder.record(
            "policy_evaluated",
            action=ActionType.NAVIGATE.value,
            target=target,
            result={
                "allowed": navigation_policy.allowed,
                "code": navigation_policy.code,
            },
            reason=navigation_policy.reason,
        )

        if not navigation_policy.allowed:
            result = DiscoveryResult(
                status="policy_blocked",
                run_id=recorder.run_id,
                message=navigation_policy.reason,
            )
            recorder.write_result(result.model_dump(mode="json"))
            return result

        async with BrowserSurface(headless=self.headless) as surface:
            await surface.navigate(target)
            recorder.record(
                "navigation_completed",
                action=ActionType.NAVIGATE.value,
                target=target,
            )

            for step_number in range(1, max_steps + 1):
                if time.monotonic() - started_at >= timeout_seconds:
                    result = DiscoveryResult(
                        status="timeout",
                        run_id=recorder.run_id,
                        steps=steps,
                        message="Discovery exceeded the configured timeout.",
                    )
                    recorder.record("run_stopped", result=result.model_dump(mode="json"))
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

                observation = await self.observer.observe(surface)
                recorder.record(
                    "observation",
                    step_id=f"step_{step_number}",
                    details={
                        "url": observation.url,
                        "title": observation.title,
                        "visible_text": observation.visible_text,
                        "controls": [
                            {
                                "index": c.index,
                                "role": c.role,
                                "name": c.name,
                                "text": c.text,
                                "value": c.value,
                            }
                            for c in observation.controls
                        ],
                    },
                )

                try:
                    decision = await asyncio.wait_for(
                        self.provider.decide(
                            goal=goal,
                            observation=observation,
                            step_number=step_number,
                            history=model_history,
                        ),
                        timeout=max(1, timeout_seconds - int(time.monotonic() - started_at)),
                    )
                except Exception as exc:
                    screenshot = await evidence.capture_failure_screenshot(
                        surface,
                        step_id=f"step_{step_number}_model_error",
                    )
                    recorder.record(
                        "model_error",
                        step_id=f"step_{step_number}",
                        details={"error": type(exc).__name__},
                        result={"screenshot": str(screenshot)},
                    )
                    result = DiscoveryResult(
                        status="model_error",
                        run_id=recorder.run_id,
                        steps=steps,
                        message=f"Model decision failed: {type(exc).__name__}",
                    )
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

                target_control = None
                if decision.control_index is not None:
                    target_control = next(
                        (
                            control
                            for control in observation.controls
                            if control.index == decision.control_index
                        ),
                        None,
                    )
                    if target_control is None:
                        screenshot = await evidence.capture_failure_screenshot(
                            surface,
                            step_id=f"step_{step_number}_invalid_control",
                        )
                        recorder.record(
                            "invalid_model_target",
                            step_id=f"step_{step_number}",
                            reason=decision.reason,
                            details={
                                "control_index": decision.control_index,
                                "screenshot": str(screenshot),
                            },
                        )
                        result = DiscoveryResult(
                            status="dead_end",
                            run_id=recorder.run_id,
                            steps=steps,
                            message="Model selected a control that was not present.",
                        )
                        recorder.write_result(result.model_dump(mode="json"))
                        return result

                target_payload = (
                    target_control.target.model_dump(mode="json")
                    if target_control is not None
                    else None
                )

                recorder.record(
                    "decision",
                    step_id=f"step_{step_number}",
                    action=decision.action.value,
                    target=target_payload,
                    reason=decision.reason,
                    details={
                        "control_index": decision.control_index,
                        "value": decision.value,
                    },
                )

                step = DiscoveryStep(
                    step_number=step_number,
                    page_url=observation.url,
                    page_title=observation.title,
                    decision=decision,
                    target=target_payload,
                    observed_text=observation.visible_text,
                )
                steps.append(step)

                if decision.action == ActionType.FINISH:
                    result = DiscoveryResult(
                        status="success",
                        run_id=recorder.run_id,
                        steps=steps,
                        outputs=decision.output_dict(),
                    )
                    recorder.record(
                        "goal_completed",
                        step_id=f"step_{step_number}",
                        reason=decision.reason,
                        result=result.model_dump(mode="json"),
                    )
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

                if decision.action == ActionType.REQUEST_HUMAN:
                    screenshot = await evidence.capture_failure_screenshot(
                        surface,
                        step_id=f"step_{step_number}_human_required",
                    )
                    result = DiscoveryResult(
                        status="human_required",
                        run_id=recorder.run_id,
                        steps=steps,
                        message=decision.reason,
                    )
                    recorder.record(
                        "human_required",
                        step_id=f"step_{step_number}",
                        reason=decision.reason,
                        result={"screenshot": str(screenshot)},
                    )
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

                policy_decision = self.policy.evaluate(
                    action=decision.action,
                    target_url=observation.url,
                    risk=RiskClass.SAFE,
                )
                recorder.record(
                    "policy_evaluated",
                    step_id=f"step_{step_number}",
                    action=decision.action.value,
                    target=target_payload,
                    reason=policy_decision.reason,
                    result={
                        "allowed": policy_decision.allowed,
                        "code": policy_decision.code,
                    },
                )

                if not policy_decision.allowed:
                    screenshot = await evidence.capture_failure_screenshot(
                        surface,
                        step_id=f"step_{step_number}_policy_blocked",
                    )
                    result = DiscoveryResult(
                        status="policy_blocked",
                        run_id=recorder.run_id,
                        steps=steps,
                        message=policy_decision.reason,
                    )
                    recorder.record(
                        "run_stopped",
                        step_id=f"step_{step_number}",
                        result={
                            "status": "policy_blocked",
                            "screenshot": str(screenshot),
                        },
                    )
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

                if decision.action in {
                    ActionType.CLICK,
                    ActionType.TYPE,
                    ActionType.READ,
                }:
                    assert target_control is not None
                    locator, candidate = await first_matching_locator(
                        surface.page,
                        target_control.target,
                    )

                    recorder.record(
                        "target_resolved",
                        step_id=f"step_{step_number}",
                        target=target_payload,
                        details={
                            "strategy": candidate.strategy,
                            "value": candidate.value,
                        },
                    )

                    if decision.action == ActionType.CLICK:
                        await locator.click()
                    elif decision.action == ActionType.TYPE:
                        await locator.fill(decision.value or "")
                    else:
                        read_value = await locator.inner_text()
                        recorder.record(
                            "read_result",
                            step_id=f"step_{step_number}",
                            result={"value": read_value},
                        )

                elif decision.action == ActionType.WAIT:
                    wait_ms = 750
                    if decision.value:
                        try:
                            wait_ms = max(0, min(5000, int(decision.value)))
                        except ValueError:
                            wait_ms = 750
                    await surface.wait(wait_ms)

                elif decision.action == ActionType.NAVIGATE:
                    # Discovery navigation is constrained to the original allowed target.
                    await surface.navigate(target)

                else:
                    screenshot = await evidence.capture_failure_screenshot(
                        surface,
                        step_id=f"step_{step_number}_unsupported_action",
                    )
                    result = DiscoveryResult(
                        status="dead_end",
                        run_id=recorder.run_id,
                        steps=steps,
                        message=f"Unsupported discovery action: {decision.action.value}",
                    )
                    recorder.record(
                        "run_stopped",
                        step_id=f"step_{step_number}",
                        result={"screenshot": str(screenshot)},
                    )
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

                recorder.record(
                    "action_completed",
                    step_id=f"step_{step_number}",
                    action=decision.action.value,
                    target=target_payload,
                )

                model_history.append(
                    {
                        "step": step_number,
                        "action": decision.action.value,
                        "control_index": decision.control_index,
                        "reason": decision.reason,
                    }
                )

            result = DiscoveryResult(
                status="max_steps",
                run_id=recorder.run_id,
                steps=steps,
                message="Discovery reached the configured maximum number of steps.",
            )
            recorder.record("run_stopped", result=result.model_dump(mode="json"))
            recorder.write_result(result.model_dump(mode="json"))
            return result

