from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.models import RunMode
from src.observability import EvidenceManager, RunRecorder


class FakeScreenshotSurface:
    async def screenshot(
        self,
        path: str | Path,
        *,
        full_page: bool = True,
    ) -> Path:
        output = Path(path)
        output.write_bytes(b"fake-png")
        return output


def test_run_recorder_writes_structured_redacted_jsonl(tmp_path: Path):
    recorder = RunRecorder(
        evidence_root=tmp_path,
        mode=RunMode.DISCOVERY,
        run_id="run_test",
    )

    event = recorder.record(
        "action_proposed",
        step_id="step_1",
        action="type",
        target={"description": "Member ID"},
        reason="Enter requested member",
        details={
            "email": "person@example.com",
            "token": "secret-token",
        },
    )

    assert event["run_id"] == "run_test"
    assert event["mode"] == "discovery"
    assert event["actor"] == "automation"
    assert event["details"]["email"] == "[EMAIL_REDACTED]"
    assert event["details"]["token"] == "[REDACTED]"

    lines = recorder.events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    persisted = json.loads(lines[0])
    assert persisted["event"] == "action_proposed"
    assert persisted["details"]["token"] == "[REDACTED]"


def test_result_file_is_redacted(tmp_path: Path):
    recorder = RunRecorder(
        evidence_root=tmp_path,
        mode=RunMode.REPLAY,
        run_id="run_result",
    )

    path = recorder.write_result(
        {
            "status": "failure",
            "authorization": "Bearer secret",
            "detail": "user person@example.com",
        }
    )

    content = path.read_text(encoding="utf-8")
    assert "Bearer secret" not in content
    assert "person@example.com" not in content


def test_failure_screenshot_is_written_inside_run_directory(tmp_path: Path):
    async def scenario():
        recorder = RunRecorder(
            evidence_root=tmp_path,
            mode=RunMode.REPLAY,
            run_id="run_failure",
        )
        evidence = EvidenceManager(recorder.run_dir)
        surface = FakeScreenshotSurface()

        path = await evidence.capture_failure_screenshot(
            surface,
            step_id="open/member details",
        )

        assert path.parent == recorder.run_dir
        assert path.name == "failure_open_member_details.png"
        assert path.exists()

    asyncio.run(scenario())
