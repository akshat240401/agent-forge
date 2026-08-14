# AgentForge

Stage 1 foundation for the interface.ai take-home assignment.

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

## Local legacy banking target

Stage 2 adds a synthetic, legacy-style member-servicing UI used as the real surface for
later discovery and replay stages.

Start it with:

```bash
python -m src.mock_bank
```

Then open `http://127.0.0.1:8000`.

Synthetic demo states:

- `12345` — successful member lookup
- `67890` — second successful member used later for parameterized replay
- `99999` — expected `member_not_found` business outcome
- `55555` — bounded delay followed by a known session-confirmation interstitial
- `77777` — permission-denied hard-failure surface

All names, IDs, account numbers, and balances are synthetic.

## Browser surface

Stage 3 adds a surface-independent `ComputerSurface` contract and a Playwright-backed
`BrowserSurface`. Higher-level agent and replay code will depend on this seam rather
than directly on Playwright.

Install the Chromium browser binary after installing Python dependencies:

```bash
playwright install chromium
```

With the mock bank running in one terminal, manually exercise the browser adapter:

```bash
python -m src.surface.demo --member-id 12345 --headed
```

Stage 3 intentionally exposes only low-level browser primitives. Structured UI
observations and robust target representations are added in Stage 4.
