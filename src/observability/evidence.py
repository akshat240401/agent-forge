\
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ScreenshotSurface(Protocol):
    async def screenshot(
        self,
        path: str | Path,
        *,
        full_page: bool = True,
    ) -> Path:
        ...


class EvidenceManager:
    """Create richer evidence associated with a RunRecorder directory."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    async def capture_failure_screenshot(
        self,
        surface: ScreenshotSurface,
        *,
        step_id: str,
    ) -> Path:
        safe_step = "".join(
            character
            if character.isalnum() or character in {"-", "_"}
            else "_"
            for character in step_id
        )
        path = self.run_dir / f"failure_{safe_step}.png"
        return await surface.screenshot(path, full_page=True)
