from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

import pytest

from src.surface import BrowserSurface


HTML = """
<!doctype html>
<html>
  <head><title>Surface Test</title></head>
  <body>
    <label>Member ID <input id="member-id"></label>
    <button id="search" onclick="
      document.getElementById('result').textContent =
        'Member ' + document.getElementById('member-id').value;
    ">Search</button>
    <div id="result">Ready</div>
  </body>
</html>
"""


def data_url() -> str:
    return "data:text/html;charset=utf-8," + quote(HTML)


def test_browser_surface_requires_start_before_page_access():
    surface = BrowserSurface()
    with pytest.raises(RuntimeError):
        _ = surface.page


def test_browser_surface_can_navigate_observe_type_click_read_and_capture(tmp_path: Path):
    async def scenario():
        async with BrowserSurface(headless=True) as surface:
            await surface.navigate(data_url())

            initial = await surface.observe()
            assert initial.title == "Surface Test"
            assert "Member ID" in initial.body_text
            assert "Ready" in initial.body_text

            await surface.type("#member-id", "12345")
            await surface.click("#search")
            assert await surface.read("#result") == "Member 12345"

            await surface.wait(10)

            image_path = await surface.screenshot(tmp_path / "surface.png")
            assert image_path.exists()
            assert image_path.stat().st_size > 0

    asyncio.run(scenario())


def test_browser_surface_close_is_idempotent():
    async def scenario():
        surface = BrowserSurface(headless=True)
        await surface.start()
        assert surface.is_started is True

        await surface.close()
        assert surface.is_started is False

        await surface.close()
        assert surface.is_started is False

    asyncio.run(scenario())


def test_browser_surface_rejects_negative_wait():
    async def scenario():
        async with BrowserSurface(headless=True) as surface:
            with pytest.raises(ValueError):
                await surface.wait(-1)

    asyncio.run(scenario())
