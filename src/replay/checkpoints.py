
from __future__ import annotations
from dataclasses import dataclass
from src.capability.artifact import CheckpointSpec
from src.surface.browser import BrowserSurface

@dataclass(frozen=True)
class CheckpointEvaluation:
    passed: bool
    observed_title: str
    missing_text: tuple[str, ...] = ()

async def evaluate_checkpoint(surface: BrowserSurface, checkpoint: CheckpointSpec) -> CheckpointEvaluation:
    page = surface.page
    title = await page.title()
    body = await page.locator("body").inner_text()
    title_ok = checkpoint.page_title is None or title == checkpoint.page_title
    missing = tuple(text for text in checkpoint.required_text if text not in body)
    return CheckpointEvaluation(title_ok and not missing, title, missing)
