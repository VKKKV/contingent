# Laboratory guide

This is the operational guide. The shared API/compatibility contract lives in
[execution-contract.md](specs/lab/execution-contract.md); current analysis behavior lives in
[bounded-analysis.md](bounded-analysis.md).

## Run

From the repository root:

```bash
./start.sh
./start.sh --no-model
./start.sh --model /path/to/model.gguf
```

The launcher builds the Web app, starts the authenticated API and local model, and waits for
readiness. It does not download models. Manual setup:

```bash
npm --prefix web ci
npm --prefix web run build
uv sync --project backend --locked
uv run --project backend --locked python -m tianji_lab serve --port 8787 --data-dir .local-data
```

Open `http://127.0.0.1:8787` and use the generated token file, or set `TIANJI_TOKEN` in the service
environment. Never put credentials in URLs or source files. The browser keeps the token in the
current tab and it grants full access to that local service. Only one service may own a data directory.
Existing databases are not converted or deleted automatically.

## Analysis modes

The default workspace creates a durable project with separate framing, strategy, critic, optional
revision and synthesis calls. All roles share the local model and are not independent evidence.
See [bounded analysis](bounded-analysis.md) for task graphs, persistence, cancellation, budgets and
partial results.

New v2 projects use bounded public research by default. The UI discloses outbound queries and local
source snapshots; offline mode skips research. Exact retained passages can be cited, but citations
do not establish truth or causality. See [research integration](research-integration.md).

The legacy view is a single-call, explicit-save workflow. Its five-node/two-path shape is a
presentation scaffold, not discovered causal structure. It remains offline. Saved drafts remain
compatible and must not be presented as multi-agent history.

## Deterministic compatibility API

The former supply-chain Web page is removed, but its kernel, stored data and registry operations
remain available through HTTP, CLI and MCP. Use `./tianji schema NAME` to inspect each operation.
The execution contract is authoritative for validation and lifecycle semantics.

The kernel is deterministic: `wait`, `order_standard` and `order_express` are the available actions;
there is no randomness or calibrated probability. Replay, goal search, observations, proposals and
adjudications operate on frozen specifications. `found` means a candidate was found; budget exhaustion
is undecided and is not `no_solution`. Model proposals are inert suggestions and never mutate a
branch without explicit adjudication.

Do not distribute the director token to untrusted participants. The compatibility operations are
local-director tools, not a deployed multi-user authorization system.

## Local model proposals

Local proposals are optional and loopback-only. Start an existing GGUF with llama.cpp, then configure
`TIANJI_LOCAL_MODEL_URL` and `TIANJI_LOCAL_MODEL_NAME`. Keep the endpoint on loopback; Contingent does
not download models or invoke external providers. The server sends only the role projection needed for
the proposal, validates the returned action, and reports disabled/unavailable/busy/invalid errors
explicitly. It never archives prompts or raw completions.

## CLI, HTTP and MCP

```bash
./tianji health
./tianji operations
./tianji schema analysis_start_v2
./tianji call analysis_start_v2 --json '{"request":{"vision":"Reduce community heat risks"}}'
./tianji call job_get --json '{"id":"JOB_ID"}'
```

The CLI and MCP discover the same authenticated registry as the Web. `POST /api/operations/{name}`
accepts an argument object and optional mutation request ID. A queued job is not complete: read it back
with `job_get` or the relevant `*_get` operation. Retry uncertain mutations with the same request ID
and identical arguments; errors are nonzero/explicit. Do not retry a model call as if it were a
cached mutation.

MCP launches the local service through the repository's backend module; supply `TIANJI_TOKEN` via the
client's secret configuration. The [execution contract](specs/lab/execution-contract.md) defines
schemas, auth, idempotency and error behavior.

## Runtime interface and checks

The runtime view shows device UTC using locally bundled nixie PNGs from the pinned
[DivergenceMeter source chain](../web/public/vendor/divergencemeter/README.md). It is a clock, not a
prediction score. GIF/audio and external feeds are excluded. Reduced motion and hidden-tab behavior
are supported.

Use the test, lint and build commands in the root [README](../README.md). Run real API/browser checks
when behavior changes. Do not create permanent reports, screenshot archives or prompt dumps.