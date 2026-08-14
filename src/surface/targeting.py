from __future__ import annotations

from playwright.async_api import Locator, Page

from src.models import LocatorCandidate, TargetLocator


def locator_from_candidate(page: Page, candidate: LocatorCandidate) -> Locator:
    strategy = candidate.strategy
    value = candidate.value

    if strategy == "role_name":
        role, name = value.split("|", 1)
        return page.get_by_role(role, name=name, exact=True)

    if strategy == "label_text":
        return page.get_by_label(value, exact=True)

    if strategy == "visible_text":
        return page.get_by_text(value, exact=True)

    if strategy == "structural":
        return page.locator(value)

    if strategy == "css":
        return page.locator(value)

    if strategy == "xpath":
        return page.locator(f"xpath={value}")

    raise ValueError(f"Unsupported locator strategy: {strategy}")


async def first_matching_locator(
    page: Page,
    target: TargetLocator,
) -> tuple[Locator, LocatorCandidate]:
    """Resolve recorded candidates in a fixed deterministic order."""

    for candidate in target.candidates:
        locator = locator_from_candidate(page, candidate)
        if await locator.count() == 1 and await locator.is_visible():
            return locator, candidate

    raise LookupError(f"No unique visible match for target: {target.description}")
