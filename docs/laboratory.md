# TianJi laboratory — M1 operator and developer guide

This guide describes the additive TypeScript/Python slice. The creative direction remains **bidirectional world simulation laboratory / computational Laplace's demon**. M1 validates its interaction and computational spine in a deliberately small fictional civilian supply chain. It is not the final world model.

## Start

Run from the repository root:

```bash
npm --prefix web ci
npm --prefix web run build
uv sync --project backend --locked --python 3.12
uv run --project backend --locked python -m tianji_lab serve --port 8787 --data-dir .local-data
```

Open http://127.0.0.1:8787 and paste the generated `.local-data/token` into the connection form. The file is mode 0600; the server prints only its path. Alternatively supply `TIANJI_TOKEN` via your process environment. Do not put it in a URL, source file, commit or shared screenshot. The browser retains it only in sessionStorage for that tab. The token gives full local director access; it is not a participant-scoped credential.

The API serves the built `web/dist` assets. Rebuild after changing UI source, then restart the server if it was launched before `web/dist` existed. For frontend development, keep the API on 8787 and run `npm --prefix web run dev`; Vite proxies `/api` and `/health` to the loopback service.

SQLite and the authentication token live in the chosen directory, separate from legacy `runs/`. A POSIX advisory file lock rejects a second service owner before it can relabel running jobs. The currently supported host targets are Linux/macOS; Windows support requires a tested lock adapter. No old databases are converted, deleted or opened by the laboratory.

## Browser workflow

1. Connect, select a scenario, edit its name and bounded parameters (including the exogenous disturbance schedule), then save or create a new scenario. Saving uses a revision check; existing branches retain their old specification.
2. Choose an action for each tick and run forward. The default is waiting, not an unstated intelligent policy. Inspect inventory, shortages, cash, shipments and event logs by moving the recorded time cursor.
3. Specify terminal goals and a search-node budget. Run goal search. Inspect candidate branches and the search completeness indicator; every returned candidate has been replayed with the same forward model.
4. Fork at the selected recorded tick, change the remaining action sequence, then compare outcomes under identical frozen specifications. The original branch is immutable.
5. Export a branch as JSON and import it back. The importer checks schema, bounded fields, digest, conserved resources, replayed prefix and every continuation frame. A valid bundle is internally model-consistent, not cryptographically authenticated or evidence about the real world.

A new scenario with no branches is an actual empty state. Job status is stored by the server; API errors, queueing, cancellation, failure and incomplete searches must remain visible. There is no simulated conversational assistant.

## Model and forward/goal semantics

`backend/tianji_lab/kernel.py` is a deterministic integer transition model. There are three actions: `wait`, `order_standard`, `order_express`. An order buys one shipment from finite supplier stock and consumes cash. A turn purchases, advances the clock, receives goods now due, applies the exogenous events declared for that tick, then serves that tick's demand. Lead times and per-shipment costs are explicit scenario parameters. There are no sales revenues or invented market dynamics.

Unmet demand is cumulative lost demand, **not** a recoverable backlog. `delivered` means units served to customers, not shipments received. `lost` counts goods destroyed by an exogenous supplier loss: still part of the conserved total, never usable again.

### Exogenous disturbances

Disturbances are an explicit, operator-visible schedule inside the scenario specification. There is no random number generator and no seed, so reproducibility never depends on hidden bookkeeping and a replay never needs a draw log. The schedule is frozen with the scenario revision and travels inside exported bundles. Two kinds exist:

- `demand_spike` (1..20): the declared tick's demand is `demand_per_tick + amount`.
- `supplier_loss` (1..200): that many units of supplier stock are destroyed, clamped to what remains; a shortfall is not carried to later ticks.

At most one entry per tick and kind, at most ten entries, and a tick beyond the horizon is rejected rather than silently ignored. Events apply after the turn's purchase and after the shipments due at that tick have arrived, and before demand is served. Because the order executes first, buying ahead of a declared disruption moves goods out of supplier custody into an in-transit shipment and protects them; the schedule is visible and frozen, so goal search is expected to plan around it.

Executable invariants include:

- inventory + in-transit goods + customer deliveries + supplier stock + lost = initial total goods;
- cash + spent = initial cash;
- cumulative deliveries + shortage = elapsed ticks × per-tick demand + declared demand spikes so far;
- purchases, prices, shipment quantities and arrival times must be legal.

The rule label is derived from the specification, not claimed by a caller: an empty schedule is `supply-chain.v1` semantics, a non-empty schedule is `supply-chain.v2`. A trajectory or bundle that disagrees with its frozen specification is rejected rather than relabelled.

Goal-directed search is currently bounded depth-first enumeration of legal action sequences in this finite transition system, followed by forward verification. This is **not** reversing time, arbitrary natural-language causal inference, backward induction in a multiplayer game, or a guarantee of the best real-world decision. It ranks up to three plans by spend, then shortage, then lexicographic actions. State deduplication retains enough equivalent prefixes for the top-three ranking.

`found` means some model-feasible plans were found. `exhausted: false` means unsearched states remain, even when plans exist; their ranking is only among explored plans. `no_solution` is permitted only after exhausting the finite model frontier. `budget_exhausted` without plans means the budget was insufficient to decide feasibility. The worker also has a wall-clock limit: exceeding it fails the job, never fabricates a successful result or converts uncertainty into no solution.

A fork stores its continuation plus the full inherited action prefix. Import reconstructs its starting state from scenario initial state and prefix, not from an untrusted claimed snapshot. Parent identifiers in imported bundles are provenance only; imports receive fresh IDs and no dangling foreign key.

## Shared operation API

`GET /health` is public. All `/api` requests require `Authorization: Bearer <token>`. `GET /api/capabilities` returns the live operation registry and its Pydantic-generated input schemas. Mutations require a nonempty `request_id`. HTTP writes reject cross-site Origin/Sec-Fetch-Site and bodies over 1 MiB. There is no wildcard CORS, arbitrary path, shell, SQL or executable scenario input.

`POST /api/operations/<name>` takes `{"arguments": {...}, "request_id": "<unique mutation id>"}`. Success is `{"ok": true, "data": ...}`; errors expose `code` and `message`. Retrying the same operation/request ID/arguments returns its original result; reusing the ID with different arguments is a 409 conflict. Refetch jobs/workspace after a mutation: idempotency preserves the original response, not the object's future state.

Operation families:

- `scenario_list/create/update`: versioned scenario specifications.
- `run_forward`, `run_backward`, `branch_fork`, `job_get/cancel`: bounded asynchronous jobs.
- `branch_list/get/compare/export/import`: immutable results and portable replay.
- `workspace_attach/get/update`: desired scenario, selected branch, comparison target, recorded tick and panel, using revision CAS. Explicit null equals omitted for scenario/tick/panel; branch/comparison null clears that selection.

The single worker supervisor starts a separate computation process, leaving the HTTP event loop available. The queue is capped at 32 outstanding jobs and search at 50,000 expanded nodes. Cancelling a queued/running job prevents any result-branch commit; the supervisor stops its subprocess. Completed results cannot be retroactively cancelled. A restart marks previous running work `interrupted` and resumes queued work. No pause/resume checkpoints or SSE are claimed.

## External Agent / MCP

The MCP adapter uses the official Python SDK, discovers `/api/capabilities`, and forwards calls through the same authenticated HTTP operation boundary. It is not a second database owner or a hidden alternative implementation.

From the repository root, set `TIANJI_TOKEN` from the running service's token file, then configure an MCP client to launch:

```text
command: uv
args: [run, --project, /absolute/path/to/tianji/backend, --locked, python, -m, tianji_lab, mcp, --url, http://127.0.0.1:8787]
env: TIANJI_TOKEN supplied by the client environment / secret configuration
```

Use an actual absolute project path in your client. Do not paste a real token into committed example configuration. The adapter only accepts loopback HTTP URLs without credentials, path, query or fragment. It generates a mutation request ID for each MCP call; repeated tool calls are distinct actions, not automatically deduplicated conversational intent.

To control the visible tab, read its displayed workspace ID, use `workspace_get`, then `workspace_update` with the returned revision and desired branch/tick/panel. Browser polling applies these changes. The command response confirms **server desired state**, not browser acknowledgement; no connected tab is required for it to succeed. This distinction is visible in tool descriptions. Authentication inputs, file pickers and download dialogs are local transport UI, not domain operations.

All API and MCP callers are privileged directors in M1. Kernel `observe` has tested retailer/supplier projections for future participants, but this is not a deployed multi-user information barrier. Do not hand the director token to an untrusted simulated player.

## Quality gates

```bash
uv run --project backend --locked pytest backend/tests
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run build
npm --prefix web audit
```

Backend tests include real HTTP subprocess and official MCP SDK initialization/list/call. Pure kernel tests compare bounded search with a small exhaustive oracle, check illegal actions, conservation and replay. Lifecycle regressions cover single-owner storage and cancellation without result commits. These establish software behavior, not forecasting accuracy.

Real browser acceptance (built assets, isolated temporary database, official MCP client changing the visible browser workspace):

```bash
uv sync --project backend --locked --group browser
uv run --project backend --group browser playwright install chromium
uv run --project backend --group browser python scripts/check-lab-browser.py
```

The script creates only local fictional test experiments in a temporary directory and stops its server. Screenshots and a JSON report remain in the printed artifact directory. A Playwright platform warning is distinct from test failure; unsupported host distributions need actual browser execution before claiming support.

## Delivered slices and next work

M1 established the full forward/goal-search/branch/replay interaction. The current slice adds the explicit exogenous disturbance schedule (demand spikes and supplier losses) with recorded replay, conserved losses and a rule label derived from the frozen specification, so a conditional future now depends on both the actor's decisions and declared outside events. Neither slice is a final product.

Next model work: competing actors with private observation and independent adjudication, baseline and sensitivity experiments across schedules, and eventually a model-backed director proposal loop. Seeded randomness would only be added together with a recorded draw log that the import verifier consumes. Retain the bidirectional core rather than regressing into a feed dashboard.

A model-backed conversational co-pilot can propose structured operations and explain traces, but must not silently change rules, own both player and referee, or claim calibrated probabilities. Provider/cost choices, legacy cleanup or data migration, remote deployment and real-world action integrations remain explicit user confirmation gates.
