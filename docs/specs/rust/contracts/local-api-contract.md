# TianJi Local API Contract (v1)

## Purpose

This document defines the shipped local HTTP API contract for TianJi.

TianJi now ships a narrow read-first loopback HTTP API inside the local daemon/server boundary. This document preserves alignment between:

- the current CLI operator surface
- the current SQLite-backed run-history surface
- the shipped local API layer for a decoupled web UI or other local readers

The shipped startup contract is the daemon runtime path: `tianji daemon start --sqlite-path runs/tianji.sqlite3 --socket-path runs/tianji.sock --host 127.0.0.1 --port 8765`, which keeps the UNIX socket control plane and binds the read API at `http://127.0.0.1:8765/api/v1` by default.

## Design Principles

1. **CLI remains the source of truth for writes first**
   - The current product surface is `tianji run ...` (Rust binary).
   - The first local API slice should be read-first.

2. **Reuse existing artifact and history shapes**
   - Do not invent a separate domain model for the API if the CLI/storage payloads are already stable enough.
   - Field names should stay aligned with current output such as `schema_version`, `scenario_summary`, `scored_events`, and `intervention_candidates`.

3. **Local-only assumptions**
   - No cloud dependency, auth layer, or distributed service assumptions in this contract.
   - The API is loopback-only and hosted by the local daemon process.

4. **Read-only first**
   - Expose current persisted data and metadata first.
   - Defer write-triggering endpoints until a broader local service runtime exists.

## Current Stable Backend Surfaces

These are the current product-aligned surfaces the shipped API mirrors:

- `tianji run ...`
  - one synchronous pipeline execution
  - emits one schema-versioned artifact

- `tianji history --sqlite-path ...`
  - lists persisted runs from SQLite

- `tianji history-show --sqlite-path ... --run-id N`
  - returns persisted run-level detail
  - includes `input_summary`, `scenario_summary`, `scored_events`, and `intervention_candidates`

- `tianji history-compare --sqlite-path ...`
  - compares two persisted runs, or resolves relative/latest compare presets first
  - reuses the same scored-event and event-group projection vocabulary as `history-show`
  - confirms that compare is already part of the mirrored backend surface that the first API slice must name explicitly for direct pair comparison

## Shipped API Resources

### 1. `GET /api/v1/meta`

Purpose:
- expose static contract metadata for a future UI
- avoid implying live runtime or job status through this read-first metadata route

Response shape:

```json
{
  "api_version": "v1",
  "data": {
    "cli_source_of_truth": true,
    "artifact_schema_version": "tianji.run-artifact.v1",
    "persistence": {
      "sqlite_optional": true
    }
  },
  "error": null
}
```

### 2. `GET /api/v1/runs?limit=N`

Purpose:
- API form of current `history`

Contract:
- `limit` is optional and defaults to the backend history default.
- `limit <= 0` is invalid and returns an API error envelope.
- Implementations must cap excessive positive `limit` values to a bounded maximum before calling storage. The Rust implementation currently caps at `200` to keep the local read API from allocating unbounded result vectors.
- Storage may push `LIMIT` into SQL when no read-time filters are active. If filters are active, preserve filter-before-limit semantics rather than returning the first N rows before filtering.

Recommended `data` shape:

```json
[
  {
    "run_id": 3,
    "schema_version": "tianji.run-artifact.v1",
    "mode": "fixture",
    "generated_at": "2026-03-22T10:00:00+00:00",
    "raw_item_count": 3,
    "normalized_event_count": 3,
    "dominant_field": "technology",
    "risk_level": "high",
    "headline": "The strongest current branch is technology..."
  }
]
```

### 3. `GET /api/v1/runs/{run_id}`

Purpose:
- API form of current `history-show`

Recommended `data` shape:
- `run_id`
- `schema_version`
- `mode`
- `generated_at`
- `input_summary`
- `scenario_summary`
- `scored_events`
- `intervention_candidates`

This endpoint should preserve the current persisted detail vocabulary rather than remapping fields.

### 4. `GET /api/v1/runs/latest`

Purpose:
- convenience alias for the newest persisted run

Notes:
- implemented as an optional convenience route in the first implementation
- should return the same payload shape as `GET /api/v1/runs/{run_id}`
- undefined when no persisted runs exist yet

### 5. `GET /api/v1/compare?left_run_id=<id>&right_run_id=<id>`

Purpose:
- API form of the existing explicit-pair `history-compare` surface
- keep the web UI thin by reusing the frozen compare payload vocabulary directly

Notes:
- this freezes exactly one compare route name for v1
- latest/relative compare preset routes stay CLI/storage concerns unless a future PRD scopes API aliases
- the `data` payload should mirror `history_compare_v1.json` field names rather than remapping compare-side or diff vocabulary

### 6. `GET /api/v1/health`

Purpose:
- liveness probe for the local API process
- does not query SQLite

### 7. `GET /api/v1/ready`

Purpose:
- readiness probe for SQLite-backed API serving
- checks pool checkout plus a trivial SQLite query

### 8. `GET /api/v1/delta/latest`

Purpose:
- expose the latest local delta report from hot memory for local dashboards

### 9. `POST /api/v1/agent/command`

Purpose:
- optional HMAC-signed local agent command ingress
- disabled when no command secret is configured
- remains loopback/local-only and preserves replay protection

## Frozen v1 Vocabulary Fixtures

The v1 vocabulary is frozen by checked-in machine-readable fixtures:

- `tests/fixtures/contracts/run_artifact_v1.json`
  - top-level `RunArtifact.to_dict()` vocabulary
- `tests/fixtures/contracts/history_list_item_v1.json`
  - persisted `history` list-item vocabulary
- `tests/fixtures/contracts/history_detail_v1.json`
  - persisted `history-show` detail vocabulary
- `tests/fixtures/contracts/history_compare_v1.json`
  - persisted `history-compare` side/diff vocabulary
- `tests/fixtures/contracts/local_api_meta_v1.json`
  - frozen `/api/v1/meta` envelope + resource manifest vocabulary
- `tests/fixtures/contracts/local_api_runs_v1.json`
  - frozen `/api/v1/runs` envelope/resource vocabulary
- `tests/fixtures/contracts/local_api_compare_v1.json`
  - frozen compare route and envelope vocabulary for `GET /api/v1/compare?left_run_id=<id>&right_run_id=<id>`

These fixtures intentionally freeze field vocabulary and envelope/resource names for the shipped read-only runtime.

## Response Envelope

To keep future UI consumers stable, use one envelope pattern for all responses:

```json
{
  "api_version": "v1",
  "data": {},
  "error": null
}
```

Error example:

```json
{
  "api_version": "v1",
  "data": null,
  "error": {
    "code": "run_not_found",
    "message": "Run not found: 7"
  }
}
```

## Compare Vocabulary Freeze Before Runtime

`history-compare` is part of the current mirrored backend read surface, so its payload vocabulary is frozen now through `tests/fixtures/contracts/history_compare_v1.json`.

For the first local API contract, compare is frozen as **exactly one explicit v1 route**:

- mirrored backend surface: `history-compare`
- v1 HTTP route: `GET /api/v1/compare?left_run_id=<id>&right_run_id=<id>`
- compare route fixture marker: `tests/fixtures/contracts/local_api_compare_v1.json`

This means future daemon/API work must preserve the frozen compare side/diff field names and expose that exact explicit-pair route, while still deferring compare preset routes such as latest-pair or relative-run shortcuts.

## What To Defer

Do **not** include these in the first local API slice:

- live progress or status endpoints over HTTP
- WebSocket streaming
- scheduler or daemon control endpoints
- source-registry management endpoints
- compare preset routes across runs beyond the explicit pair route, even though `history-compare` already exists in the CLI/storage mirror surface
- standalone resources for `event_groups`, `scored_events`, or `intervention_candidates`
- auth, users, sessions, or multi-tenant concepts

These either do not exist in the current product surface or would force architecture choices beyond the shipped read-only loopback runtime.

## Mapping to Current TianJi Code

- `src/main.rs`
  - current operator commands: `run`, `history`, `history-show`, `history-compare`, `daemon`, `webui`, `tui`, `delta`, `predict`, `backtrack`, `baseline`, `watch`, `doctor`, `eval`, `sources`, `maintenance`, and `completions`

- `src/lib.rs` plus pipeline modules (`fetch`, `normalize`, `scoring`, `backtrack`)
  - define the unit of work: one run -> one artifact

- `src/models.rs`
  - current artifact schema vocabulary

- `src/storage.rs`
  - current persisted read/write boundary for runs, run details, and run comparison payloads

## Risks to Avoid

1. **Shape drift**
   - If API payloads diverge from CLI artifact/history payloads too early, TianJi will maintain two domain models for the same concept.

2. **Premature live-runtime assumptions**
   - Current TianJi is still CLI-first. Avoid exposing daemon job semantics through the HTTP API just because the loopback daemon boundary now exists.

3. **Overcommitting writes**
   - A future `POST /runs` may exist, but the first shipped contract does not require it before the broader local service boundary is ready.

## Shipped Implementation Order

The first shipped local API slice follows this order:

1. `GET /api/v1/meta`
2. `GET /api/v1/health`
3. `GET /api/v1/ready`
4. `GET /api/v1/runs`
5. `GET /api/v1/runs/latest`
6. `GET /api/v1/runs/{run_id}`
7. `GET /api/v1/compare?left_run_id=<id>&right_run_id=<id>`
8. `GET /api/v1/delta/latest`
9. optional `POST /api/v1/agent/command` when command secret configuration is available

This keeps the first API slice aligned with the current stable product reality: read-first, local-first, deterministic, loopback-only, and optional for operators who only need the CLI or TUI.
