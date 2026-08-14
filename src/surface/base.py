from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SurfaceSnapshot:
    """Minimal surface state used by the browser adapter in Stage 3.

    Stage 4 will build the richer structured UI observation model on top of
    this surface abstraction.
    """

    url: str
    title: str
    body_text: str


class ComputerSurface(ABC):
    """Surface-independent contract for computer-use execution.

    Higher layers should depend on this abstraction rather than directly on
    Playwright so browser, accessibility, or desktop adapters can share the
    same execution boundary.
    """

    @abstractmethod
    async def start(self) -> None:
        """Acquire the underlying live surface/session."""

    @abstractmethod
    async def close(self) -> None:
        """Release the underlying surface/session."""

    @abstractmethod
    async def navigate(self, target: str) -> None:
        """Navigate the live surface to a target entry point."""

    @abstractmethod
    async def observe(self) -> SurfaceSnapshot:
        """Return a minimal observation of the current surface state."""

    @abstractmethod
    async def click(self, selector: str) -> None:
        """Activate a control identified by a low-level selector."""

    @abstractmethod
    async def type(self, selector: str, value: str) -> None:
        """Replace the current value of an editable control."""

    @abstractmethod
    async def read(self, selector: str) -> str:
        """Read visible text from a control or region."""

    @abstractmethod
    async def wait(self, milliseconds: int) -> None:
        """Wait a bounded amount of time."""

    @abstractmethod
    async def screenshot(self, path: str | Path, *, full_page: bool = True) -> Path:
        """Capture the current live surface for evidence/debugging."""

    async def __aenter__(self) -> "ComputerSurface":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
