from __future__ import annotations

from pathlib import Path

from src.capability.artifact import CapabilityArtifactV1, LiteralValue, ParameterValue
from src.handoff.manager import TerminalHandoffManager
from src.models import ActionType, PolicyConfig, RunMode
from src.observability import EvidenceManager, RunRecorder
from src.policy import PolicyEngine
from src.replay.checkpoints import evaluate_checkpoint
from src.replay.extractors import extract_table_cell
from src.replay.models import ReplayResult, ReplayStepRecord
from src.surface import BrowserSurface, first_matching_locator


class ReplayEngine:
    def __init__(
        self,
        *,
        artifact: CapabilityArtifactV1,
        policy: PolicyEngine,
        evidence_root: str = "evidence",
        headless: bool = False,
        enable_handoff: bool = False,
        handoff_input_func=input,
    ) -> None:
        self.artifact = artifact
        self.policy = policy
        self.evidence_root = evidence_root
        self.headless = headless
        self.enable_handoff = enable_handoff
        self.handoff_input_func = handoff_input_func

    async def run(self, inputs: dict[str, str]) -> ReplayResult:
        recorder = RunRecorder(
            evidence_root=self.evidence_root,
            mode=RunMode.REPLAY,
        )
        evidence = EvidenceManager(recorder.run_dir)
        handoff = (
            TerminalHandoffManager(
                recorder=recorder,
                evidence=evidence,
                input_func=self.handoff_input_func,
            )
            if self.enable_handoff
            else None
        )
        records: list[ReplayStepRecord] = []

        error = self._validate_inputs(inputs)
        if error:
            return self._finish(
                recorder,
                ReplayResult(
                    status="invalid_input",
                    run_id=recorder.run_id,
                    capability_id=self.artifact.capability.id,
                    capability_version=self.artifact.capability.version,
                    message=error,
                ),
            )

        entry = self.artifact.target.entry_point
        navigation = self.policy.evaluate(
            action=ActionType.NAVIGATE,
            target_url=entry,
        )
        if not navigation.allowed:
            return self._finish(
                recorder,
                ReplayResult(
                    status="policy_blocked",
                    run_id=recorder.run_id,
                    capability_id=self.artifact.capability.id,
                    capability_version=self.artifact.capability.version,
                    code=navigation.code,
                    message=navigation.reason,
                ),
            )

        async with BrowserSurface(headless=self.headless) as surface:
            await surface.navigate(entry)
            recorder.record(
                "replay_started",
                details={
                    "capability_id": self.artifact.capability.id,
                    "version": self.artifact.capability.version,
                    "inputs": inputs,
                },
            )

            for step in self.artifact.steps:
                policy = self.policy.evaluate(
                    action=step.action,
                    target_url=surface.page.url,
                    risk=step.risk,
                )
                if not policy.allowed:
                    screenshot = await evidence.capture_failure_screenshot(
                        surface,
                        step_id=f"{step.id}_policy",
                    )
                    return self._finish(
                        recorder,
                        ReplayResult(
                            status="policy_blocked",
                            run_id=recorder.run_id,
                            capability_id=self.artifact.capability.id,
                            capability_version=self.artifact.capability.version,
                            steps=records,
                            code=policy.code,
                            message=policy.reason,
                            evidence_path=str(screenshot),
                        ),
                    )

                try:
                    strategy = None
                    resolved_value = None

                    if step.action in {
                        ActionType.CLICK,
                        ActionType.TYPE,
                        ActionType.READ,
                    }:
                        if step.target is None:
                            raise LookupError(f"Step {step.id} has no target.")

                        locator, candidate = await first_matching_locator(
                            surface.page,
                            step.target,
                        )
                        strategy = candidate.strategy
                        resolved_value = candidate.value

                        if step.action == ActionType.CLICK:
                            await locator.click()
                        elif step.action == ActionType.TYPE:
                            await locator.fill(
                                self._resolve_value(step.value, inputs)
                            )
                        else:
                            await locator.inner_text()

                    elif step.action == ActionType.WAIT:
                        await surface.wait(
                            int(self._resolve_value(step.value, inputs))
                        )
                    elif step.action == ActionType.NAVIGATE:
                        await surface.navigate(entry)
                    else:
                        raise ValueError(
                            f"Unsupported replay action: {step.action.value}"
                        )

                    checkpoint_passed = None
                    if step.checkpoint is not None:
                        evaluation = await evaluate_checkpoint(
                            surface,
                            step.checkpoint,
                        )
                        checkpoint_passed = evaluation.passed

                        if not evaluation.passed:
                            business = await self._match_business_outcome(surface)
                            if business is not None:
                                return self._finish(
                                    recorder,
                                    ReplayResult(
                                        status="business_outcome",
                                        run_id=recorder.run_id,
                                        capability_id=self.artifact.capability.id,
                                        capability_version=self.artifact.capability.version,
                                        steps=records + [
                                            self._record_for_step(
                                                step.id,
                                                step.action.value,
                                                strategy,
                                                resolved_value,
                                                False,
                                            )
                                        ],
                                        code=business.code,
                                        message=business.description,
                                    ),
                                )

                            recoverable = await self._detect_recoverable(surface)
                            if recoverable is not None:
                                if handoff is None:
                                    return self._finish(
                                        recorder,
                                        ReplayResult(
                                            status="recoverable",
                                            run_id=recorder.run_id,
                                            capability_id=self.artifact.capability.id,
                                            capability_version=self.artifact.capability.version,
                                            steps=records + [
                                                self._record_for_step(
                                                    step.id,
                                                    step.action.value,
                                                    strategy,
                                                    resolved_value,
                                                    False,
                                                )
                                            ],
                                            code=recoverable,
                                            message=(
                                                "Known recoverable runtime "
                                                "condition detected."
                                            ),
                                        ),
                                    )

                                await handoff.intervene(
                                    surface=surface,
                                    capability_id=self.artifact.capability.id,
                                    capability_version=(
                                        self.artifact.capability.version
                                    ),
                                    current_step=step.id,
                                    reason=(
                                        "Known interstitial blocked deterministic "
                                        "replay and requires manual continuation."
                                    ),
                                )

                                resumed = await evaluate_checkpoint(
                                    surface,
                                    step.checkpoint,
                                )
                                if not resumed.passed:
                                    screenshot = (
                                        await evidence.capture_failure_screenshot(
                                            surface,
                                            step_id=(
                                                f"{step.id}_resume_validation"
                                            ),
                                        )
                                    )
                                    return self._finish(
                                        recorder,
                                        ReplayResult(
                                            status="failure",
                                            run_id=recorder.run_id,
                                            capability_id=(
                                                self.artifact.capability.id
                                            ),
                                            capability_version=(
                                                self.artifact.capability.version
                                            ),
                                            steps=records,
                                            code="resume_validation_failed",
                                            message=(
                                                "Human returned control, but the "
                                                "expected checkpoint was not reached."
                                            ),
                                            evidence_path=str(screenshot),
                                        ),
                                    )

                                checkpoint_passed = True
                                recorder.record(
                                    "resume_validated",
                                    step_id=step.id,
                                    actor="automation",
                                    result={
                                        "checkpoint_passed": True,
                                        "page_title": resumed.observed_title,
                                    },
                                )
                            else:
                                screenshot = (
                                    await evidence.capture_failure_screenshot(
                                        surface,
                                        step_id=f"{step.id}_checkpoint",
                                    )
                                )
                                return self._finish(
                                    recorder,
                                    ReplayResult(
                                        status="failure",
                                        run_id=recorder.run_id,
                                        capability_id=self.artifact.capability.id,
                                        capability_version=(
                                            self.artifact.capability.version
                                        ),
                                        steps=records + [
                                            self._record_for_step(
                                                step.id,
                                                step.action.value,
                                                strategy,
                                                resolved_value,
                                                False,
                                            )
                                        ],
                                        code="checkpoint_failed",
                                        message=(
                                            f"Checkpoint failed after {step.id}. "
                                            f"Expected title="
                                            f"{step.checkpoint.page_title!r} and "
                                            f"text={step.checkpoint.required_text!r}; "
                                            f"observed title="
                                            f"{evaluation.observed_title!r}, "
                                            f"missing="
                                            f"{list(evaluation.missing_text)!r}."
                                        ),
                                        evidence_path=str(screenshot),
                                    ),
                                )

                    record = self._record_for_step(
                        step.id,
                        step.action.value,
                        strategy,
                        resolved_value,
                        checkpoint_passed,
                    )
                    records.append(record)
                    recorder.record(
                        "replay_step_completed",
                        step_id=step.id,
                        action=step.action.value,
                        details={
                            "resolved_strategy": strategy,
                            "resolved_value": resolved_value,
                            "checkpoint_passed": checkpoint_passed,
                        },
                    )

                except Exception as exc:
                    screenshot = await evidence.capture_failure_screenshot(
                        surface,
                        step_id=f"{step.id}_failure",
                    )
                    return self._finish(
                        recorder,
                        ReplayResult(
                            status="failure",
                            run_id=recorder.run_id,
                            capability_id=self.artifact.capability.id,
                            capability_version=self.artifact.capability.version,
                            steps=records,
                            code=type(exc).__name__,
                            message=str(exc),
                            evidence_path=str(screenshot),
                        ),
                    )

            final = await evaluate_checkpoint(
                surface,
                self.artifact.success_checkpoint,
            )
            if not final.passed:
                screenshot = await evidence.capture_failure_screenshot(
                    surface,
                    step_id="success_checkpoint_failed",
                )
                return self._finish(
                    recorder,
                    ReplayResult(
                        status="failure",
                        run_id=recorder.run_id,
                        capability_id=self.artifact.capability.id,
                        capability_version=self.artifact.capability.version,
                        steps=records,
                        code="success_checkpoint_failed",
                        message=(
                            "Final success checkpoint failed. "
                            f"Observed title={final.observed_title!r}, "
                            f"missing={list(final.missing_text)!r}."
                        ),
                        evidence_path=str(screenshot),
                    ),
                )

            try:
                outputs = {
                    name: await extract_table_cell(surface, spec.extractor)
                    for name, spec in self.artifact.outputs.items()
                }
            except Exception as exc:
                screenshot = await evidence.capture_failure_screenshot(
                    surface,
                    step_id="output_extraction_failed",
                )
                return self._finish(
                    recorder,
                    ReplayResult(
                        status="failure",
                        run_id=recorder.run_id,
                        capability_id=self.artifact.capability.id,
                        capability_version=self.artifact.capability.version,
                        steps=records,
                        code=type(exc).__name__,
                        message=str(exc),
                        evidence_path=str(screenshot),
                    ),
                )

            result = ReplayResult(
                status="success",
                run_id=recorder.run_id,
                capability_id=self.artifact.capability.id,
                capability_version=self.artifact.capability.version,
                steps=records,
                outputs=outputs,
            )
            recorder.record(
                "replay_completed",
                result=result.model_dump(mode="json"),
            )
            return self._finish(recorder, result)

    def _validate_inputs(self, inputs: dict[str, str]) -> str | None:
        for name, spec in self.artifact.inputs.items():
            if spec.required and name not in inputs:
                return f"Missing required input: {name}"

        unknown = sorted(set(inputs) - set(self.artifact.inputs))
        if unknown:
            return f"Unknown input(s): {', '.join(unknown)}"

        return None

    @staticmethod
    def _resolve_value(value, inputs: dict[str, str]) -> str:
        if value is None:
            return ""
        if isinstance(value, ParameterValue):
            if value.name not in inputs:
                raise KeyError(f"Missing bound parameter: {value.name}")
            return str(inputs[value.name])
        if isinstance(value, LiteralValue):
            return value.value
        raise TypeError(
            f"Unsupported step value: {type(value).__name__}"
        )

    async def _match_business_outcome(self, surface):
        for outcome in self.artifact.business_outcomes:
            evaluation = await evaluate_checkpoint(
                surface,
                outcome.checkpoint,
            )
            if evaluation.passed:
                return outcome
        return None

    @staticmethod
    async def _detect_recoverable(surface) -> str | None:
        title = await surface.page.title()
        body = await surface.page.locator("body").inner_text()
        if (
            title == "Session Confirmation"
            and "Continue Session" in body
        ):
            return "known_interstitial"
        return None

    @staticmethod
    def _record_for_step(
        step_id,
        action,
        strategy,
        value,
        checkpoint_passed,
    ) -> ReplayStepRecord:
        return ReplayStepRecord(
            step_id=step_id,
            action=action,
            resolved_strategy=strategy,
            resolved_value=value,
            checkpoint_passed=checkpoint_passed,
        )

    @staticmethod
    def _finish(
        recorder: RunRecorder,
        result: ReplayResult,
    ) -> ReplayResult:
        recorder.write_result(result.model_dump(mode="json"))
        return result


def load_artifact(path: str | Path) -> CapabilityArtifactV1:
    return CapabilityArtifactV1.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def default_replay_policy(
    artifact: CapabilityArtifactV1,
) -> PolicyEngine:
    from urllib.parse import urlparse

    parsed = urlparse(artifact.target.entry_point)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    return PolicyEngine(
        PolicyConfig(
            allowed_origins=[origin],
            allowed_actions={
                ActionType.NAVIGATE,
                ActionType.CLICK,
                ActionType.TYPE,
                ActionType.READ,
                ActionType.WAIT,
            },
            blocked_routes=["/admin"],
        )
    )
