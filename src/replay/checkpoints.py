from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from src.capability.artifact import CheckpointSpec
from src.surface.browser import BrowserSurface


@dataclass(frozen=True)
class CheckpointEvaluation:
    passed: bool
    observed_title: str
    missing_text: tuple[str, ...] = ()

    def observed_state(self) -> dict[str, object]:
        return {
            "page_title": self.observed_title,
            "missing_required_text": list(self.missing_text),
        }


def expected_state(checkpoint: CheckpointSpec) -> dict[str, object]:
    return {
        "page_title": checkpoint.page_title,
        "required_text": list(checkpoint.required_text),
    }


async def evaluate_checkpoint(
    surface: BrowserSurface,
    checkpoint: CheckpointSpec,
) -> CheckpointEvaluation:
    page = surface.page
    title = await page.title()
    body = await page.locator("body").inner_text()

    title_ok = (
        checkpoint.page_title is None
        or title == checkpoint.page_title
    )

    missing = tuple(
        text
        for text in checkpoint.required_text
        if text not in body
    )

    return CheckpointEvaluation(
        passed=title_ok and not missing,
        observed_title=title,
        missing_text=missing,
    )


async def wait_for_checkpoint(
    surface: BrowserSurface,
    checkpoint: CheckpointSpec,
    *,
    timeout_ms: int = 2500,
    poll_interval_ms: int = 100,
) -> CheckpointEvaluation:
    """Bounded polling for stable enterprise UI transitions.

    No model recovery occurs here. The expected checkpoint is fixed by the
    capability artifact; replay only waits a bounded amount of time for the
    deterministic state to appear.
    """

    if timeout_ms < 0:
        raise ValueError("timeout_ms must be non-negative")
    if poll_interval_ms <= 0:
        raise ValueError("poll_interval_ms must be positive")

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest = await evaluate_checkpoint(surface, checkpoint)

    while not latest.passed and time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        await asyncio.sleep(
            min(poll_interval_ms / 1000.0, max(0.0, remaining))
        )
        latest = await evaluate_checkpoint(surface, checkpoint)

    return latest
