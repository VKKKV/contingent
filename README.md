# Contingent

Contingent is a local-first workbench for goal-directed scenario analysis and backcasting.
Describe an objective, optional horizon and constraints; the system proposes alternative pathways,
actors, assumptions, risks and observable signals.

Product intent: [goal.md](goal.md). Current implementation: [handoff.md](handoff.md).

Generated pathways are hypotheses, not validated causal models, calibrated forecasts or guarantees.
V2 can retrieve bounded public sources and retain exact passages for citations; citation traceability
is not fact checking. Existing `tianji_lab` imports, `./tianji`, `TIANJI_*` keys, browser storage and
stored IDs remain compatible with the Contingent product/repository rename.

## Quick start

Requirements: Python 3.12+, uv, Node 22.12+, Bash and a POSIX host. Model-backed runs also need
llama.cpp and an existing GGUF model.

```bash
./start.sh
./start.sh --model /path/to/model.gguf
./start.sh --no-model
```

The launcher syncs dependencies, builds the Web app and waits for readiness; it does not download a
model. The default model is `~/models/Qwen3.5-9B/Qwen3.5-9B-Q4_K_M.gguf`. Open the printed URL and
enter the token from the printed token file. Ctrl+C stops only services started by the launcher.

Configuration overrides: `TIANJI_MODEL_PATH`, `TIANJI_PORT`, `TIANJI_MODEL_PORT`,
`TIANJI_DATA_DIR` and `TIANJI_GPU_LAYERS` (`0` for CPU inference). `--no-model` still serves saved
analyses and deterministic HTTP/CLI/MCP operations. Do not put private information in online queries.

## Web workflow

1. Enter an objective. New v2 projects default to bounded online research; choose offline mode when
   external queries are not wanted. The UI discloses query externalization and local snapshots.
2. Inspect framing, strategies, critique, optional revision and synthesis. Task dependencies and the
   issue graph are separate; select nodes to inspect structured contributions and citations.
3. Reopen saved projects or cancel running work. Partial/interrupted runs retain completed results and
   unresolved objections; they do not fabricate a finished answer.

See [bounded analysis](docs/bounded-analysis.md) for execution semantics and
[online research](docs/research-integration.md) for source limits and privacy boundaries.

Legacy `vision_*` generation remains a single-call, explicit-save workflow. Its five-node/two-path
shape is a presentation scaffold, not discovered causality. The former supply-chain Web page is
removed, but its deterministic kernel and HTTP/CLI/MCP operations remain compatible.

## Runtime interface

The runtime clock uses locally bundled static nixie PNGs from the pinned GPLv3
[DivergenceMeter source chain](web/public/vendor/divergencemeter/README.md). It displays device UTC
as `HH.MM.SS`, not a score or divergence measurement. GIF/audio, external time services and news
feeds are excluded. Reduced motion and mobile layouts are supported; tsParticles is local and lazy.

## CLI

Start the server first. The CLI discovers the live operation registry; it does not maintain a second
operation list.

```bash
./tianji health
./tianji operations
./tianji schema analysis_start_v2
./tianji call analysis_start_v2 --json '{"request":{"vision":"Reduce community heat risks","horizon":"Next two summers"}}'
./tianji call analysis_list_v2
./tianji call vision_generate --json '{"vision":"Reduce conflict risks associated with AI deployment","horizon":"Next ten years"}'
./tianji call scenario_list
./tianji call job_get --json '{"id":"JOB_ID"}'
```

Use `--file arguments.json` or `--stdin` for larger argument objects; these are operation arguments,
not an HTTP envelope. Output is JSON, errors return nonzero, and a queued job is not completion.
Keep the same mutation request ID and arguments when retrying an uncertain write.

`vision_*` names and the `vision` input key are compatibility identifiers. See
[the laboratory guide](docs/laboratory.md) for authentication, MCP and local model setup.

## Development checks

```bash
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run format:check
npm --prefix web build
```

Python/FastAPI/Pydantic/SQLite live in `backend/`; React/TypeScript/Vite lives in `web/`.
Web, CLI and MCP share the HTTP operation registry and validation. Normal checks do not create
mandatory reports, screenshots or prompt/response archives.

Documentation map: [docs/README.md](docs/README.md).