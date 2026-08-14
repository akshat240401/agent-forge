# AgentForge

LLM-discovered, deterministic computer-use automation.

AgentForge is a computer-use automation system in which an LLM discovers how to complete a task against a real UI, compiles the successful run into a typed reusable capability, and replays that capability deterministically without a model in the decision loop.

Stage 1 foundation.

Current scope:
- repository structure
- typed core models
- capability artifact contract
- replay result taxonomy
- human-handoff models
- policy models
- schema tests

Later stages will add the local legacy banking UI, surface abstraction, LLM discovery,
deterministic replay, safety enforcement, observability, and same-session human handoff.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```
