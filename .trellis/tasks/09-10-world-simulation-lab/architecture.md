# Proposed Architecture and Acceptance Contract

Status: architecture direction accepted with TypeScript + Python. The active m1-contract.md defines a narrower first runnable slice: deterministic labeled policies, bounded worker jobs and polling; real LLM agents, full pause/resume, approval flows and richer role models remain later work. This document is not an implementation report.

## Product invariants

1. Forward simulation and backward goal planning use the same scenario, state transition semantics, action validation and constraints.
2. Every user-facing product operation has a structured API representation. Web and agent adapters do not maintain different business rules.
3. Branches, goals and experiments are inspectable artifacts, not chat transcripts. Evidence and assumptions initialize and explain scenarios.
4. Players see role-scoped observations, including adjudicator summaries. Director/observer views are explicitly privileged and never silently fed to players.
5. "Computational Laplace's demon" is the creative identity. Model-conditional exploration must not be labeled omniscient prediction or empirical probability.

## Proposed stack-neutral component boundary

    Browser workbench / external agent / built-in director assistant
                  |
    Operation catalog + authentication + authorization + validation
                  |
    Application service (scenarios, branches, goals, experiments, jobs)
          |                    |                    |
      Persistence       Domain kernel         Event stream
                           |                       |
                    Bounded worker process -------+
                    policies / planning / adjudication

The application is a modular monolith plus a worker process, not a microservice fleet. Browser assets and API should share an origin in normal local deployment. CPU-bound exploration does not run on the API event loop. SQLite is the local default; do not add Redis/PostgreSQL until measured workload or multi-user deployment justifies it.

## The workbench

Default visual direction: a restrained dark scientific console, legible labels, distinct observed/assumed/simulated markers, no fake military telemetry. Use Chinese-first copy with identifiers and core terminology preserved. A branch tree and synchronized time cursor are the central canvas; charts, actor cards, event history and an optional assistant expose detail. A map is secondary, not the homepage requirement.

Essential workflows:

- Create/import a bounded scenario, inspect assumptions and validate it.
- Set role, initial conditions, goals, deadline, constraints and search budget.
- Run/step a forward experiment and inspect each state change and its justification.
- Pause at a committed tick, fork, alter a permitted assumption or decision and compare continuations.
- Ask for a goal plan, inspect alternatives and replay every claimed feasible plan through the same kernel.
- Compare costs, shortages, constraint violations and assumption dependence across branches.
- Export/import a versioned experiment bundle and replay without calling a model.

The assistant is a command/analysis surface over these workflows. With no model configured, the workbench remains usable with manual or explicitly labeled deterministic policies. Do not imply those policies are live LLM decisions. The first model-assisted slice must visibly identify the provider/model and tool results.

## Operation parity and agent control

Maintain a versioned capability manifest with stable operation IDs, input/output JSON schemas, read/write class, required scope, approval class and whether an operation creates a job. REST/OpenAPI and MCP derive their exposure from this catalog and call the same service handlers; automatic schema generation alone does not implement permissions.

Initial operation families (design identifiers, not existing endpoints):

- Scenario: list/get/create/clone/update-draft/validate/freeze/export/import. Mutation uses revision checks; frozen scenarios remain immutable.
- Experiment: create-forward/create-goal-search/step/pause/resume/cancel/get/list-events/get-snapshot.
- Branch/goal: list/get/fork/compare/create-goal/update-goal/evaluate-goal/verify-plan.
- Adjudication: list-pending/propose/accept/reject, with appropriate authority and an audit trail. Agents may propose; user-required approval cannot be supplied by adding an approved=true argument.
- Workspace: read-state/select-scenario/select-branch/seek-tick/show-panel/set-view. Commands target a specific browser session and acknowledged revision. No connected browser returns an explicit not-connected state, never false success.

Workspace commands are not domain events: moving the time cursor does not rewind or mutate the experiment. Concurrent human/agent edits use revision checks; stale commands fail predictably. Semantic commands are preferable to exposing arbitrary DOM JavaScript or using pixel coordinates.

Parity acceptance: enumerate product affordances against the capability manifest. The same permitted operation issued from Web and an authenticated MCP test client must produce equivalent domain results; scopes and role filtering must also match. Sensitive operations may exist but remain unavailable to an unprivileged agent. Agent controllability does not require exposing plaintext credentials, arbitrary shell/SQL or unrestricted filesystem access.

## Scenario kernel and reverse planning

Start with one fictional civilian supply-chain scenario, finite actions, explicit resource/time units, bounded horizon and separate participant objectives. Use integer quantities or explicit fixed units for conserved resources in the first kernel. Initial randomness, rules and policy choices are recorded. No real tactical targeting, production system writes or untrusted executable plugins are included.

An action has an actor, typed parameters, preconditions, time/cost effects and declared visibility. All admissibility and updates go through one kernel. Quantitative constraints are executable; uncertain social effects must be labeled modeled assumptions or await adjudication.

A goal defines desired terminal predicates, invariants, deadline, controlled actors and optimization preferences. Start with bounded search, optionally assisted by LLM candidate proposals. Candidate actions from any source are revalidated. Search returns best found candidates and the explored budget; only exhaustive search over an explicitly finite model can establish no solution within that model. Budget exhaustion is not impossibility.

Every feasible plan contains a verification receipt: scenario/rule/policy revision, initial state hash, ordered actions/observations, outcome hash, satisfied/failed predicates and budget. Reverify using the forward kernel; never force another actor's cooperation or alter the adjudication model to make a target succeed. Store policy/environment assumptions with the plan. Adaptive opponents eventually require contingent policies, not just favorable action sequences.

Results distinguish heuristic score, scenario frequency and empirically calibrated probability. Do not port the old divergence-to-probability formula as the new truth model.

## Persistence, jobs and replay

Persist ScenarioRevision, StateSnapshot, Branch, GoalRevision, Experiment, DomainEvent, ModelCallReceipt and AdjudicationRecord with schema versions. Immutable snapshots and append-only events support fork/replay; store expected revision on writes. Application objects contain timestamps, but deterministic state hashing excludes incidental wall-clock metadata and uses canonical serialization.

Jobs are durable, bounded and single-worker by default. Proposed states: queued, running, pause-requested, paused, awaiting-adjudication, cancel-requested, cancelled, succeeded, failed and interrupted. Define transitions and resumable checkpoints explicitly. A browser disconnect does not cancel a job; a reconnect resumes event reading by cursor. Failed work is not silently relabeled success or restarted as a duplicate.

Use idempotency keys for job submission and domain-changing commands. Commit tick effects, domain events and checkpoints atomically where possible. LLM/network calls are outside a database transaction; reconcile recorded call receipts and idempotency before applying effects. Document at-least-once external-call risk instead of promising impossible exactly-once billing.

Strict replay consumes recorded decisions/adjudications/random draws; a fixed random seed alone does not reproduce a cloud model. Live rerun and historical replay are separate modes. Bundle manifests pin rules/schema/provider metadata, omit secrets, and validate paths, counts, hashes and size caps on import. Old observations do not change when fresh evidence arrives.

## Security and approval gates

Bind the default server to loopback; use an authenticated local session/token, same-origin checks for browser writes and server-side authorization. External agents receive scoped tokens. Role-scoped data applies to API, MCP, SSE streams, errors, bundles and context summaries, not only the UI.

Sources and scenario text are untrusted data, never authority to modify capabilities. Rules are trusted project code or an allowlisted declarative schema; no eval of imported expressions. Credentials remain server-side, referred to by configured aliases. Log tool actions and concise rationales, not hidden chain-of-thought; redact secrets from traces.

Stop for user confirmation before choosing the new language architecture, deleting/retiring old source, transforming existing databases, enabling remote/multi-user access, spending material model/API budgets, adding production action execution, copying incompatible licensed assets, or materially changing the agreed core. Routine layout, endpoint naming and bounded implementation details may be decided autonomously.

## Milestone acceptance (not date promises)

M0 — planning approval: stack and compatibility boundary selected; repository architecture/spec authority updated only after that decision.

M1 — usable two-way laboratory: actual browser workflow from scenario editing through forward and goal search, branch comparison and replay, with deterministic actors. The same operations are reachable through the shared API and a real MCP test client; workspace selection/tick control is acknowledged by the connected browser. No placeholder search or fabricated simulation output.

M2 — model-assisted laboratory: one bounded director/tool loop and optional role agents, real configured-provider smoke test approved by the user, structured outputs, role isolation, adjudication UI, budget/cancellation and transparent failure modes. Recorded replay still works offline.

M3 — richer scenarios: new scenario packs and evidence-assisted initialization; add maps, scientific libraries or accelerated kernels only for a concrete need. Not an automatic commitment to a global digital twin.

Release tests include invariant/property checks, reference small-model search oracles, forward/reverse semantic consistency, role-isolation tests, concurrent/stale writes, worker interruption/resume, idempotency, import/export integrity, API/MCP parity and real browser end-to-end tests. All planning defaults remain reviewable; they do not constitute implemented features.
