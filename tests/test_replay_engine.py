
from __future__ import annotations
import asyncio
from pathlib import Path
from urllib.parse import quote
from src.capability import (
    CapabilityArtifactV1, CapabilityIdentitySpec, CapabilityInputSpec,
    CapabilityOutputSpec, CapabilityStepSpec, CheckpointSpec, ParameterValue,
    TableCellExtractor, TargetApplicationSpec,
)
from src.models import ActionType, CapabilityValueType
from src.replay import ReplayEngine

def artifact(entry):
    return CapabilityArtifactV1(
        capability=CapabilityIdentitySpec(id="member_savings_balance",name="Read Member Savings Balance",
            description="Test",version="1.0.0"),
        target=TargetApplicationSpec(application_family="test",entry_point=entry),
        inputs={"member_id":CapabilityInputSpec(type=CapabilityValueType.STRING,description="Member ID")},
        outputs={"savings_balance":CapabilityOutputSpec(type=CapabilityValueType.STRING,description="Savings",
            extractor=TableCellExtractor(row_text="Savings",column_header="Balance"))},
        steps=[
            CapabilityStepSpec(id="step_1_type",action=ActionType.TYPE,
                target={"description":"Member ID","candidates":[{"strategy":"structural","value":'input[name="member_id"]'}]},
                value=ParameterValue(name="member_id"),checkpoint=CheckpointSpec(page_title="Replay Test")),
            CapabilityStepSpec(id="step_2_click",action=ActionType.CLICK,
                target={"description":"Search","candidates":[{"strategy":"role_name","value":"button|Search"}]},
                checkpoint=CheckpointSpec(page_title="Replay Test",required_text=["Savings"])),
        ],
        success_checkpoint=CheckpointSpec(page_title="Replay Test",required_text=["Savings"]),
    )

def html_url():
    html = """<!doctype html><html><head><title>Replay Test</title></head><body>
    <input name="member_id"><button onclick="document.getElementById('a').innerHTML=
    '<table><tr><th>Type</th><th>Balance</th></tr><tr><td>Savings</td><td>$2,614.09</td></tr></table>'">Search</button>
    <div id="a"></div></body></html>"""
    return "data:text/html;charset=utf-8," + quote(html)

class AllowPolicy:
    def evaluate(self, **kwargs):
        class D:
            allowed=True; code="allowed"; reason="test"
        return D()

def test_replay_executes_parameterized_artifact_without_model(tmp_path: Path):
    async def scenario():
        result = await ReplayEngine(artifact=artifact(html_url()),policy=AllowPolicy(),
            evidence_root=str(tmp_path),headless=True).run({"member_id":"67890"})
        assert result.status == "success"
        assert result.outputs["savings_balance"] == "$2,614.09"
        assert len(result.steps) == 2
    asyncio.run(scenario())

def test_replay_rejects_missing_input(tmp_path: Path):
    async def scenario():
        result = await ReplayEngine(artifact=artifact(html_url()),policy=AllowPolicy(),
            evidence_root=str(tmp_path),headless=True).run({})
        assert result.status == "invalid_input"
    asyncio.run(scenario())
