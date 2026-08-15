
from __future__ import annotations
from pathlib import Path
from src.capability.artifact import CapabilityArtifactV1, LiteralValue, ParameterValue
from src.models import ActionType, PolicyConfig, RunMode
from src.observability import EvidenceManager, RunRecorder
from src.policy import PolicyEngine
from src.replay.checkpoints import evaluate_checkpoint
from src.replay.extractors import extract_table_cell
from src.replay.models import ReplayResult, ReplayStepRecord
from src.surface import BrowserSurface, first_matching_locator

class ReplayEngine:
    def __init__(self, *, artifact: CapabilityArtifactV1, policy: PolicyEngine, evidence_root: str="evidence", headless: bool=False):
        self.artifact = artifact
        self.policy = policy
        self.evidence_root = evidence_root
        self.headless = headless

    async def run(self, inputs: dict[str, str]) -> ReplayResult:
        recorder = RunRecorder(evidence_root=self.evidence_root, mode=RunMode.REPLAY)
        evidence = EvidenceManager(recorder.run_dir)
        records: list[ReplayStepRecord] = []
        err = self._validate_inputs(inputs)
        if err:
            result = ReplayResult(status="invalid_input", run_id=recorder.run_id,
                capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                message=err)
            recorder.write_result(result.model_dump(mode="json"))
            return result

        entry = self.artifact.target.entry_point
        nav = self.policy.evaluate(action=ActionType.NAVIGATE, target_url=entry)
        if not nav.allowed:
            result = ReplayResult(status="policy_blocked", run_id=recorder.run_id,
                capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                code=nav.code, message=nav.reason)
            recorder.write_result(result.model_dump(mode="json"))
            return result

        async with BrowserSurface(headless=self.headless) as surface:
            await surface.navigate(entry)
            recorder.record("replay_started", details={
                "capability_id": self.artifact.capability.id,
                "version": self.artifact.capability.version,
                "inputs": inputs,
            })

            for step in self.artifact.steps:
                pol = self.policy.evaluate(action=step.action, target_url=surface.page.url, risk=step.risk)
                if not pol.allowed:
                    shot = await evidence.capture_failure_screenshot(surface, step_id=f"{step.id}_policy")
                    result = ReplayResult(status="policy_blocked", run_id=recorder.run_id,
                        capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                        steps=records, code=pol.code, message=pol.reason, evidence_path=str(shot))
                    recorder.write_result(result.model_dump(mode="json"))
                    return result
                try:
                    strategy = value = None
                    if step.action in {ActionType.CLICK, ActionType.TYPE, ActionType.READ}:
                        if step.target is None:
                            raise LookupError(f"Step {step.id} has no target.")
                        locator, candidate = await first_matching_locator(surface.page, step.target)
                        strategy, value = candidate.strategy, candidate.value
                        if step.action == ActionType.CLICK:
                            await locator.click()
                        elif step.action == ActionType.TYPE:
                            await locator.fill(self._resolve_value(step.value, inputs))
                        else:
                            await locator.inner_text()
                    elif step.action == ActionType.WAIT:
                        await surface.wait(int(self._resolve_value(step.value, inputs)))
                    elif step.action == ActionType.NAVIGATE:
                        await surface.navigate(entry)
                    else:
                        raise ValueError(f"Unsupported replay action: {step.action.value}")

                    passed = None
                    if step.checkpoint is not None:
                        evaluation = await evaluate_checkpoint(surface, step.checkpoint)
                        passed = evaluation.passed
                        if not passed:
                            business = await self._match_business_outcome(surface)
                            if business:
                                result = ReplayResult(status="business_outcome", run_id=recorder.run_id,
                                    capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                                    steps=records+[ReplayStepRecord(step_id=step.id, action=step.action.value,
                                        resolved_strategy=strategy, resolved_value=value, checkpoint_passed=False)],
                                    code=business.code, message=business.description)
                                recorder.write_result(result.model_dump(mode="json"))
                                return result
                            recoverable = await self._detect_recoverable(surface)
                            if recoverable:
                                result = ReplayResult(status="recoverable", run_id=recorder.run_id,
                                    capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                                    steps=records+[ReplayStepRecord(step_id=step.id, action=step.action.value,
                                        resolved_strategy=strategy, resolved_value=value, checkpoint_passed=False)],
                                    code=recoverable, message="Known recoverable runtime condition detected.")
                                recorder.write_result(result.model_dump(mode="json"))
                                return result
                            shot = await evidence.capture_failure_screenshot(surface, step_id=f"{step.id}_checkpoint")
                            result = ReplayResult(status="failure", run_id=recorder.run_id,
                                capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                                steps=records+[ReplayStepRecord(step_id=step.id, action=step.action.value,
                                    resolved_strategy=strategy, resolved_value=value, checkpoint_passed=False)],
                                code="checkpoint_failed", message=f"Checkpoint failed after {step.id}.",
                                evidence_path=str(shot))
                            recorder.write_result(result.model_dump(mode="json"))
                            return result

                    record = ReplayStepRecord(step_id=step.id, action=step.action.value,
                        resolved_strategy=strategy, resolved_value=value, checkpoint_passed=passed)
                    records.append(record)
                    recorder.record("replay_step_completed", step_id=step.id, action=step.action.value,
                        details={"resolved_strategy": strategy, "resolved_value": value, "checkpoint_passed": passed})
                except Exception as exc:
                    shot = await evidence.capture_failure_screenshot(surface, step_id=f"{step.id}_failure")
                    result = ReplayResult(status="failure", run_id=recorder.run_id,
                        capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                        steps=records, code=type(exc).__name__, message=str(exc), evidence_path=str(shot))
                    recorder.write_result(result.model_dump(mode="json"))
                    return result

            final = await evaluate_checkpoint(surface, self.artifact.success_checkpoint)
            if not final.passed:
                business = await self._match_business_outcome(surface)
                if business:
                    result = ReplayResult(status="business_outcome", run_id=recorder.run_id,
                        capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                        steps=records, code=business.code, message=business.description)
                    recorder.write_result(result.model_dump(mode="json"))
                    return result
                recoverable = await self._detect_recoverable(surface)
                if recoverable:
                    result = ReplayResult(status="recoverable", run_id=recorder.run_id,
                        capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                        steps=records, code=recoverable, message="Known recoverable runtime condition detected.")
                    recorder.write_result(result.model_dump(mode="json"))
                    return result
                shot = await evidence.capture_failure_screenshot(surface, step_id="success_checkpoint_failed")
                result = ReplayResult(status="failure", run_id=recorder.run_id,
                    capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                    steps=records, code="success_checkpoint_failed", message="Final success checkpoint failed.",
                    evidence_path=str(shot))
                recorder.write_result(result.model_dump(mode="json"))
                return result

            try:
                outputs = {name: await extract_table_cell(surface, spec.extractor)
                           for name, spec in self.artifact.outputs.items()}
            except Exception as exc:
                shot = await evidence.capture_failure_screenshot(surface, step_id="output_extraction_failed")
                result = ReplayResult(status="failure", run_id=recorder.run_id,
                    capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                    steps=records, code=type(exc).__name__, message=str(exc), evidence_path=str(shot))
                recorder.write_result(result.model_dump(mode="json"))
                return result

            result = ReplayResult(status="success", run_id=recorder.run_id,
                capability_id=self.artifact.capability.id, capability_version=self.artifact.capability.version,
                steps=records, outputs=outputs)
            recorder.record("replay_completed", result=result.model_dump(mode="json"))
            recorder.write_result(result.model_dump(mode="json"))
            return result

    def _validate_inputs(self, inputs: dict[str, str]) -> str | None:
        for name, spec in self.artifact.inputs.items():
            if spec.required and name not in inputs:
                return f"Missing required input: {name}"
        unknown = sorted(set(inputs) - set(self.artifact.inputs))
        return f"Unknown input(s): {', '.join(unknown)}" if unknown else None

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
        raise TypeError(f"Unsupported step value: {type(value).__name__}")

    async def _match_business_outcome(self, surface):
        for outcome in self.artifact.business_outcomes:
            if (await evaluate_checkpoint(surface, outcome.checkpoint)).passed:
                return outcome
        return None

    @staticmethod
    async def _detect_recoverable(surface) -> str | None:
        title = await surface.page.title()
        body = await surface.page.locator("body").inner_text()
        if title == "Session Confirmation" and "Continue Session" in body:
            return "known_interstitial"
        return None

def load_artifact(path: str | Path) -> CapabilityArtifactV1:
    return CapabilityArtifactV1.model_validate_json(Path(path).read_text(encoding="utf-8"))

def default_replay_policy(artifact: CapabilityArtifactV1) -> PolicyEngine:
    from urllib.parse import urlparse
    parsed = urlparse(artifact.target.entry_point)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return PolicyEngine(PolicyConfig(
        allowed_origins=[origin],
        allowed_actions={ActionType.NAVIGATE,ActionType.CLICK,ActionType.TYPE,ActionType.READ,ActionType.WAIT},
        blocked_routes=["/admin"],
    ))
