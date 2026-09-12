# Laboratory execution and adapter contract

## 1. Scope / trigger

Applies to `backend/tianji_lab/`, `web/src/` and their tests whenever a scenario, branch, job, workspace or import schema changes. The initial model is fictional `supply-chain.v1`; all external clients are local directors. Participant projections in `kernel.observe` are not deployed per-user authorization.

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

The workspace stores selected scenario (including empty scenarios), selected branch, comparison target, actual recorded tick and panel. Selecting a branch derives its scenario; explicitly contradictory branch/scenario IDs fail. Changing scenario clears stale branch/tick/comparison; changing primary branch clears comparison unless explicitly supplied. Comparison requires equal frozen specs. Revision CAS prevents silent lost updates. Explicit null equals omitted for scenario/tick/panel; branch/comparison null clears that selection. The browser clears the previous branch while a different one loads so branch-dependent controls never act on a workspace/branch mismatch. State is desired state, not a browser acknowledgement.

Jobs freeze scenario/spec/revision on enqueue. One supervisor spawns a bounded subprocess and commits results only while job status is running. Queue max32, search max50000, subprocess wall limit30s. Cancellation prevents branch commit; shutdown/restart interrupts running work, queued jobs survive. Do not use the HTTP event loop for CPU search.

Replay bundles prove internal consistency, not origin authenticity. Reconstruct initial/fork state from frozen spec and complete prefix actions; then replay every continuation frame, event, goal predicate and hash. Retain `imported_parent_id` across repeated export/import; discard live foreign-key parent links on external imports.

## 4. Validation and error matrix

- Missing/wrong Bearer: 401 `unauthorized`.
- Cross-site write: 403 `origin_denied`.
- Unknown operation/object: 404 `not_found`.
- Stale scenario/workspace revision: 409 `stale_revision`.
- Request ID reused with changed input: 409 `idempotency_conflict`.
- Queue full, incompatible comparison, revision increment past limit: 409 with explicit code.
- Extra keys, bool for integer, invalid recorded tick, malformed/dishonest bundle, body >1MiB: 422.
- Revisions are bounded to 1..2147483647; do not accept arbitrary Python integers into SQLite INTEGER and let them become HTTP500.
- A second owner of the same data directory fails before startup recovery can alter jobs.
- Kernel legal-action failures produce failed jobs, never synthetic trajectories or silent action substitution.

## 5. Good / base / bad cases

Good: run a default wait baseline, search for shortage0 under spend100, replay candidates, fork baseline at T2, export/import the fork; parent stays byte-for-byte unchanged.

Base: attach a workspace with no selected branch; select an empty scenario through MCP; Web displays the real empty state. Select a goal branch, comparison target and T3 through MCP; browser independently displays those values.

Bad: forge a fork start while recomputing outer digest; import must reject against replayed ancestry. Reimport a valid imported fork must keep parent provenance. Budget1 without a plan must say undecided/budget_exhausted, not no_solution.

## 6. Required tests and assertion points

- `tests/test_kernel.py`: conservation, illegal actions, deterministic replay, bounded goals/search vs finite exhaustive oracle, observation projections.
- `tests/test_service.py`, `test_import_metadata.py`: frozen versions, idempotency, continuation prefix and goal replay, repeated import, revision bounds and no partial write.
- `tests/test_lifecycle.py`: second owner cannot interrupt live jobs; cancellation leaves no result branch and next queued work completes.
- `tests/test_workspace.py`: scenario/branch/compare selection, empty scenarios, contradictory IDs, selected comparison invariants.
- `tests/test_api.py`, `test_mcp.py`: auth/origin/body bounds, actual CLI HTTP service and official MCP SDK initialization/list/call.
- `scripts/check-lab-browser.py`: actual Chromium create/edit/run/goal/fork/compare/import/export/cancel, external MCP visible selections, reload without old-job auto-selection, stale human edit preservation, layout and uncaught JS checks.

Build/test from a new snapshot without `.venv`, `node_modules`, `dist`, cached state or data. Do not use a one-off Vite resolver to bless a broken documented `npm run build` command.

## 7. Wrong vs correct

Wrong: apply desired branch ID immediately, fail its fetch once, then skip future loading because IDs already match. Correct: track loaded branch independently and retry missing results; reject out-of-generation or out-of-revision responses.

Wrong: reload terminal job history and auto-select every old result again. Correct: restored terminal jobs are already handled; preserve the last workspace selection.

Wrong: keep the previous branch selected and actionable while a different workspace branch loads. Correct: clear the branch for the duration of the load; branch-dependent buttons stay disabled until the matching branch object arrives.

Wrong: show editable rev4 parameters beside a rev2 result without distinction. Correct: show frozen-revision mismatch, expose frozen parameters/goal and stable short IDs for same-name candidates.

Wrong: restart recovery runs before checking directory ownership. Correct: acquire the exclusive lock first, then mark abandoned jobs interrupted.
