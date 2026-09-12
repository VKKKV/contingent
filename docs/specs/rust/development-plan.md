# TianJi Development Plan

## Authority

Root `plan.md` is the authoritative architecture and roadmap document for TianJi.
It defines the four subsystems (Cangjie, Fuxi, Hongmeng, Nuwa), implemented
Rust surfaces, current dependency list, verification criteria, and next-phase
roadmap.

**Python oracle retired in Phase 6 (v0.2.0).** All Rust parity gates have passed.
The project is now a pure Rust binary. Historical verified snapshot after Phase F
(root `plan.md` is authoritative for current status):
56 Rust source files, 25,398 Rust source lines, 24 manifest dependencies, and
341 unit + 39 integration tests passing.

## Migration Alignment

`plan.md` defines this build order and current status:

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Worldline core + pipeline (Cangjie/Fuxi) | Milestone 1A+1B complete |
| 2 | Storage + History | Milestone 2 complete |
| 3 | Local Runtime (daemon + API + webui) | Milestone 3 complete |
| 3.5 | Crucix Delta Engine | Complete |
| 4 | TUI (ratatui + Kanagawa Dark) | Milestone 4 complete |
| 5 | Hongmeng orchestration + Nuwa simulation | Complete |
| 6 | Cleanup + docs (Python retirement) | Complete |
| A | Immediate cleanup hardening | Complete |
| B | Code quality hardening | Complete |
| C | Architecture cleanup | Complete |
| D | Production features | Complete |
| E | Agent integration + simulation auditability | Complete |
| F | Product polish + operator readiness | Complete |
| G | Roadmap + spec authority refresh | Complete |
| H | Evaluation harness | Complete |
| I | Source/feed management | Complete |
| J | Operational reliability | Complete |
| K | Simulation replay/export | Complete |

### Milestone 1A — Feed + Normalization Parity

**Complete.** Replaced the Milestone 0 scaffold with real deterministic feed
parsing, canonical hashing, and normalized event emission.

- RSS 2.0 and Atom 1.0 local fixture parsing ✅
- SHA-256 entry identity and content hashes ✅
- Deterministic normalization: keywords, actors, regions, field scores, event IDs ✅
- Normalized-event-shaped payloads emitted through the Rust artifact ✅

### Milestone 1B — Scoring + Grouping + Backtracking Parity

**Complete.** Rust one-shot output is deterministic and verified.

- `Im` / `Fa` scoring semantics and rationale vocabulary ✅
- Event grouping, causal/evidence summaries ✅
- Backtrack intervention candidates ✅
- Full `RunArtifact` field-for-field parity verified ✅

### Milestone 2 — Storage + History Parity

**Complete.** Ported the durable local read model with field-for-field parity.

- SQLite persistence: 6 tables (`runs`, `source_items`, `raw_items`, `normalized_events`, `scored_events`, `intervention_candidates`) ✅
- `PRAGMA foreign_keys = ON`, atomic transactions, canonical source item deduplication ✅
- Event groups recomputed on read (LiveStore principle: never persist derived values) ✅
- `history`: list/filter runs with filter-before-limit semantics ✅
- `history-show`: single-run detail with scored-event/intervention/event-group projection lenses ✅
- `history-compare`: pair comparison with diff computation and presets ✅
- CLI: clap subcommands (`run`, `history`, `history-show`, `history-compare`) ✅

#### Storage Read-Model Paging Contract

`list_runs(sqlite_path, limit, filters)` preserves the shipped history contract:
filters are applied before final limit truncation. To avoid loading an unbounded
SQL result set into memory, filtered reads page through `runs` in deterministic
`ORDER BY id DESC` order using bounded `LIMIT/OFFSET` queries, apply Rust-side
filters per page, and stop only after collecting `limit` matching rows or
exhausting the table. Do not add a hard max scanned-row cap, because that can
silently violate filter-before-limit semantics when a matching run exists beyond
the cap.

```rust
// Correct: bounded SQL pages, unbounded logical scan until enough matches or EOF.
while items.len() < limit {
    let rows = query_run_list_rows(connection, PAGE_SIZE, offset)?;
    if rows.is_empty() {
        break;
    }
    items.extend(filter_run_list_items(build_run_list_items(connection, &rows)?, filters));
    offset += rows.len();
}
items.truncate(limit);
```

Tests must cover a filtered match that appears beyond the first SQL page.

### Milestone 3 — Local Runtime Parity

**Complete.** Ported the thin local runtime with behavior parity.

- Daemon core: in-memory job queue, worker loop, subprocess model ✅
- UNIX socket control plane: JSON-lines protocol, queue/status actions ✅
- HTTP read API: axum routes with stable response envelope ✅
- Web UI: compile-time embedded static files, API proxy, queue-run ✅
- CLI: daemon lifecycle commands, `webui`, PID file management ✅
- Bounded schedule helpers ✅

### Milestone 3.5 — Cross-Run Delta Engine

**Complete.** Adds a Crucix-inspired cross-run analysis layer on top of the
persisted SQLite read model without changing the six-table schema. Persisted
runs update hot memory, classify alert tiers, and expose delta summary through
daemon job status and the read API.

Key contracts:

- `compute_delta` returns `None` when no previous run is available.
- Numeric and count delta outputs are deterministic and sorted by stable metric definitions.
- New-signal identity uses persisted scored-event fields from `get_run_summary`.
- Hot memory stores compact runs newest-first and writes atomically with `.bak` fallback.
- Alert pruning uses persisted run timestamps, not wall-clock time, so fixture runs stay deterministic.
- API run-summary routes apply explicit bounded scored-event and event-group limits.
- CLI/history-show defaults remain unbounded unless the caller provides an explicit limit.
- Daemon successful job status includes `delta_tier` and `delta_summary` fields.
- `GET /api/v1/delta/latest` returns latest delta/tier and returns null fields when no delta exists.

### Milestone 4 — TUI (ratatui + Kanagawa Dark)

**Complete.** Ratatui TUI is implemented with Kanagawa Dark styling, Vim-style
navigation, history/detail/compare views, simulation view, search/filter,
fallback rendering, half-page scroll, and replay cursor scrubbing.

### Milestone 5 — Hongmeng/Nuwa + Local Runtime Completion

**Complete.** LLM provider configuration, optional real provider chat, Hongmeng
agent orchestration, Nuwa simulation sandbox, daemon/web UI integration, and
TUI simulation surfaces are implemented.

### Milestone 6 — Cleanup

**Complete.** Python oracle retired, shell completions added, documentation updated.

- Delete Python code and caches ✅
- Update README/operator docs ✅
- Shell completions (clap_complete) ✅
- Preserve single-binary Rust deployment model ✅

## Post-v0.2.0 Hardening Progress

Historical post-v0.2.0 hardening notes through Phase F are retained below for
context. Root `plan.md` remains the authority for the current roadmap. As of
2026-05-20:

### Phase A — Immediate Cleanup

**Complete.** Input bounds and cleanup guardrails are in place.

- `MAX_RAW_ITEMS` limits feed parsing to 500 raw items ✅
- `MAX_SCORED_EVENTS` limits pipeline/persistence output to 500 scored events ✅
- Deprecated delta-memory wall-clock helpers removed from public use ✅
- `fetch` and `normalize` share `utils::clean_text` trim/collapse semantics ✅
- `TianJiError::DataIntegrity` represents integrity failures directly ✅

### Phase B — Code Quality

**Complete.** Code-quality cleanup is landed.

- Shared `time_utils` module for ISO/RFC timestamp parsing and day math ✅
- Async TUI detail/compare data loading with loading indicators ✅
- Structured logging through `tracing` / `RUST_LOG` ✅
- Configurable `ScoreParams` with default backward-compatible scoring ✅

### Phase C — Architecture

**Complete.** Architecture cleanup is landed.

- Hongmeng agent private state and board stick values use strong types while keeping JSON compatibility at boundaries ✅
- TUI view-state dispatch preserves per-view state and reduces monolithic state coupling ✅
- Nuwa forward loop shares `tick_simulation` core logic ✅
- `sandbox::fork_worldline` and `WorldlineStore` unify worldline branching ✅

### Phase D — Production & Features

**Complete.** D1-D8 are implemented.

- D1: storage history integration coverage ✅
- D2: ActorProfile YAML validation ✅
- D3: SQLite connection pool for long-lived API/daemon paths ✅
- D4: Ollama `/api/chat` structured-message migration ✅
- D5: LLM concurrency limiting via `tokio::sync::Semaphore` ✅
- D6: explicit worldline `causal_graph` serialization contract ✅
- D7: alert dispatch to external channels ✅
- D8: fast/slow feed tier separation ✅

### Phase E — Agent Integration & Simulation Auditability

**Complete.** Signed local command ingress, structured agent output, and TUI
snapshot replay are implemented and contract-tested.

### Phase F — Product Polish & Operator Readiness

**Complete.** Config doctor, credential-free sample config, API contract
fixtures, README operator quickstart, shell completions verification, fixture
smoke run, release build, and release checklist are complete.

### Historical Phase F Verification Baseline

- `cargo build --release`: pass ✅
- `cargo test --quiet`: 341 unit + 39 integration passed / 0 failed ✅
- `cargo clippy -- -D warnings`: pass ✅
- `git diff --check`: pass ✅
- Release binary: 15,338,616 bytes / 14.63 MiB (< 25 MB) ✅

## Dependency Guidance

The dependency list in root `plan.md` is the target. Each milestone should add
only the dependencies it needs. Do not add async runtimes, web frameworks, TUI
crates, graph engines, or LLM provider crates without a scoped milestone and
local-first verification plan.

## Documentation Rules

- `plan.md` is the authority for architecture, project structure, and build phases.
- The spec documents in `docs/specs/` should be updated before claiming a Rust layer is current.
- Historical Python-oracle references must be explicitly labelled as historical/superseded.
- New examples should use `cargo run -- ...` or `tianji ...`, not `python3 -m tianji`.

## Guardrails

- Keep first-party Rust source under `src/`.
- Avoid framework-first expansion — add dependencies per milestone.
- Every new layer should preserve local-first, deterministic-first behavior.
- No tests should depend on public network, live LLM providers, or real credentials.
