\
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.models import RunMode
from src.policy.redaction import redact


class RunRecorder:
    """Append-only JSONL recorder for discovery/replay/handoff evidence."""

    def __init__(
        self,
        *,
        evidence_root: str | Path,
        mode: RunMode,
        run_id: str | None = None,
    ) -> None:
        self.run_id = run_id or f"run_{uuid4().hex[:12]}"
        self.mode = mode
        self.run_dir = Path(evidence_root) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"

    def record(
        self,
        event: str,
        *,
        step_id: str | None = None,
        action: str | None = None,
        target: Any | None = None,
        reason: str | None = None,
        result: Any | None = None,
        details: Any | None = None,
        actor: str = "automation",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode.value,
            "actor": actor,
            "event": event,
        }

        optional = {
            "step_id": step_id,
            "action": action,
            "target": target,
            "reason": reason,
            "result": result,
            "details": details,
        }
        payload.update(
            {
                key: value
                for key, value in optional.items()
                if value is not None
            }
        )

        safe_payload = redact(payload)

        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe_payload, sort_keys=True) + "\n")

        return safe_payload

    def write_result(self, result: Any) -> Path:
        path = self.run_dir / "result.json"
        path.write_text(
            json.dumps(redact(result), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
