# AgentForge

AgentForge is a proof-of-concept computer-use automation system.

It demonstrates the complete path from a natural-language goal to a genuine LLM-driven interaction with a live UI, compilation of that successful run into a typed and versioned capability artifact, and deterministic replay of the capability with no model in the execution loop.

The concrete target is a synthetic legacy member-servicing application. It intentionally uses table-oriented markup, no test IDs, and multiple runtime states so the system has to reason about targeting, checkpoints, exceptional outcomes, safety, and human intervention rather than only replaying a happy-path script.

## End-to-end flow

```text
Natural-language goal
        |
        v
LLM discovery
observe -> decide -> act
        |
        v
Successful discovery trace
        |
        v
Capability compiler
        |
        v
Typed + versioned artifact
        |
        v
Deterministic replay
NO LLM IN THE LOOP
        |
        +--> success + outputs
        |
        +--> business outcome
        |
        +--> recoverable condition
        |
        +--> hard failure + evidence
        |
        +--> same-session human handoff when enabled
```

## What is implemented

- Genuine LLM-driven observe -> decide -> act discovery against a live UI.
- Configurable maximum steps and discovery timeout.
- Playwright-backed browser interaction behind a `ComputerSurface` abstraction.
- Structured UI observations and ordered fallback target candidates.
- Explicit policy allowlists for origins, routes, and action types.
- Safe/risky action classification and conservative policy enforcement.
- Sensitive-data redaction for persisted evidence.
- Typed, serializable, human-reviewable capability artifacts.
- Parameterization of discovery-time values into runtime inputs.
- Typed output extraction rules and explicit success checkpoints.
- Deterministic replay with no LLM decision calls.
- Bounded checkpoint waiting for transient UI state.
- Explicit replay taxonomy for success, business outcomes, recoverable conditions, policy blocks, invalid inputs, and hard failures.
- Failure diagnostics containing the failed step, expected state, observed state, and screenshot evidence.
- Same-session human handoff with explicit ownership transfer, recorded manual actions, resume signaling, and checkpoint revalidation.
- Structured JSONL run logs and JSON results.
- Automated tests covering the load-bearing discovery, artifact, replay, safety, observability, and handoff seams.

## Repository layout

```text
artifacts/
  member_savings_balance.json   Canonical reusable capability

evidence/
  member_savings_balance.json   Demonstration copy of the saved artifact
  run_*/                        Curated discovery/replay evidence

src/
  agent/                        LLM discovery loop
  capability/                   Artifact schema + compiler
  capability_api/               Agent-facing catalog + invocation API
  handoff/                      Same-session intervention flow
  mock_bank/                    Synthetic legacy target application
  observability/                Run logs + failure evidence
  policy/                       Allowlist, risk policy, redaction
  replay/                       Deterministic execution engine
  surface/                      Surface abstraction + Playwright adapter

tests/                          Automated test suite

README.md                       Setup and demo path
REPORT.md                       Design write-up
```

## Requirements

- Python 3.11+
- An OpenAI API key for the discovery run only
- Chromium installed through Playwright

Replay does **not** require an OpenAI API key.

## Setup

Clone the repository and enter it:

```bash
git clone https://github.com/akshat240401/agent-forge.git
cd agent-forge
```

Create a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Install Chromium for Playwright:

```bash
python -m playwright install chromium
```

Run the tests:

```bash
pytest
```

The final implementation currently contains 51 tests.

## Configuration

Discovery requires these environment variables:

```text
OPENAI_API_KEY
OPENAI_MODEL
```

An example is provided in `.env.example`.

Never commit a real API key.

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="YOUR_API_KEY"
$env:OPENAI_MODEL="gpt-5"
```

macOS/Linux:

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_MODEL="gpt-5"
```

`OPENAI_MODEL` is optional because the discovery CLI defaults to `gpt-5`.

## Start the legacy target application

Run the mock bank in its own terminal:

```bash
python -m src.mock_bank
```

The application is served at:

```text
http://127.0.0.1:8000
```

All names, IDs, account numbers, and balances are synthetic.

| Member ID | State |
|---|---|
| `12345` | Successful lookup used for discovery |
| `67890` | Second successful member used for parameterized replay |
| `99999` | Expected `member_not_found` business outcome |
| `55555` | Session-confirmation interstitial used for recovery/handoff |
| `77777` | Permission-denied hard-failure surface |

## Demo 1: genuine LLM discovery

Keep the mock bank running. In another terminal, configure `OPENAI_API_KEY`, then run:

```powershell
python -m src.agent.cli `
  --goal "Look up member 12345 and return their current savings balance" `
  --target "http://127.0.0.1:8000" `
  --headed
```

The LLM observes the current UI and chooses one structured action at a time. A successful run performs approximately:

```text
observe Member Search
-> TYPE 12345
-> observe
-> CLICK Search
-> observe Member Details
-> FINISH
-> savings_balance = $4,821.37
```

Discovery supports bounded execution with `--max-steps` and `--timeout`. Evidence is written under `evidence/run_<id>/`.

## Demo 2: compile the successful run into a capability

Given a successful discovery result:

```powershell
python -m src.capability.cli `
  --discovery evidence\<DISCOVERY_RUN_ID>\result.json `
  --output artifacts\member_savings_balance.json `
  --sample-member-id 12345
```

The compiler converts the discovery-time literal into a runtime parameter:

```json
{
  "kind": "parameter",
  "name": "member_id"
}
```

The saved artifact declares capability identity/version, target family/surface, typed inputs/outputs, ordered actions, locator candidates, checkpoints, and known business outcomes.

## Demo 3: deterministic replay with no LLM

Replay a different member ID:

```powershell
python -m src.replay.cli `
  --artifact artifacts\member_savings_balance.json `
  --member-id 67890 `
  --headed
```

Expected:

```text
status = success
savings_balance = $2,614.09
```

Replay binds the runtime parameter to the saved artifact, resolves targets deterministically, verifies checkpoints, and extracts the declared output. It does not ask an LLM what to do.

## Demo 4: business outcome

```powershell
python -m src.replay.cli `
  --artifact artifacts\member_savings_balance.json `
  --member-id 99999 `
  --headed
```

Expected:

```text
status = business_outcome
code   = member_not_found
```

A nonexistent member is treated as a legitimate caller-facing outcome rather than a system crash.

## Demo 5: recoverable runtime condition

Without handoff enabled, the `55555` session-confirmation state is classified as:

```text
status = recoverable
code   = known_interstitial
```

This keeps a known recoverable runtime condition distinct from both business outcomes and hard failures.

## Demo 6: same-session human handoff

```powershell
python -m src.replay.cli `
  --artifact artifacts\member_savings_balance.json `
  --member-id 55555 `
  --headed `
  --handoff
```

When replay reaches the session-confirmation interstitial, automation pauses and prints an intervention request while the Chromium page remains open. The human manually clicks `Continue Session` in that same browser session, returns to the terminal, and presses Enter to return control.

AgentForge records the human action, restores automation ownership, revalidates the expected checkpoint, and resumes deterministic execution.

Evidence includes:

```text
intervention_requested
control_transferred
human_action
control_returned
resume_validated
replay_completed
```

## Demo 7: hard failure and diagnostics

```powershell
python -m src.replay.cli `
  --artifact artifacts\member_savings_balance.json `
  --member-id 77777 `
  --headed
```

The permission-denied surface produces a structured hard failure:

```json
{
  "status": "failure",
  "code": "checkpoint_failed",
  "failed_step_id": "step_2_click",
  "expected_state": {
    "page_title": "Member Details",
    "required_text": ["Member Record"]
  },
  "observed_state": {
    "page_title": "Permission Denied",
    "missing_required_text": ["Member Record"]
  }
}
```

A screenshot is also captured for debugging.

## Safety model

Every automation action passes through an explicit policy layer. The demo constrains allowed origins, allowed action types, blocked routes such as `/admin`, and action risk classification.

The discovery model does not directly invent arbitrary selectors for execution. It chooses among controls exposed by the structured observation, and the system resolves the recorded target representation.

Secrets are not stored in capability artifacts. `.env` is ignored by Git, and persisted evidence passes through redaction.

## Targeting and determinism

Targets are stored as ordered locator candidates rather than a single fragile selector.

The member ID field uses a legacy-table-aware XPath with a structural input selector fallback. The Search button uses role plus accessible name with visible text as a fallback.

Replay attempts recorded candidates in deterministic order, and checkpoints are validated separately from locator success. A click succeeding therefore does not by itself mean the business operation succeeded.

## Evidence

The repository contains curated evidence:

```text
evidence/run_d37f9847c87c
  Genuine LLM discovery

evidence/run_05b560cca299
  Deterministic replay success using member 67890

evidence/run_a099316ecef6
  member_not_found business outcome

evidence/run_3a9f88e34b09
  Same-session human intervention and resume

evidence/run_26d42264e4d2
  Permission-denied hard failure with screenshot
```

Each run contains structured `events.jsonl` and `result.json`. Failure/intervention runs additionally contain screenshot evidence.

The capability artifact is available in both locations:

```text
artifacts/member_savings_balance.json
  Canonical reusable capability used by replay

evidence/member_savings_balance.json
  Saved demonstration copy included with the end-to-end evidence
```

The `artifacts/` copy is the runtime source of truth. The `evidence/` copy makes the complete demonstrated flow reviewable from one directory.

## Running without a live model service

Only discovery needs OpenAI access. Tests, artifact validation, and deterministic replay can run without `OPENAI_API_KEY`.

```powershell
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue

python -m src.replay.cli `
  --artifact artifacts\member_savings_balance.json `
  --member-id 67890
```


## Stretch goal: agent-facing capability API

AgentForge also exposes saved artifacts as an agent-discoverable capability catalog and invocation API.

Start the capability API in a separate terminal:

```bash
python -m src.capability_api
```

It listens on:

```text
http://127.0.0.1:8010
```

Discover available capabilities:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8010/v1/capabilities" |
  ConvertTo-Json -Depth 10
```

The catalog exposes each capability's identity, version, application family, typed input/output schemas, and a provider-neutral function/tool schema. For `member_savings_balance`, an agent sees a required string argument named `member_id` and a declared string output named `savings_balance`.

Invoke the capability by name with typed arguments:

```powershell
$body = @{
    arguments = @{
        member_id = "67890"
    }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8010/v1/capabilities/member_savings_balance/invoke" `
  -ContentType "application/json" `
  -Body $body |
  ConvertTo-Json -Depth 10
```

The demonstrated invocation returns:

```text
status = success
capability_id = member_savings_balance
savings_balance = $2,614.09
```

The API does not create a second automation path. It loads the same saved artifact and invokes the existing deterministic `ReplayEngine`, preserving the same policy, checkpoint, output, and error semantics as direct replay.

## Design scope

The implementation deliberately focuses on one concrete browser surface and one thin end-to-end capability.

The central boundary is `ComputerSurface`: actions, targets, checkpoints, artifacts, results, policy, and handoff are separate from the concrete Playwright adapter.

Desktop adapters and production multi-tenant infrastructure are intentionally not implemented. The extension model, vendor-family reuse strategy, tenant specialization, drift management, and other trade-offs are described in `REPORT.md`.

## Tests

Run the complete suite:

```bash
pytest
```

Focused suites:

```bash
pytest tests/test_policy_engine.py tests/test_redaction.py
pytest tests/test_replay_engine.py tests/test_replay_hardening.py
pytest tests/test_handoff.py
```

## Notes

- The target contains synthetic data only.
- No real bank credentials or customer PII are used.
- Discovery requires model API access.
- Deterministic replay intentionally does not use an LLM for decisions.
- The operator UI is intentionally minimal; the pause/ownership/manual-control/resume mechanism itself is real.