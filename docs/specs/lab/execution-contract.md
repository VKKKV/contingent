# Laboratory execution and adapter contract

## Bounded analysis projects

`analysis_start` is an idempotent mutation accepting `request: VisionRequest` and optional bounded
`budget`. It explicitly persists a `tianji.analysis.v1` project and returns a queued `analysis`
job. `analysis_get` reads a current project by ID; `analysis_list` discovers project summaries.
`job_get` and `job_cancel` share the existing authenticated registry. Analysis results have their
own task/issue schema and never pass through supply-chain branch validation. The Web's new project
action is distinct from the legacy ephemeral Generate action.

Task hierarchy/dependencies are acyclic; issue feedback is permitted. Producing task identity,
claim references, role/output pairing and candidate supersession are validated. Separate same-model
role calls are not independent evidence. Budgets and structured partial results, active cancellation,
restart interruption and privacy boundaries are specified in [bounded analysis](../../bounded-analysis.md).
New tables are additive; existing vision/branch/workspace records are not converted or renamed.

## 1. Scope / trigger

Applies to `backend/tianji_lab/`, `web/src/` and their tests whenever a scenario, branch, job, workspace or import schema changes. The model is a fictional `supply-chain` kernel whose rule label is derived from the frozen specification: an empty exogenous-disturbance schedule is `supply-chain.v1`, a non-empty one is `supply-chain.v2`. All external clients are local directors. Participant projections and saved observations are not deployed per-user authorization. The offline adjudication service retains director-only, independently kernel-checked previews; it never mutates a recorded branch.

## Goal-directed scenario analysis

The primary workbench accepts an open-ended objective. It is separate from the deterministic
supply-chain kernel: schema validation proves well-formedness, not that an intervention works.
The supply-chain Web page is removed. Kernel operations and stored data remain compatible through
HTTP, CLI and MCP; workspace selections no longer have a browser renderer.

- `vision_generate` (nonmutating) accepts `vision`, `horizon`, `perspective`, `constraints`; returns
  a draft with the exact request, plan, model name, generated time and fixed `model_hypothesis`
  grounding. No automatic persistence or scenario conversion.
- Plans include interpretation, assumptions, tensions, 4–8 turning points and 2–3 paths.
  Nodes contain stage, actors, action, mechanism, prerequisites, risks and signals. Paths contain
  title, summary, ordered node references and tradeoff. Stage order is dependency order, not time.
- Validate bounded strings/arrays, unique identifiers, valid path references, increasing stages,
  distinct paths, at least one exclusive intervention per path, and use of all nodes. Subset routes
  that merely skip a step are rejected. Broken graph responses fail visibly, never become samples.
  The current small-model prompt uses five nodes and two branching/converging routes as a
  presentation scaffold, not a discovered causal topology.
- `vision_save` is an explicit idempotent mutation taking `draft`; returns an immutable saved object
  with id, created time and draft. `vision_get` retrieves one; `vision_list` lists bounded summaries.
  At most 100 saved analyses. Saves are structurally checked but user-supplied content is not proof
  of model origin or truth; stored model metadata is descriptive, not an authenticity certificate.
- Local inference shares the configured loopback provider and concurrency limit with actor proposals,
  uses a bounded response and deadline, and never holds a SQLite transaction during network IO.
- Browser input edits, disconnects and newer selections must invalidate stale responses. Save is a
  separate user action with readback. No speculative probability, fabricated evidence or fake progress.

## Runtime statistics

`analysis_stats({})` is authenticated and nonmutating. It validates explicitly saved drafts and
returns `saved_analyses`, `nodes`, `paths`, `scope="saved_analyses_only"` and
`architecture="single_model_single_call"`. Counts sum saved objects, not unique real-world claims
or inference calls. No activity log is collected. Browser generation timing is in-memory only,
measured around successful generation and validation, never inferred from saved timestamps.
The legacy keys keep their original scope and architecture values. Additive `multi_agent_runs`,
`multi_agent_tasks` and `multi_agent_nodes` count durable projects, their actual task records and
validated issue nodes separately; cancelled/partial projects are included, not labelled successful.

## Command-line access

The CLI discovers the live capability registry rather than maintaining a second operation list.
Every registered operation is invokable with a JSON argument object, with the same authentication,
validation, idempotency and error behavior as Web/MCP. JSON stdout is machine-readable; diagnostics
and mutation request IDs belong on stderr, failures return nonzero, and writes never retry silently.
Job commands return queued/running state without claiming completion; poll `job_get` explicitly.

`vision_*`, the `vision` request key and internal class names are compatibility identifiers.
User-facing terminology is goal-directed scenario analysis / 目标导向情景分析. This wording does not
upgrade model-generated hypotheses into scientifically validated claims.

## 2. Signatures

- `Service.execute(name, arguments, request_id=None)` is the sole application dispatch.
- `GET /api/capabilities` provides `{name, description, input_schema, mutating}` entries; MCP `tools/list` must match its names and schemas.
- `POST /api/operations/{name}` accepts `{arguments, request_id?}` and returns `{ok:true,data}` or `{ok:false,error:{code,message}}`.
- `workspace_update` uses `{id, revision, scenario_id?, branch_id?, compare_branch_id?, tick?, panel?}`; IDs are strings. Optional branch/compare IDs may be null; scenario/tick/panel cannot be null.
- `create_app(data_dir, token=None, start_worker=True, web_dir=None)` owns exactly one local Store. `Service.close()` joins the supervisor before releasing the POSIX ownership lock.
- `branch_import({bundle})`: versioned JSON, new local ID, no arbitrary paths or executable expressions.

## 3. Request / response / environment contracts

`TIANJI_TOKEN` is externally supplied or generated to `data-dir/token` mode0600. Public health/static routes disclose no experiment data. Bearer authentication gates all `/api` operations. The CLI binds loopback only; MCP accepts loopback HTTP URLs without credentials, path, query or fragment. Production Web shares API origin; Vite proxies API development requests without bypassing Origin checks.

Mutations require request IDs, stored in the same transaction as their effects. Same operation/request ID/arguments returns the original response. A retry is not a future-state query: refetch jobs and workspace. MCP creates one request ID per tool call; separate tool calls are separate user intents.

The workspace stores selected scenario (including empty scenarios), selected branch, comparison target, actual recorded tick and panel. Selecting a branch derives its scenario; explicitly contradictory branch/scenario IDs fail. Changing scenario clears stale branch/tick/comparison; changing primary branch clears comparison unless explicitly supplied. Comparison requires equal frozen specs. Revision CAS prevents silent lost updates. Explicit null equals omitted for scenario/tick/panel; branch/comparison null clears that selection. These compatibility operations retain desired state only; the removed supply-chain page no longer renders it. They are not browser acknowledgements.

Jobs freeze scenario/spec/revision on enqueue. One supervisor spawns a bounded subprocess and commits results only while job status is running. Queue max32, search max50000, subprocess wall limit30s. Cancellation prevents branch commit; shutdown/restart interrupts running work, queued jobs survive. Do not use the HTTP event loop for CPU search.

Replay bundles prove internal consistency, not origin authenticity. Reconstruct initial/fork state from frozen spec and complete prefix actions; then replay every continuation frame, event, goal predicate and hash. Retain `imported_parent_id` across repeated export/import; discard live foreign-key parent links on external imports. A bundle's declared `rule_version` and provenance must agree with `rule_version_for(spec)`; a schedule-bearing branch labelled with the pre-disturbance rules is rejected, never relabelled. Bundles exported before the disturbance slice (no `disturbances`, no `lost` keys) remain valid and replay under v1 semantics, because the digest covers the supplied branch object rather than a re-serialized model.

## Local model proposal

`actor_propose` takes only `observation_id` and returns an inert `ActionProposal`. It is a
nonmutating explicit inference request, not a cached read: repeated calls may differ. No
idempotency record, prompt, raw response, job or branch is created. Saved observation integrity
and frozen branch replay are checked before inference; SQLite is released before network IO.

`TIANJI_LOCAL_MODEL_URL` must be a literal loopback HTTP origin without paths, credentials or
redirects. `TIANJI_LOCAL_MODEL_NAME` names the model. Configuration is read at service start.
Only one in-flight call is allowed per process; total timeout is 30 seconds, output budget 96 tokens,
response bound 16 KiB. Proxy environment is ignored. The model receives role projection and an
explicit public-rule allowlist, never the full specification/state, actor identity or tokens.

Output must be exactly one JSON action, without refusal, tool calls, reasoning or truncation.
Actor/role/hash/policy (`local.llamacpp.v1`) are server-bound. Permissions, affordability and horizon
remain authoritative adjudication decisions. Errors: `actor_disabled`/`actor_unavailable` (503),
`actor_busy` (409), `actor_invalid_output` (502). No failure invents an action. HTTP/CLI/MCP callers
request adjudication explicitly; the removed Web page provides no proposal/adjudication controls.
Callers manually changing an action should use `manual.director.v1` rather than model attribution.

## 4. Validation and error matrix

- Missing/wrong Bearer: 401 `unauthorized`.
- Cross-site write: 403 `origin_denied`.
- Unknown operation/object: 404 `not_found`.
- Stale scenario/workspace revision: 409 `stale_revision`.
- Request ID reused with changed input: 409 `idempotency_conflict`.
- Queue full, incompatible comparison, revision increment past limit: 409 with explicit code.
- Extra keys, bool for integer, invalid recorded tick, malformed/dishonest bundle, body >1MiB: 422.
- Revisions are bounded to 1..2147483647; do not accept arbitrary Python integers into SQLite INTEGER and let them become HTTP500.
- Saved observations and adjudications are capped separately at 100 per branch; further creates return 409 `record_limit` atomically. Their scope is a frozen recorded branch, not the live scenario revision.
- A second owner of the same data directory fails before startup recovery can alter jobs.
- Kernel legal-action failures produce failed jobs, never synthetic trajectories or silent action substitution.

## 5. Good / base / bad cases

Good: run a default wait baseline, search for shortage0 under spend100, replay candidates, fork baseline at T2, export/import the fork; parent stays byte-for-byte unchanged.

Base: attach a workspace with no selected branch; select an empty scenario through MCP and read it back with `workspace_get`. Select a compatible goal branch, comparison target and T3; the API returns those values. No browser synchronization is implied.

Bad: forge a fork start while recomputing outer digest; import must reject against replayed ancestry. Reimport a valid imported fork must keep parent provenance. Budget1 without a plan must say undecided/budget_exhausted, not no_solution.

## 6. Required tests and assertion points

- `tests/test_kernel.py`: conservation, illegal actions, deterministic replay, bounded goals/search vs finite exhaustive oracle, observation projections, exogenous disturbance ordering (purchase, arrivals, event, demand), loss clamping without carry-forward, schedule bounds rejection, rule-label derivation, and schedule-aware search verified by replay.
- `tests/test_service.py`, `test_import_metadata.py`: frozen versions, idempotency, continuation prefix and goal replay, repeated import, revision bounds and no partial write, schedule frozen across later revisions, pre-slice bundles importing under v1, and mislabelled schedules rejected.
- `tests/test_lifecycle.py`: second owner cannot interrupt live jobs; cancellation leaves no result branch and next queued work completes.
- `tests/test_workspace.py`: scenario/branch/compare selection, empty scenarios, contradictory IDs, selected comparison invariants.
- `tests/test_m2_private_observation.py`, `test_adjudication_service.py`: strict immutable projections and hashes, actor/role/context binding, independent referee label, role action permissions, real forward equality, persistence/restart, transactional idempotency/caps/rollback, frozen revisions, imported/fork identity, HTTP allowlists and unchanged branch/jobs/workspace.
- `tests/test_api.py`, `test_mcp.py`: auth/origin/body bounds, actual CLI HTTP service and official MCP SDK initialization/list/call, published capability schema matching the live model.
- Frontend tests cover the remaining application navigation, shared capability/transport validation, stale analysis responses and explicit saves. Backend tests retain proposal identity and policy validation. Inspect real browser behavior when changing the workbench; do not store routine reports or screenshot archives.

Use the documented test/build commands. Temporary test data is cleaned up; no per-session evidence archive or dedicated evaluation runner is required.

## 7. Wrong vs correct

Wrong: let an old generated analysis replace a newer selection or edited request. Correct: invalidate obsolete requests and reject late results.

Wrong: remove the supply-chain page and silently drop its registry operations or stored objects. Correct: preserve HTTP/CLI/MCP compatibility and document that workspace state has no browser renderer.

Wrong: treat current scenario parameters as a recorded branch specification. Correct: retain the branch's frozen revision/specification and compare only compatible branches.

Wrong: restart recovery runs before checking directory ownership. Correct: acquire the exclusive lock first, then mark abandoned jobs interrupted.
