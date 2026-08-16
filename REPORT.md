# Architecture

AgentForge separates **discovery** from **production execution**. Discovery is intentionally flexible: a natural-language goal and entry point are given to an LLM-driven loop that repeatedly observes the current UI, chooses one structured action, executes it through a policy-checked surface adapter, and observes again. The loop is bounded by maximum steps and a wall-clock timeout so a model cannot wander indefinitely. A successful discovery run is evidence, not the production automation itself.

The production path begins only after compilation. `CapabilityCompiler` converts a successful discovery result into a typed, reviewable capability artifact. Runtime values such as the discovery member ID are replaced with named parameters, UI targets are preserved as ordered candidates, output extraction is encoded explicitly, and checkpoints define the expected state. `ReplayEngine` then executes this artifact deterministically with no LLM decision calls.

The concrete implementation is a local legacy-style web application driven through Playwright, but discovery and replay are not organized around Playwright APIs directly. `ComputerSurface` is the seam between logical automation actions and a particular perception/action technology; `BrowserSurface` is the current adapter. Structured observation and target construction live above that adapter. This lets the artifact describe *what control is intended and what state is expected* rather than embedding raw browser code as the capability.

I chose a single-process Python design because the problem is dominated by correctness of the control loop, artifact contract, policy boundary, replay semantics, and handoff seam—not queueing or distributed infrastructure. Pydantic provides strict data models and serialization, FastAPI serves the synthetic target, Playwright gives reliable browser control, and the OpenAI Responses API supplies structured discovery decisions. The trade-off is that this implementation does not demonstrate distributed scheduling or high-throughput execution; those are intentionally left outside the core.

The synthetic target is deliberately unfriendly enough to exercise the design: table-oriented layout, no test IDs, runtime business outcomes, an interstitial, and a permission-denied surface. This avoids proving the system only on a modern application with perfect semantic markup.

As an optional stretch goal, the final system also exposes an **agent-facing capability API**. `CapabilityCatalog` discovers saved JSON artifacts from the artifact directory and converts their typed inputs/outputs into a provider-neutral function/tool schema. A FastAPI surface exposes catalog, detail, and invocation endpoints. Invocation is intentionally thin: it loads the selected artifact and delegates to the existing deterministic `ReplayEngine`, so the API does not introduce a second execution model or bypass replay policy/checkpoint semantics.

# Artifact schema

The artifact is the central contract between discovery and replay. It is JSON-serializable, schema-versioned (`schema_version`) and capability-versioned independently (`capability.version`). That distinction allows the representation format to evolve separately from an individual automation flow.

A capability includes identity (`id`, `name`, description, version), a target specification (`application_family`, `surface_type`, `entry_point`, compatible versions), typed inputs, typed outputs, ordered steps, a success checkpoint, and known business outcomes. Inputs are explicit invocation parameters rather than values copied from the discovery trace. In the example capability, `12345` is replaced by the parameter `member_id`, which lets the same capability replay successfully for member `67890`.

Each step stores an action, a target descriptor, an optional value binding, a checkpoint, and risk metadata. Targets contain **ordered locator candidates**, not a single selector. For the legacy member-ID field, the strongest candidate is derived from nearby table text and the next candidate is structural. The Search button uses role/name first and visible text second. Candidate order is deliberate: replay is deterministic, but it still has a bounded fallback strategy if the strongest representation cannot resolve.

Outputs are declared independently of discovery text. `savings_balance` is typed as a string and uses a deterministic table-cell extractor defined by row text (`Savings`) and column header (`Balance`). This makes the caller contract explicit: an invoking agent does not receive an opaque transcript; it receives named outputs.

Checkpoints are separate from action success. A click completing does not prove the intended operation completed. The replay engine therefore verifies page title and required text after steps and again at the final success checkpoint. Known business outcomes use the same checkpoint concept, which keeps “no such member” as a modeled outcome rather than an exception caused by an unexpected page.

The schema is intentionally human-reviewable. A reviewer can answer: what does this capability do, what arguments does it require, what controls will it touch, what state proves success, what data will be returned, and what known outcomes exist—without reading the original LLM conversation.

# Determinism & error handling

Replay is a fixed execution engine over a saved artifact. It does not import an LLM decision into the control path and can run with `OPENAI_API_KEY` removed. Runtime parameters are validated before execution; required strings cannot be empty, unknown inputs are rejected, capability versions must be semantic versions, step IDs must be unique, and action steps that require targets must contain candidates.

For every UI step, replay resolves the saved target candidates in order and performs the saved action. It then verifies the saved checkpoint. Normal replay uses bounded polling so a stable but slow UI transition is not mistaken for a failure. Wait actions are also bounded. Importantly, bounded waiting does not become open-ended “self healing”: the expected target and expected state remain fixed by the artifact.

The result taxonomy separates three operationally different classes. **Business outcomes** are legitimate domain results the caller needs to know about; member `99999` returns `business_outcome / member_not_found`. **Recoverable conditions** are known runtime states that are not the requested result but may be resolved; the session-confirmation state returns `recoverable / known_interstitial` when handoff is disabled. **Hard failures** stop execution and surface diagnostics; member `77777` produces `checkpoint_failed` rather than blindly continuing.

Hard failures carry `failed_step_id`, `expected_state`, `observed_state`, and an evidence path. For the permission-denied scenario, the result explicitly says the engine expected `Member Details` containing `Member Record`, but observed `Permission Denied` with the required text missing. A screenshot is captured at the same point. This makes the result useful both to a calling agent and to a human debugging the automation.

The current targeting strategy is robust against small differences in markup but is not a general visual self-healing system. That is intentional. If all recorded candidates fail or the checkpoint does not match, replay stops or routes to a modeled intervention path instead of silently asking a model to reinterpret the UI. A bounded, policy-checked single-step recovery model could be added later, but leaving it out keeps the production path explainable.

# Heterogeneity & multi-tenant

The surface boundary is the main mechanism for extending beyond the implemented web target. `ComputerSurface` represents the operations the automation system needs—navigation, interaction, state access, and waits—while `BrowserSurface` supplies those operations through Playwright. Structured observations and artifact semantics sit above that boundary.

For another legacy web product, the browser adapter could expose additional observation channels such as frame traversal, accessibility information, DOM snapshots, or screenshot-derived regions while preserving the same logical action/checkpoint contract. For a desktop product, a `DesktopSurface` could implement the same interface using Windows UI Automation, accessibility APIs, image/coordinate control, or an OS automation framework. Target candidates would gain surface-specific strategies, for example accessibility role/name, window/control hierarchy, visual anchors, or coordinates relative to a stable region. The artifact remains a capability contract; only perception and actuation strategies change.

The current Playwright adapter does benefit from a DOM, but the design does not assume a single CSS selector is the capability. That is why targets are candidate descriptors and why checkpoints/output extraction are represented independently. On a no-clean-DOM surface, the observation/targeting adapter can produce different candidate types without requiring the discovery/replay architecture to be redesigned.

For multi-tenant reuse, I would key the base capability primarily by **application family + capability ID + compatible application version**, not by tenant. Hundreds of institutions using the same vendor product should share a base artifact. Tenant configuration would provide the concrete entry point, authentication/session context, and narrowly scoped target/checkpoint overrides only when necessary.

Per-tenant specialization should be layered rather than copied: base vendor artifact → version profile → tenant override. An override would be reviewable and minimal, for example replacing one target candidate or route pattern while inheriting the rest of the capability. Replay telemetry would track target-resolution failures and checkpoint mismatch rates by vendor version and tenant. A sudden cluster of failures across tenants on the same product version is evidence of vendor drift; an isolated tenant failure suggests local customization. New or changed artifacts would be versioned and promoted only after successful replay evidence, rather than silently mutating a shared flow.

I did not build a registry, tenant database, queues, or a desktop adapter because those are scaling mechanisms around the core contract. The important part implemented here is that the artifact and surface boundaries do not require per-tenant re-recording as the fundamental model.

# Escalation & handoff

Handoff is modeled as an ownership transition over the **same live browser session**, not as opening a new operator session. During replay, a known interstitial can be detected before normal deterministic progress is possible. With handoff enabled, AgentForge creates an intervention request containing the run ID, capability ID/version, current step, reason, and screenshot path. The event log records `intervention_requested`, then changes ownership to the human with `control_transferred`.

Automation remains paused while the Playwright page stays alive and visible. The operator uses that exact Chromium window. In the demonstrated scenario, the human clicks `Continue Session`. A lightweight browser-side recorder captures the manual action into session-scoped storage so the record survives same-origin navigation. The terminal prompt is the intentionally minimal operator surface: pressing Enter is an explicit signal that the human is returning ownership.

On return, AgentForge records each manual action, emits `control_returned` with the action count, and revalidates the checkpoint before resuming. If the human says control is returned but the required state is not reached, replay fails with `resume_validation_failed` and screenshot evidence rather than assuming the intervention worked. A successful handoff emits `resume_validated` and continues the original deterministic flow.

This design makes ownership observable: the run log says whether automation or the human has control and preserves context across the transition. The operator UI is deliberately bare because a production co-browsing console would add transport, authentication, presence, and remote-control complexity without changing the core seam being evaluated. In production, the same `InterventionRequest` could be routed to an operator service that exposes the existing browser session through a remote-browser stream while retaining the same pause/cede/resume state machine.

# Safety

Policy enforcement is outside the LLM. Discovery and replay both evaluate actions through a `PolicyEngine` before execution. Policy configuration contains allowed origins, permitted action types, and blocked routes. For the demonstration target, navigation is constrained to the configured origin and `/admin` is explicitly blocked.

Actions also carry risk classification. Safe/reversible actions can execute under the configured allowlist; risky or irreversible actions are handled conservatively by policy rather than being left to model judgment. The current capability only needs lookup/read behavior, so the demonstrated path remains in the safe class. A production deployment would bind higher-risk categories to explicit confirmation or mandatory human intervention.

The discovery model cannot directly execute an arbitrary selector or URL string it invents. It receives a structured observation and chooses a control index/action. The executor maps that choice to the system-generated target representation and still applies policy. This reduces the authority of model output and keeps the execution boundary typed and inspectable.

Secrets are supplied through environment variables and are not part of the capability artifact. `.env` is ignored by Git. The project uses synthetic banking data only. Persisted run information passes through redaction logic, and automated tests exercise secret/PII redaction behavior. The final repository is additionally checked for obvious secret patterns before submission.

The current redaction rules are intentionally small and demonstrative rather than a complete financial-data governance system. In production I would add structured field-level sensitivity labels, tenant-specific retention rules, encrypted evidence storage, access-controlled screenshots, and centralized secret scanning. Screenshots deserve particular care because visual evidence can contain information that text redaction cannot reliably remove.

# Cuts

I deliberately chose a thin, complete vertical slice instead of adding infrastructure around an incomplete core.

**Desktop automation was not implemented.** The `ComputerSurface` seam and target-candidate model are designed so a desktop adapter can be added, but building and testing OS-specific automation would have reduced time spent on the artifact, replay, error taxonomy, and handoff paths.

**Production multi-tenant plumbing was not implemented.** There is no capability registry, tenant database, distributed queue, worker fleet, or deployment system. The report instead defines how base vendor artifacts, version profiles, and tenant overrides would compose so reuse does not require recording every tenant independently.

**The operator surface is a terminal prompt plus the existing headed browser.** This is intentionally minimal, but the actual control transfer is real: automation pauses, the same session remains live, human actions are recorded, ownership returns explicitly, and state is revalidated.

**Replay does not use open-ended LLM self-healing.** Runtime execution stays deterministic. A future assisted fallback would be bounded to a single step, policy checked, separately evidenced, and never silently rewrite an approved artifact.

**A small agent-facing capability API was implemented as the single optional stretch goal.** It intentionally stops at catalog/discovery plus deterministic invocation by capability name. It is not a production registry: there is no persistence service, approval workflow, authentication layer, tenant-scoped catalog, or distributed execution backend. Those remain future product infrastructure around the same artifact/replay contract.

With more time, my next additions would be: (1) approval state, authentication, and replay stability metrics around the capability API; (2) one second surface adapter or tenant variant to validate the abstraction empirically; (3) structured screenshot redaction and evidence retention controls; and (4) bounded single-step assisted recovery behind explicit policy and audit logging.