from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from src.models import LocatorCandidate, TargetLocator
from src.surface.browser import BrowserSurface


class StrictSurfaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObservedControl(StrictSurfaceModel):
    index: int = Field(ge=0)
    tag: str
    role: str | None = None
    name: str | None = None
    name_source: str | None = None
    text: str | None = None
    input_type: str | None = None
    value: str | None = None
    disabled: bool = False
    target: TargetLocator


class StructuredObservation(StrictSurfaceModel):
    url: str
    title: str
    visible_text: list[str] = Field(default_factory=list)
    controls: list[ObservedControl] = Field(default_factory=list)


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(value.split())
    return cleaned or None


def _infer_role(
    tag: str,
    input_type: str | None,
    explicit_role: str | None,
) -> str | None:
    if explicit_role:
        return explicit_role

    tag = tag.lower()
    input_type = (input_type or "").lower()

    if tag == "button":
        return "button"

    if tag == "a":
        return "link"

    if tag == "textarea":
        return "textbox"

    if tag == "select":
        return "combobox"

    if tag == "input":
        if input_type in {"button", "submit", "reset"}:
            return "button"

        if input_type == "checkbox":
            return "checkbox"

        if input_type == "radio":
            return "radio"

        if input_type != "hidden":
            return "textbox"

    return None


def _xpath_literal(value: str) -> str:
    """Return a safe XPath string literal."""
    if "'" not in value:
        return f"'{value}'"

    if '"' not in value:
        return f'"{value}"'

    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"


def build_target_locator(
    *,
    role: str | None,
    name: str | None,
    name_source: str | None,
    text: str | None,
    tag: str,
    input_name: str | None,
) -> TargetLocator:
    candidates: list[LocatorCandidate] = []

    # Only use accessibility/label locators when the underlying page
    # genuinely exposes those semantics.
    if name_source in {
        "aria_label",
        "associated_label",
        "title",
        "placeholder",
        "control_text",
    }:
        if role and name:
            candidates.append(
                LocatorCandidate(
                    strategy="role_name",
                    value=f"{role}|{name}",
                )
            )

        if name_source == "associated_label" and name:
            candidates.append(
                LocatorCandidate(
                    strategy="label_text",
                    value=name,
                )
            )

        if text and role in {"button", "link"}:
            candidates.append(
                LocatorCandidate(
                    strategy="visible_text",
                    value=text,
                )
            )

    # Legacy enterprise forms frequently identify inputs using adjacent
    # table cells rather than semantic HTML labels.
    if name_source == "nearby_table_cell" and name:
        label_literal = _xpath_literal(name)

        candidates.append(
            LocatorCandidate(
                strategy="xpath",
                value=(
                    f"//td[normalize-space(.)={label_literal}]"
                    f"/following-sibling::td[1]//{tag}"
                ),
            )
        )

    # Stable structural information remains a deterministic fallback.
    if input_name:
        candidates.append(
            LocatorCandidate(
                strategy="structural",
                value=f'{tag}[name="{input_name}"]',
            )
        )

    if not candidates:
        candidates.append(
            LocatorCandidate(
                strategy="structural",
                value=tag,
            )
        )

    description_parts = [part for part in [role, name] if part]
    description = " / ".join(description_parts) or tag

    return TargetLocator(
        description=description,
        candidates=candidates,
    )


class BrowserObserver:
    """Extract a compact representation of the current browser UI."""

    CONTROL_SELECTOR = (
        'button, a[href], input:not([type="hidden"]), textarea, select, '
        '[role="button"], [role="link"], [role="textbox"], [role="combobox"]'
    )

    async def observe(
        self,
        surface: BrowserSurface,
    ) -> StructuredObservation:
        page = surface.page

        visible_text_raw = await page.locator("body").inner_text()

        visible_text = [
            " ".join(fragment.split())
            for fragment in re.split(r"[\r\n\t]+", visible_text_raw)
            if fragment.strip()
        ]

        locator = page.locator(self.CONTROL_SELECTOR)
        count = await locator.count()

        controls: list[ObservedControl] = []

        for index in range(count):
            element = locator.nth(index)

            if not await element.is_visible():
                continue

            metadata = await element.evaluate(
                """
                (el) => {
                  const tag = el.tagName.toLowerCase();
                  const explicitRole = el.getAttribute('role');
                  const inputType = el.getAttribute('type');
                  const inputName = el.getAttribute('name');

                  let associatedLabel = null;

                  if (el.labels && el.labels.length > 0) {
                    associatedLabel = Array.from(el.labels)
                      .map(
                        label =>
                          label.innerText ||
                          label.textContent ||
                          ''
                      )
                      .join(' ');
                  }

                  const ariaLabel = el.getAttribute('aria-label');
                  const title = el.getAttribute('title');
                  const placeholder = el.getAttribute('placeholder');

                  let nearbyTableLabel = null;

                  const owningCell = el.closest('td, th');

                  if (
                    owningCell &&
                    owningCell.previousElementSibling
                  ) {
                    nearbyTableLabel =
                      owningCell.previousElementSibling.innerText ||
                      owningCell.previousElementSibling.textContent ||
                      null;
                  }

                  let text = '';

                  if (tag === 'input') {
                    text = el.value || '';
                  } else {
                    text =
                      el.innerText ||
                      el.textContent ||
                      '';
                  }

                  let name = null;
                  let nameSource = null;

                  if (ariaLabel) {
                    name = ariaLabel;
                    nameSource = 'aria_label';
                  } else if (associatedLabel) {
                    name = associatedLabel;
                    nameSource = 'associated_label';
                  } else if (title) {
                    name = title;
                    nameSource = 'title';
                  } else if (placeholder) {
                    name = placeholder;
                    nameSource = 'placeholder';
                  } else if (nearbyTableLabel) {
                    name = nearbyTableLabel;
                    nameSource = 'nearby_table_cell';
                  } else if (
                    tag === 'button' ||
                    tag === 'a'
                  ) {
                    name = text;
                    nameSource = 'control_text';
                  }

                  return {
                    tag,
                    explicitRole,
                    inputType,
                    inputName,
                    name,
                    nameSource,
                    text,
                    value:
                      'value' in el
                        ? el.value
                        : null,
                    disabled: Boolean(el.disabled)
                  };
                }
                """
            )

            role = _infer_role(
                metadata["tag"],
                metadata["inputType"],
                metadata["explicitRole"],
            )

            name = _normalized_text(metadata["name"])
            name_source = _normalized_text(metadata["nameSource"])
            text = _normalized_text(metadata["text"])
            input_name = _normalized_text(metadata["inputName"])

            # Typed textbox content is runtime state, not control identity.
            locator_text = None if role == "textbox" else text

            target = build_target_locator(
                role=role,
                name=name,
                name_source=name_source,
                text=locator_text,
                tag=metadata["tag"],
                input_name=input_name,
            )

            controls.append(
                ObservedControl(
                    index=len(controls),
                    tag=metadata["tag"],
                    role=role,
                    name=name,
                    name_source=name_source,
                    text=text,
                    input_type=_normalized_text(
                        metadata["inputType"]
                    ),
                    value=_normalized_text(
                        metadata["value"]
                    ),
                    disabled=metadata["disabled"],
                    target=target,
                )
            )

        return StructuredObservation(
            url=page.url,
            title=await page.title(),
            visible_text=visible_text,
            controls=controls,
        )
