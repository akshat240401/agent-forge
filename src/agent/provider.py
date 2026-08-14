from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from src.agent.models import DiscoveryDecision
from src.surface.observation import StructuredObservation


SYSTEM_PROMPT = """You are the discovery planner for a computer-use automation system.

Your job is to accomplish the user's goal by choosing exactly one next action from the
currently observed UI.

Rules:
- You may only choose controls that appear in the supplied observation.
- Use control_index to refer to a control. Never invent selectors.
- Prefer the smallest safe next step.
- Use TYPE to enter a requested value into a textbox.
- Use CLICK to activate a visible control.
- Use READ only when a control's text/value must be explicitly read.
- Use WAIT only for a transient state that may resolve shortly.
- Use FINISH only when the goal is actually satisfied and verified in the current observation.
- For FINISH, return result as a list of name/value entries, for example:
  [{"name":"savings_balance","value":"$4,821.37"}].
- Use REQUEST_HUMAN when proceeding is unsafe or the UI cannot be handled safely.
- Do not claim success based on an expected result; verify the current observation first.
- Do not include secrets or unnecessary personal data in result or reason.
"""


class DecisionProvider(ABC):
    @abstractmethod
    async def decide(
        self,
        *,
        goal: str,
        observation: StructuredObservation,
        step_number: int,
        history: list[dict[str, Any]],
    ) -> DiscoveryDecision:
        raise NotImplementedError


def compact_observation(
    observation: StructuredObservation,
) -> dict[str, Any]:
    return {
        "url": observation.url,
        "title": observation.title,
        "visible_text": observation.visible_text,
        "controls": [
            {
                "index": control.index,
                "role": control.role,
                "name": control.name,
                "name_source": control.name_source,
                "text": control.text,
                "value": control.value,
                "disabled": control.disabled,
            }
            for control in observation.controls
        ],
    }


class OpenAIDecisionProvider(DecisionProvider):
    """OpenAI Responses API adapter using Pydantic Structured Outputs."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key)

    async def decide(
        self,
        *,
        goal: str,
        observation: StructuredObservation,
        step_number: int,
        history: list[dict[str, Any]],
    ) -> DiscoveryDecision:
        payload = {
            "goal": goal,
            "step_number": step_number,
            "observation": compact_observation(observation),
            "recent_history": history[-6:],
        }

        response = await self.client.responses.parse(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=json.dumps(payload, ensure_ascii=False),
            text_format=DiscoveryDecision,
            store=False,
        )

        if response.output_parsed is None:
            raise RuntimeError(
                "Model returned no parsed DiscoveryDecision."
            )

        return response.output_parsed
