from __future__ import annotations

import asyncio
from pathlib import Path

from src.handoff import TerminalHandoffManager
from src.models import RunMode
from src.observability import EvidenceManager, RunRecorder
from src.surface import BrowserSurface


def test_handoff_records_human_action_and_returns_control(tmp_path: Path):
    async def scenario():
        recorder = RunRecorder(
            evidence_root=tmp_path,
            mode=RunMode.REPLAY,
            run_id="run_handoff",
        )
        evidence = EvidenceManager(recorder.run_dir)

        async with BrowserSurface(headless=True) as surface:
            await surface.navigate("http://127.0.0.1:8000/")

            def fake_input(_prompt: str) -> str:
                import time
                time.sleep(0.5)
                return ""

            manager = TerminalHandoffManager(
                recorder=recorder,
                evidence=evidence,
                input_func=fake_input,
            )

            task = asyncio.create_task(
                manager.intervene(
                    surface=surface,
                    capability_id="member_savings_balance",
                    capability_version="1.0.0",
                    current_step="test_handoff",
                    reason="Test human intervention",
                )
            )

            await asyncio.sleep(0.2)

            await surface.page.evaluate("""
                () => {
                    const button = document.createElement('button');
                    button.id = 'continue-test';
                    button.textContent = 'Continue Session';
                    document.body.appendChild(button);
                }
            """)

            await surface.page.locator("#continue-test").click()

            result = await task

            assert result.resumed is True
            assert result.intervention.control_owner == "human"
            assert len(result.human_actions) >= 1

            assert any(
                action.event == "click"
                and action.text == "Continue Session"
                for action in result.human_actions
            )

        events = recorder.events_path.read_text(encoding="utf-8")

        assert '"event": "human_action"' in events
        assert '"human_action_count": 1' in events

    asyncio.run(scenario())
