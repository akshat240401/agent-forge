from __future__ import annotations

from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from src.surface.base import ComputerSurface, SurfaceSnapshot


class BrowserSurface(ComputerSurface):
    """Playwright-backed implementation of the computer surface seam."""

    def __init__(
        self,
        *,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        action_timeout_ms: int = 10_000,
    ) -> None:
        self._headless = headless
        self._viewport_width = viewport_width
        self._viewport_height = viewport_height
        self._action_timeout_ms = action_timeout_ms

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        """Expose the live page only for explicit low-level integration needs.

        Agent/replay layers should prefer the ComputerSurface methods.
        """
        if self._page is None:
            raise RuntimeError("BrowserSurface has not been started.")
        return self._page

    @property
    def is_started(self) -> bool:
        return self._page is not None

    async def start(self) -> None:
        if self.is_started:
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": self._viewport_width,
                "height": self._viewport_height,
            }
        )
        self._context.set_default_timeout(self._action_timeout_ms)
        self._page = await self._context.new_page()

    async def close(self) -> None:
        # Keep cleanup idempotent so error paths can safely call close().
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def navigate(self, target: str) -> None:
        await self.page.goto(target, wait_until="domcontentloaded")

    async def observe(self) -> SurfaceSnapshot:
        page = self.page
        body_text = await page.locator("body").inner_text()
        return SurfaceSnapshot(
            url=page.url,
            title=await page.title(),
            body_text=body_text,
        )

    async def click(self, selector: str) -> None:
        await self.page.locator(selector).click()

    async def type(self, selector: str, value: str) -> None:
        # fill() is intentionally used instead of press-by-press typing:
        # this low-level primitive means "set this editable value".
        await self.page.locator(selector).fill(value)

    async def read(self, selector: str) -> str:
        return await self.page.locator(selector).inner_text()

    async def wait(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("milliseconds must be non-negative")
        await self.page.wait_for_timeout(milliseconds)

    async def screenshot(self, path: str | Path, *, full_page: bool = True) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(output_path), full_page=full_page)
        return output_path
