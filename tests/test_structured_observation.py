from __future__ import annotations

import asyncio
from urllib.parse import quote

from src.surface import BrowserObserver, BrowserSurface, first_matching_locator


HTML = """
<!doctype html>
<html>
  <head><title>Legacy Observation Test</title></head>
  <body>
    <table>
      <tr>
        <td><label for="member">Member ID</label></td>
        <td><input id="member" name="member_id" type="text"></td>
        <td><button type="button">Search</button></td>
      </tr>
    </table>
    <a href="/help">Help</a>
  </body>
</html>
"""


def data_url() -> str:
    return "data:text/html;charset=utf-8," + quote(HTML)


def test_structured_observation_extracts_visible_controls_and_text():
    async def scenario():
        observer = BrowserObserver()
        async with BrowserSurface(headless=True) as surface:
            await surface.navigate(data_url())
            observation = await observer.observe(surface)

            assert observation.title == "Legacy Observation Test"
            assert "Member ID" in observation.visible_text
            assert len(observation.controls) == 3

            textbox = next(c for c in observation.controls if c.role == "textbox")
            assert textbox.name == "Member ID"
            assert textbox.target.candidates[0].strategy == "role_name"
            assert textbox.target.candidates[0].value == "textbox|Member ID"

            button = next(c for c in observation.controls if c.role == "button")
            assert button.name == "Search"
            assert button.target.candidates[0].value == "button|Search"

            link = next(c for c in observation.controls if c.role == "link")
            assert link.name == "Help"

    asyncio.run(scenario())


def test_target_candidates_are_semantic_first_structural_last():
    async def scenario():
        observer = BrowserObserver()
        async with BrowserSurface(headless=True) as surface:
            await surface.navigate(data_url())
            observation = await observer.observe(surface)

            textbox = next(c for c in observation.controls if c.role == "textbox")
            strategies = [c.strategy for c in textbox.target.candidates]

            assert strategies[0] == "role_name"
            assert "label_text" in strategies
            assert strategies[-1] == "structural"

    asyncio.run(scenario())


def test_recorded_target_resolves_without_model_reasoning():
    async def scenario():
        observer = BrowserObserver()
        async with BrowserSurface(headless=True) as surface:
            await surface.navigate(data_url())
            observation = await observer.observe(surface)

            textbox = next(c for c in observation.controls if c.role == "textbox")
            locator, candidate = await first_matching_locator(surface.page, textbox.target)

            assert candidate.strategy == "role_name"
            await locator.fill("12345")
            assert await locator.input_value() == "12345"

    asyncio.run(scenario())


def test_typed_value_does_not_become_textbox_identity():
    async def scenario():
        observer = BrowserObserver()
        async with BrowserSurface(headless=True) as surface:
            await surface.navigate(data_url())
            await surface.page.get_by_label("Member ID").fill("12345")
            observation = await observer.observe(surface)

            textbox = next(c for c in observation.controls if c.role == "textbox")
            assert textbox.value == "12345"
            assert all(c.value != "12345" for c in textbox.target.candidates)

    asyncio.run(scenario())
