from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import quote

from src.agent.discovery import DiscoveryRunner
from src.agent.models import DiscoveryDecision, DiscoveryOutput
from src.agent.provider import DecisionProvider
from src.models import ActionType


HTML = """
<!doctype html>
<html>
  <head><title>Discovery Test</title></head>
  <body>
    <table>
      <tr>
        <td>Member ID</td>
        <td><input name="member_id" type="text"></td>
        <td>
          <button type="button" onclick="
            const id = document.querySelector('input[name=member_id]').value;
            document.getElementById('result').textContent =
              id === '12345'
                ? 'Savings Balance $4,821.37'
                : 'No member found';
          ">Search</button>
        </td>
      </tr>
    </table>
    <div id="result"></div>
  </body>
</html>
"""


def data_url() -> str:
    return "data:text/html;charset=utf-8," + quote(HTML)


class AllowPolicy:
    def evaluate(self, *, action, target_url, risk):
        class Decision:
            allowed = True
            code = "allowed"
            reason = "test policy"

        return Decision()


class ScriptedProvider(DecisionProvider):
    async def decide(
        self,
        *,
        goal,
        observation,
        step_number,
        history,
    ):
        if step_number == 1:
            return DiscoveryDecision(
                action=ActionType.TYPE,
                control_index=0,
                value="12345",
                reason="Enter the requested member ID.",
            )
        if step_number == 2:
            return DiscoveryDecision(
                action=ActionType.CLICK,
                control_index=1,
                reason="Submit the member search.",
            )
        return DiscoveryDecision(
            action=ActionType.FINISH,
            reason="The savings balance is visible.",
            result=[
                DiscoveryOutput(
                    name="savings_balance",
                    value="$4,821.37",
                )
            ],
        )


def test_discovery_loop_executes_observe_decide_policy_act_until_success(
    tmp_path: Path,
):
    async def scenario():
        runner = DiscoveryRunner(
            provider=ScriptedProvider(),
            policy=AllowPolicy(),
            evidence_root=str(tmp_path),
            headless=True,
        )

        result = await runner.run(
            goal="Look up member 12345 and return the savings balance",
            target=data_url(),
            max_steps=5,
            timeout_seconds=30,
        )

        assert result.status == "success"
        assert result.outputs["savings_balance"] == "$4,821.37"
        assert [step.decision.action for step in result.steps] == [
            ActionType.TYPE,
            ActionType.CLICK,
            ActionType.FINISH,
        ]

        events = Path(tmp_path, result.run_id, "events.jsonl")
        saved_result = Path(tmp_path, result.run_id, "result.json")
        assert events.exists()
        assert saved_result.exists()

    asyncio.run(scenario())


class InvalidControlProvider(DecisionProvider):
    async def decide(self, **kwargs):
        return DiscoveryDecision(
            action=ActionType.CLICK,
            control_index=99,
            reason="Select a control that does not exist.",
        )


def test_discovery_loop_stops_on_invalid_model_control(tmp_path: Path):
    async def scenario():
        runner = DiscoveryRunner(
            provider=InvalidControlProvider(),
            policy=AllowPolicy(),
            evidence_root=str(tmp_path),
            headless=True,
        )

        result = await runner.run(
            goal="Do something",
            target=data_url(),
            max_steps=2,
            timeout_seconds=30,
        )

        assert result.status == "dead_end"
        run_dir = Path(tmp_path, result.run_id)
        assert any(path.suffix == ".png" for path in run_dir.iterdir())

    asyncio.run(scenario())


class HumanProvider(DecisionProvider):
    async def decide(self, **kwargs):
        return DiscoveryDecision(
            action=ActionType.REQUEST_HUMAN,
            reason="Unsafe or ambiguous state requires a person.",
        )


def test_discovery_loop_can_escalate_to_human_required(tmp_path: Path):
    async def scenario():
        runner = DiscoveryRunner(
            provider=HumanProvider(),
            policy=AllowPolicy(),
            evidence_root=str(tmp_path),
            headless=True,
        )

        result = await runner.run(
            goal="Do something",
            target=data_url(),
            max_steps=2,
            timeout_seconds=30,
        )

        assert result.status == "human_required"

    asyncio.run(scenario())
