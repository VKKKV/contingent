# Development plan: bounded multi-agent scenario analysis

Status: supply-chain Web removal and bounded multi-agent execution are implemented. The new
workspace uses PydanticAI and React Flow/Dagre, with durable jobs and public structured results.
The original-static-asset UTC clock now uses full-viewport composition, 2px gaps and a reduced
150px image cap (upstream uses 200px). GIF and audio are excluded. Locally bundled tsParticles
supplies the reference-style
particle/link background with reduced-motion and visibility lifecycle handling. Black panels, glow,
form spacing and graph controls share the theme across both analysis modes. Desktop/mobile live
checks and side-by-side meter inspection are complete; exact visual reproduction across all states
remains pending. Legacy actor/vision HTTP exchange is
shared without changing endpoint contracts. Durable workspace reads/polling use TanStack Query
core; legacy single-call controllers remain separate, with idempotent save retries. Legacy path diagrams now also use
React Flow/Dagre, preserving path membership, explicit saves and domain validation.
See [current execution boundaries](bounded-analysis.md); sections below retain the design
and remaining acceptance criteria rather than asserting all items are complete.
Repository: `VKKKV/contingent`. Existing uncommitted work must be preserved.

Next feature increments and open-source adoption decisions are in
[next development](next-development.md). They are proposals, not implemented capabilities.

## Product identity

Approved product name: **Contingent**; GitHub repository: **VKKKV/contingent**.
The name emphasizes conditional outcomes rather than prediction certainty. This is not trademark
clearance or a claim of global name uniqueness.

The GitHub repository was renamed in place, retaining its identity and history; local `origin`
uses the new SSH URL. Pages is not enabled and no registered Actions workflows or reusable action
manifests were found during the rename check. Local uncommitted work has not been pushed.

The local directory, `tianji_lab` package/imports, `./tianji` command, `TIANJI_*` environment keys,
browser storage keys and operation/data IDs remain unchanged for compatibility. Any later migration
of these interfaces is separate from the product/repository rename.

## Architecture decision

Replace the one-shot five-node response with separately executed, bounded agent tasks. Keep
FastAPI, SQLite, Pydantic and the shared Web/CLI/MCP operation registry. Remove the supply-chain
experiment page and its navigation; it is no longer a product destination. Rebuild the remaining
UI against the actual DivergenceMeter reference, not the current approximate black/orange theme.

Prefer dependencies when they replace owned infrastructure:

- `pydantic-ai-slim[openai]`: typed model output, role-specific agents, shared usage accounting,
  bounded validation retries and provider integration. Replace duplicated completion handling in
  `local_actor.py` and `vision.py`; retain local-origin restrictions, sanitized errors, transport
  size limits and application-level cancellation. Verify real llama.cpp compatibility before
  replacing both production paths. Disable telemetry and implicit network retries.
- `@xyflow/react` with `@dagrejs/dagre`: one graph renderer for task dependencies and issue graphs.
  The legacy path diagram now uses the same renderer/layout dependencies instead of manual
  placement, SVG edge routing and CSS-scale zoom. Domain validation, shared-node membership,
  path highlighting, keyboard selection and explicit-save behavior remain intact.
  Stage labels describe the domain nodes; horizontal ranks now follow path dependencies rather
  than fixed stage columns. The goal is a non-selectable direction, not an inferred task.
  Use OSS components, not paid example code.
  Dagre is the initial directed-layout choice; ELK is an alternative if compound graph/port-routing
  needs actually arise, not an additional default dependency.
- TanStack Query: the durable workspace now uses `@tanstack/query-core` directly with its existing
  external-store controller, replacing custom read timers/controllers without a forced hooks rewrite.
  The React hooks package is not needed for this integration. Legacy controllers remain separate, with idempotent save retries. Configure retries explicitly; generation is
  an explicit mutation, never a refetch-on-focus query. Browser fetch cancellation does not cancel
  server work: maintain a server cancellation operation and per-run result identity.
- Defer Typer, ORM, Redis, Celery, LangGraph and additional agent frameworks unless a concrete
  requirement makes them simpler than existing code. Do not replace working argparse/SQLite
  merely to accumulate dependencies. Reconsider LangGraph only if durable branching/resume is
  required; it would replace the runner, not sit beside another orchestration stack.

These primary candidates have MIT licenses in their upstream repositories. Pin compatible
versions only during implementation. Compare removed custom code, adapter code, dependency size
and runtime behavior; no percentage reduction is promised. Add features and replace infrastructure
as separate changes so increased feature scope does not disguise unnecessary framework code.

## UI revision — approved direction, partially implemented

The maintainer rejected the current visual approximation across all pages. Matching the palette
alone is insufficient. This section supersedes the earlier independent CSS tube recreation and
runtime-count-as-hero direction.

### Remove the supply-chain page — implemented

The navigation entry and lazy route in `AppShell.tsx`, the supply-chain `App.tsx` page and its
exclusive components/hooks/styles/tests are removed. Shared API/auth/schema utilities required
by the analysis product remain. There is no hidden legacy page.

The deterministic kernel and existing scenario, branch, job, observation, proposal, adjudication
and workspace operations remain available through HTTP/CLI/MCP. Workspace selection no longer
has a browser renderer. This change does not delete user databases, rename stored objects, rewrite
Git history or retire backend compatibility operations. Any later retirement requires a separate
compatibility/data decision.

### Preserve the original nixie presentation

Upstream `Website/divergence_meter.js` renders digits from `Website/images/0.png` through `9.png`
and the separator from `p.png`; `11.gif` and `12.gif` provide the startup/change animation.
`Website/style.css` uses a full-height centered meter, 2px digit gaps, proportional image scaling,
`object-fit: contain` and pixelated rendering. The current CSS-drawn tubes and stacked text digits
are not an acceptable substitute.

Use the original digit/separator assets and their rendering proportions, glass/body appearance,
glow and spacing. Do not redraw the tubes, recolor/recompress the images or replace them with a
font. Verify asset provenance and reuse terms before vendoring, pin the upstream revision, retain
applicable GPL notices and attribution, and serve assets locally rather than hotlinking. Both
repositories have GPLv3 license texts, but repository licensing alone does not establish the
provenance of every media asset; unresolved asset rights must be raised, not silently worked around
with another unapproved imitation. Adapt only the value source and application integration.

The hero display becomes an actual **UTC clock**. Prefer `HH.MM.SS` with the upstream separator
artwork, accompanied by an unambiguous `UTC / HH.MM.SS` label and UTC calendar date. Never show
host-local time under a UTC label. Derive each update from the current timestamp rather than
incrementing a counter; refresh correctly after tab suspension and at midnight. The clock reflects
the device clock, not an independently synchronized time authority. It requires neither API login
nor a model call. Disable random-value-on-click behavior. Any initial animation is decorative,
brief and honors reduced motion; normal ticking must remain readable without repeated fake
loading sequences. Screen-reader text should identify UTC without announcing every second.

Analysis counts, task counts and measured durations may remain in a secondary status/report area.
Do not label time or counts as divergence, probability or scientific measurement of world state.

### Match the complete reference, not only the meter page

Inspect the live reference and source together: full-viewport composition, negative space,
background particle/link behavior, typography, glow layers, tables, controls, borders and content
density. Carry that visual language consistently into the analysis input, task tree, issue graph,
node details, saved analyses, connection states and errors. Do not leave generic dashboard cards
or the former theme underneath orange overrides. Keep long-form analysis readable and controls
keyboard-accessible; adapt small-screen layout without altering tube proportions. Use existing
licensed upstream mechanisms or focused libraries when they reduce custom code; avoid introducing
a separate hand-written particle engine merely to imitate one already available.

Completion requires direct side-by-side visual inspection against the reference, not merely color
or overflow assertions. Check original asset fidelity, scale, placement and effects; test UTC with
non-UTC system zones, leading zeros, midnight rollover and tab resume. Exercise both populated and
empty/error analysis states, desktop/mobile, keyboard focus and reduced motion. If visual inspection
is unavailable, state that limitation rather than calling fidelity verified. Do not create a
mandatory screenshot/report archive; temporary comparisons suffice.

## Execution model

A bounded application coordinator schedules real calls with separate input contexts and typed
outputs. It is not itself an additional “manager LLM” by default:

1. Framing agent converts the objective into operational criteria, scope, stakeholders, constraints,
   missing information and subquestions. Contradictions can stop the run for clarification.
2. Strategy agents examine distinct mechanisms or stakeholder perspectives selected from those
   subquestions. Each sees the brief, not the other agent's first draft. Their number follows the
   problem within explicit run limits, not a fixed graph-node quota.
3. Critic examines each strategy for unsupported dependencies, incentives, feasibility,
   counterexamples and unintended effects. It references concrete claim IDs, not an ungrounded score.
4. A challenged strategy can receive a bounded targeted revision. Budget exhaustion produces a
   partial result with unresolved objections, not a fabricated consensus or hidden extra calls.
5. Synthesis retains alternatives, dependencies, objections and unknowns. It cannot mark claims as
   verified merely because agents agree.

Use the same local model initially with separate contexts and role instructions. This creates
separate executed tasks, not independent sources of truth. Shared model biases remain. A single
local GPU queues model calls; logical fan-out does not imply simultaneous GPU execution.

Run limits cover model calls (including all retries), tokens, elapsed time, task count and revision
depth. Initial suggested ceilings: 8 total calls, one revision pass, 20 issue nodes and 40 edges;
these are resource bounds, not mandatory output shapes. Select actual limits after local profiling.
Do not silently lower a failing run into the old five-node template.

## Data and graph semantics

Keep three separate objects:

- Analysis run: request, status, resource budget, task identities/dependencies and public structured
  task results. States include queued, running, succeeded, partial, failed, cancelled and interrupted.
- Issue graph: question, assumption, claim, intervention and outcome nodes; typed edges such as
  requires, supports, challenges and may-influence. Claims reference their producing task and any
  actual source or reviewer result. Unsupported claims stay hypotheses; no invented citations.
- Candidate strategy: a selected set of interventions, prerequisite conditions, tradeoffs and
  observable signals. It references the issue graph without forcing all strategies to converge.

Task dependencies must be acyclic. The issue graph may contain feedback or mutual objections;
cycles must be explicit, not rejected simply because the old four-stage layout cannot draw them.
Domain validation covers reference integrity and compatible edge types, not reality certification.

Execution view: expandable task tree/DAG, actual status/duration/model, task brief, structured result,
errors and targeted rerun controls. Planned nodes are visibly queued; completed status requires a
real completed call. Do not display hidden chain-of-thought or simulated typing/agent debate.

Issue view: filter by strategy, stakeholder or objection; selecting a claim locates its producing
agent task, and selecting a task highlights its contributions. Review outcomes remain visible.
The primary meter shows the UTC clock with the original nixie presentation; secondary status
reports actual counts and measured durations, never fictional divergence.

## API and lifecycle

Add `analysis_start`; prefer existing `job_get` and `job_cancel` for shared lifecycle control rather
than introducing a second generic scheduler. The run result exposes task states and graphs; CLI and
MCP use the same registry. Targeted reruns are a later bounded operation with explicit lineage and
a new budget, not an unlimited recursive agent spawn command.

Recommended new UI action: **Create and run analysis**. It explicitly creates a product project and
returns a run ID immediately. Persist current task status and validated structured results so a
refresh can reopen the project. This proposal changes the new operation's product semantics, not
`vision_generate`: the existing one-shot endpoint remains ephemeral and its saves remain explicit.
Do not enable automatic persistence behind an unchanged Generate button. No raw prompts,
completions, hidden reasoning, per-event traces, reports or screenshots are retained. Inspect the
idempotency table too: it stores operation arguments/results and must not become a transcript archive.

Reuse SQLite job lifecycle boundaries but separate executors by job kind. The current rules worker
has a 30-second subprocess deadline and branch-specific commits; it cannot execute multi-agent
analysis unchanged. Update frontend discriminated job results so analysis completion never triggers
supply-chain branch selection. Network calls stay outside SQLite transactions. Restart marks
in-flight analysis interrupted; no automatic resume or exactly-once model invocation is promised.
Cancel prevents subsequent tasks and late result commits and aborts the active client request;
provider-side cancellation remains best-effort.

Version the new analysis objects. Existing saved drafts lack task history and must remain readable
as single-call legacy results; never invent agents for them. Runtime statistics must distinguish
single-call and multi-agent runs instead of globally relabeling historical records. The task hierarchy
uses parent IDs, with scheduling dependencies represented separately. Both must be validated.

## Scientific limits and evidence

Multiple agents improve decomposition and adversarial review, not empirical validity. First release
supports model hypotheses and user-supplied material; no agent is called a factual researcher unless
it actually has evidence access. A subsequent explicit retrieval capability can provide source URL,
date and supporting passage. Distinguish source support, contradictions and unknowns; retrieved
content is data, never instructions. Citation integrity still does not prove causation.

Do not compute universal success probabilities, impact scores or claim causal identification from
textual debate. Executable domain models may validate specific claims where such models exist;
the supply-chain kernel cannot certify arbitrary social/political paths.

## Implementation order and completion conditions

Product/repository naming and the page-removal portion of step 2 are implemented without
vendoring unresolved media. The implementation sequence and acceptance conditions are:

1. Product name and in-place GitHub rename are complete; primary branding and origin use
   Contingent / contingent. Preserve the dirty tree and explicit compatibility identifiers.
2. With the supply-chain page removed, rebuild all remaining pages against DivergenceMeter, including
   the original nixie assets displaying UTC. Replace manual graph rendering with React Flow/Dagre
   as part of the task/issue visualization work; check visual fidelity, keyboard access, responsive
   layouts and reduced motion rather than accepting a palette-only reskin.
3. Add the typed agent adapter and bounded analysis runner. Actual local-model integration must
   demonstrate framing, separate strategy calls, critic and synthesis, plus failure/cancel paths.
4. Replace the fixed topology with typed task/issue data. Add linked execution and issue views,
   run polling and explicit project creation; all functions callable from Web, CLI and MCP.
5. Remove superseded transport/session/layout code after equivalence and new behavior pass normal
   tests. Update current documentation without adding a report pipeline.

Completion requires actual per-task invocation state, variable issue topology, visible objections,
no fake evidence, capped retries and cancellation, preserved saved analyses, and UI/CLI/MCP parity.
A same-model agreement must never appear as independent validation. Use ordinary tests plus live
local-model/browser checks; report outcomes directly rather than creating mandatory evidence files.

## Sources

- https://github.com/FrancescoCaracciolo/DivergenceMeter
- https://divergence.nyarchlinux.moe/
- https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository
- https://pydantic.dev/docs/ai/guides/multi-agent-applications/
- https://pydantic.dev/docs/ai/models/openai/
- https://reactflow.dev/learn/layouting/layouting
- https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation
- https://docs.langchain.com/oss/python/langgraph/overview
