
from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import uuid4

from src.handoff.models import HandoffResult, HumanAction, InterventionRequest
from src.observability import EvidenceManager, RunRecorder
from src.surface.browser import BrowserSurface


_HUMAN_RECORDING_SCRIPT = r"""
(() => {
  const STORAGE_KEY = '__agentforgeHumanActions';

  const load = () => {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
    } catch (_) {
      return [];
    }
  };

  const save = actions => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(actions));
  };

  if (sessionStorage.getItem(STORAGE_KEY) === null) {
    save([]);
  }

  if (window.__agentforgeHumanRecorderInstalled) {
    return;
  }
  window.__agentforgeHumanRecorderInstalled = true;

  const summarize = (el, eventType) => {
    const tag = (el.tagName || '').toLowerCase();
    const name =
      el.getAttribute?.('aria-label') ||
      el.getAttribute?.('name') ||
      el.innerText ||
      el.textContent ||
      null;

    const inputType = el.getAttribute?.('type') || null;
    let value = null;

    if ('value' in el && eventType !== 'click') {
      value = el.value;
    }

    const actions = load();
    actions.push({
      event: eventType,
      tag,
      text: (el.innerText || el.textContent || '').trim() || null,
      name: name ? String(name).trim() : null,
      input_type: inputType,
      value
    });
    save(actions);
  };

  document.addEventListener(
    'click',
    event => summarize(event.target, 'click'),
    true
  );
  document.addEventListener(
    'input',
    event => summarize(event.target, 'input'),
    true
  );
  document.addEventListener(
    'change',
    event => summarize(event.target, 'change'),
    true
  );
})();
"""


_READ_ACTIONS_SCRIPT = r"""
() => {
  try {
    return JSON.parse(
      sessionStorage.getItem('__agentforgeHumanActions') || '[]'
    );
  } catch (_) {
    return [];
  }
}
"""


class TerminalHandoffManager:
    def __init__(
        self,
        *,
        recorder: RunRecorder,
        evidence: EvidenceManager,
        input_func: Callable[[str], str] = input,
    ) -> None:
        self.recorder = recorder
        self.evidence = evidence
        self.input_func = input_func

    async def intervene(
        self,
        *,
        surface: BrowserSurface,
        capability_id: str,
        capability_version: str,
        current_step: str,
        reason: str,
    ) -> HandoffResult:
        screenshot = await self.evidence.capture_failure_screenshot(
            surface,
            step_id=f"{current_step}_intervention",
        )

        intervention = InterventionRequest(
            intervention_id=f"int_{uuid4().hex[:12]}",
            run_id=self.recorder.run_id,
            capability_id=capability_id,
            capability_version=capability_version,
            current_step=current_step,
            reason=reason,
            screenshot=str(screenshot),
        )

        self.recorder.record(
            "intervention_requested",
            step_id=current_step,
            actor="automation",
            reason=reason,
            details=intervention.model_dump(mode="json"),
        )
        self.recorder.record(
            "control_transferred",
            step_id=current_step,
            actor="human",
            details={
                "control_owner": "human",
                "intervention_id": intervention.intervention_id,
            },
        )

        await surface.page.context.add_init_script(_HUMAN_RECORDING_SCRIPT)
        await surface.page.evaluate(_HUMAN_RECORDING_SCRIPT)

        print("")
        print("=" * 72)
        print("INTERVENTION REQUIRED")
        print("=" * 72)
        print(f"Run ID:      {intervention.run_id}")
        print(f"Capability:  {intervention.capability_id}")
        print(f"Step:        {intervention.current_step}")
        print(f"Reason:      {intervention.reason}")
        print(f"Screenshot:  {intervention.screenshot}")
        print("Owner:       HUMAN")
        print("")
        print("Operate the SAME Chromium window manually.")
        print("When the UI is in the correct state, return here and press Enter.")
        print("=" * 72)

        await asyncio.to_thread(
            self.input_func,
            "Press Enter to return control to automation... ",
        )

        raw_actions = await surface.page.evaluate(_READ_ACTIONS_SCRIPT)
        actions = [
            HumanAction.model_validate(action)
            for action in raw_actions
        ]

        for action in actions:
            self.recorder.record(
                "human_action",
                step_id=current_step,
                actor="human",
                action=action.event,
                target={
                    "tag": action.tag,
                    "name": action.name,
                    "text": action.text,
                },
                details={
                    "input_type": action.input_type,
                    "value": action.value,
                },
            )

        self.recorder.record(
            "control_returned",
            step_id=current_step,
            actor="automation",
            details={
                "control_owner": "automation",
                "intervention_id": intervention.intervention_id,
                "human_action_count": len(actions),
            },
        )

        return HandoffResult(
            resumed=True,
            intervention=intervention,
            human_actions=actions,
        )
