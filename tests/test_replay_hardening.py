from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

import pytest

from src.capability import (
    CapabilityArtifactV1,
    CapabilityIdentitySpec,
    CapabilityInputSpec,
    CapabilityOutputSpec,
    CapabilityStepSpec,
    CheckpointSpec,
    ParameterValue,
    TableCellExtractor,
    TargetApplicationSpec,
)
from src.models import ActionType, CapabilityValueType
from src.replay import (
    CapabilityValidationError,
    ReplayEngine,
    validate_capability_for_replay,
)
from src.replay.checkpoints import wait_for_checkpoint


class AllowPolicy:
    def evaluate(self, **kwargs):
        class Decision:
            allowed = True
            code = "allowed"
            reason = "test"
        return Decision()


def make_artifact(
    entry_point: str,
    *,
    version: str = "1.0.0",
) -> CapabilityArtifactV1:
    return CapabilityArtifactV1(
        capability=CapabilityIdentitySpec(
            id="member_savings_balance",
            name="Read Member Savings Balance",
            description="Hardening test",
            version=version,
        ),
        target=TargetApplicationSpec(
            application_family="test",
            entry_point=entry_point,
        ),
        inputs={
            "member_id": CapabilityInputSpec(
                type=CapabilityValueType.STRING,
                description="Member ID",
            )
        },
        outputs={
            "savings_balance": CapabilityOutputSpec(
                type=CapabilityValueType.STRING,
                description="Savings",
                extractor=TableCellExtractor(
                    row_text="Savings",
                    column_header="Balance",
                ),
            )
        },
        steps=[
            CapabilityStepSpec(
                id="step_1_type",
                action=ActionType.TYPE,
                target={
                    "description": "Member ID",
                    "candidates": [
                        {
                            "strategy": "structural",
                            "value": 'input[name="member_id"]',
                        }
                    ],
                },
                value=ParameterValue(
                    name="member_id"
                ),
                checkpoint=CheckpointSpec(
                    page_title="Hardening Test",
                ),
            ),
            CapabilityStepSpec(
                id="step_2_click",
                action=ActionType.CLICK,
                target={
                    "description": "Search",
                    "candidates": [
                        {
                            "strategy": "role_name",
                            "value": "button|Search",
                        }
                    ],
                },
                checkpoint=CheckpointSpec(
                    page_title="Member Details",
                    required_text=["Member Record"],
                ),
            ),
        ],
        success_checkpoint=CheckpointSpec(
            page_title="Member Details",
            required_text=["Member Record", "Savings"],
        ),
    )


def data_url(html: str) -> str:
    return (
        "data:text/html;charset=utf-8,"
        + quote(html)
    )


def test_capability_version_must_be_semver():
    artifact = make_artifact(
        "http://127.0.0.1:8000/",
        version="version-one",
    )

    with pytest.raises(
        CapabilityValidationError
    ):
        validate_capability_for_replay(
            artifact
        )


def test_required_string_input_cannot_be_empty(
    tmp_path: Path,
):
    html = """
    <html>
      <head><title>Hardening Test</title></head>
      <body>
        <input name="member_id">
        <button>Search</button>
      </body>
    </html>
    """

    async def scenario():
        engine = ReplayEngine(
            artifact=make_artifact(
                data_url(html)
            ),
            policy=AllowPolicy(),
            evidence_root=str(tmp_path),
            headless=True,
        )

        result = await engine.run(
            {"member_id": "   "}
        )
        assert result.status == "invalid_input"
        assert "must not be empty" in (
            result.message or ""
        )

    asyncio.run(scenario())


def test_unknown_runtime_input_is_rejected(
    tmp_path: Path,
):
    html = """
    <html>
      <head><title>Hardening Test</title></head>
      <body>
        <input name="member_id">
        <button>Search</button>
      </body>
    </html>
    """

    async def scenario():
        engine = ReplayEngine(
            artifact=make_artifact(
                data_url(html)
            ),
            policy=AllowPolicy(),
            evidence_root=str(tmp_path),
            headless=True,
        )

        result = await engine.run(
            {
                "member_id": "12345",
                "unexpected": "value",
            }
        )
        assert result.status == "invalid_input"
        assert "Unknown input" in (
            result.message or ""
        )

    asyncio.run(scenario())


def test_bounded_checkpoint_wait_handles_delayed_state(
    tmp_path: Path,
):
    html = """
    <html>
      <head><title>Loading</title></head>
      <body>
        <div id="state">Please wait</div>
        <script>
          setTimeout(() => {
            document.title = 'Member Details';
            document.getElementById('state').textContent =
              'Member Record Savings';
          }, 200);
        </script>
      </body>
    </html>
    """

    from src.surface import BrowserSurface

    async def scenario():
        async with BrowserSurface(
            headless=True
        ) as surface:
            await surface.navigate(
                data_url(html)
            )

            result = await wait_for_checkpoint(
                surface,
                CheckpointSpec(
                    page_title="Member Details",
                    required_text=[
                        "Member Record",
                        "Savings",
                    ],
                ),
                timeout_ms=1000,
            )

            assert result.passed is True

    asyncio.run(scenario())


def test_hard_failure_reports_step_expected_and_observed(
    tmp_path: Path,
):
    html = """
    <html>
      <head><title>Hardening Test</title></head>
      <body>
        <input name="member_id">
        <button>Search</button>
      </body>
    </html>
    """

    async def scenario():
        engine = ReplayEngine(
            artifact=make_artifact(
                data_url(html)
            ),
            policy=AllowPolicy(),
            evidence_root=str(tmp_path),
            headless=True,
            checkpoint_timeout_ms=0,
        )

        result = await engine.run(
            {"member_id": "77777"}
        )

        assert result.status == "failure"
        assert result.code == "checkpoint_failed"
        assert result.failed_step_id == "step_2_click"

        assert result.expected_state == {
            "page_title": "Member Details",
            "required_text": [
                "Member Record"
            ],
        }

        assert result.observed_state is not None
        assert (
            result.observed_state[
                "page_title"
            ]
            == "Hardening Test"
        )
        assert "Member Record" in (
            result.observed_state[
                "missing_required_text"
            ]
        )

    asyncio.run(scenario())
