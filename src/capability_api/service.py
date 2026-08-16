from __future__ import annotations

from typing import Protocol

from src.capability.artifact import CapabilityArtifactV1
from src.replay import ReplayEngine, ReplayResult, default_replay_policy


class CapabilityInvoker(Protocol):
    async def invoke(
        self,
        *,
        artifact: CapabilityArtifactV1,
        arguments: dict[str, str],
    ) -> ReplayResult:
        ...


class DeterministicCapabilityInvoker:
    """Production-style invocation: saved artifact -> deterministic replay."""

    def __init__(
        self,
        *,
        evidence_root: str = "evidence",
        headless: bool = True,
    ) -> None:
        self.evidence_root = evidence_root
        self.headless = headless

    async def invoke(
        self,
        *,
        artifact: CapabilityArtifactV1,
        arguments: dict[str, str],
    ) -> ReplayResult:
        engine = ReplayEngine(
            artifact=artifact,
            policy=default_replay_policy(artifact),
            evidence_root=self.evidence_root,
            headless=self.headless,
            enable_handoff=False,
        )
        return await engine.run(arguments)
