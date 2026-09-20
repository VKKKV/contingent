# Contingent

A local-first workbench for **goal-directed scenario analysis and backcasting**.

Describe an objective, time horizon, stakeholder perspective and constraints. Contingent uses a local
language model to propose alternative intervention pathways, then visualizes their dependencies,
actors, assumptions, risks and observable indicators.

Generated pathways are hypotheses for analysis—not validated causal models, calibrated forecasts
or guarantees of success. There is currently no live evidence retrieval or automated fact checking.

Repository: https://github.com/VKKKV/contingent

The product was formerly named TianJi. Existing `tianji_lab` imports, `./tianji` CLI,
`TIANJI_*` environment keys, browser storage keys and stored data identifiers remain unchanged
for compatibility; this is a product/repository rename, not a data migration.

## Quick start

Requirements: Python 3.12+, uv, Node 22.12+, Bash and a POSIX host. Local inference also requires
llama.cpp and an existing GGUF model.

```bash
./start.sh
./start.sh --model /path/to/model.gguf
./start.sh --no-model
```

The default model path is `~/models/Qwen3.5-9B/Qwen3.5-9B-Q4_K_M.gguf`. The launcher synchronizes
dependencies, builds the web application and waits for service readiness; it does not download a
model. Open the displayed URL and enter the token from the displayed file into the connection form.
Ctrl+C stops the services started by the launcher, not unrelated processes.

Overrides: `TIANJI_MODEL_PATH`, `TIANJI_PORT`, `TIANJI_MODEL_PORT`, `TIANJI_DATA_DIR` and
`TIANJI_GPU_LAYERS` (`0` for CPU inference). Occupied ports cause an explicit startup failure.
With `--no-model`, saved analyses remain available in the Web; deterministic supply-chain
operations remain available through HTTP, CLI and MCP, without a dedicated Web page.

## Web workflow

1. Enter an objective, time horizon, stakeholder perspective and constraints. Creating a new
   analysis project explicitly saves that request and starts bounded background work.
2. Inspect the actual framing, strategy, critic, optional revision and synthesis tasks. Switch
   between task dependencies and the issue graph; select nodes to read structured contributions.
3. Cancel running work or reopen a project from the saved list. Partial/interrupted results retain
   completed contributions and unresolved objections rather than fabricating a finished answer.

See [bounded analysis](docs/bounded-analysis.md) for budgets, persistence and cancellation.
The legacy single-call analysis remains separately available: its five-node/two-path scaffold is
not a discovered causal topology, and it still saves only on explicit request. The former
supply-chain Web page is removed; its deterministic kernel, stored data and HTTP/CLI/MCP operations
remain compatible and do not validate open-ended scenario analysis.

## Interface and runtime instrumentation

The runtime clock uses original static nixie PNGs from the pinned GPLv3
[DivergenceMeter source chain](web/public/vendor/divergencemeter/README.md), with full notices
and file hashes retained. It displays device time in UTC as `HH.MM.SS`, not a prediction score
or statistics disguised as divergence. No external time service, original GIF/audio or news
feed is used. Runtime counts are secondary and scoped to legacy saved analyses; new task status
is shown in the analysis workspace. Reduced motion and mobile layouts are supported.
The meter uses full-viewport composition and original image proportions. A locally bundled,
lazy-loaded tsParticles background replaces the CSS imitation; reduced motion disables it and
hidden tabs pause it. Analysis forms, diagrams and reports share the black/orange theme. Live
browser checks cover desktop/mobile, navigation, focus and real saved-result readback. Side-by-side
meter inspection does not establish pixel-identical reproduction across every application state;
remaining boundaries are in [the development plan](docs/development-plan.md).

New analysis projects execute **separate bounded same-model agent calls** through PydanticAI.
Task dependencies and issue relations are different graphs, rendered using React Flow/Dagre.
This is not independent evidence: the roles share a local model, and no live researcher, factual
retrieval or independent fact checking runs behind them. Legacy saved drafts stay single-call
results without invented task histories.

## Command-line control

The CLI discovers the running server's capability registry and can invoke **every registered
operation**, including analysis, model proposals, scenarios, jobs, branches and workspace controls.
Start the server first. From the repository root:

```bash
./tianji health
./tianji operations
./tianji schema analysis_start
./tianji call analysis_start --json '{"request":{"vision":"Reduce community heat risks","horizon":"Next two summers"}}'
./tianji call analysis_list
./tianji call vision_generate --json '{"vision":"Reduce conflict risks associated with AI deployment","horizon":"Next ten years"}'
./tianji call scenario_list
./tianji call job_get --json '{"id":"YOUR_JOB_ID"}'
```

The `vision_*` operation names and `vision` input key are retained as compatibility identifiers;
product terminology is **goal-directed scenario analysis**. No existing stored objects are renamed.

Use `--file arguments.json` or `--stdin` for larger argument objects. These contain operation
arguments, not the HTTP envelope. Output is JSON; errors return a nonzero exit status. Mutation
request IDs support idempotent retries—keep the same ID and arguments when retrying an uncertain
write. The CLI does not retry automatically or equate a queued job with completion.

See [the operating guide](docs/laboratory.md) for authentication, examples and local model setup.
Use `./tianji --help` and `./tianji call --help` for connection and input options.

## Development

```bash
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run format:check
npm --prefix web run build
```

Python/FastAPI/SQLite live in `backend/`; the React/TypeScript workbench lives in `web/`.
Web, CLI and MCP share the HTTP operation registry and server-side validation.
Normal tests do not create mandatory reports, screenshot archives or prompt/response logs.
Explicitly created analysis projects, saved legacy drafts, scenarios, branches and adjudications
are product data. Internal prompt/response transcripts are not persisted.

See the [execution contract](docs/specs/lab/execution-contract.md) for schemas and behavior.
