# TianJi (天机) — Development Plan v6

> New direction approved 2026-09-10: **Bidirectional World Simulation Laboratory**, Web-first and agent-operable, implemented with TypeScript/React + Python/FastAPI. M1 and the exogenous-disturbance slice are delivered and verified on branch `feat/world-simulation-lab` (status and evidence in handoff.md; slice records under [docs/milestones/](docs/milestones/)). The active implementation authority for new `backend/` and `web/` code is [m1-contract.md](docs/milestones/2026-09-m1-world-simulation-lab/m1-contract.md), extended by [m2-contract.md](docs/milestones/2026-09-m2-exogenous-disturbances/m2-contract.md) and [execution-contract.md](docs/specs/lab/execution-contract.md), with broader design in [architecture.md](docs/milestones/2026-09-m1-world-simulation-lab/architecture.md).
> The remainder of this file records the **legacy Rust v0.2 baseline**, not a requirement to port heuristic probabilities or CLI-first behavior into the new product. Rust source and existing databases are preserved; no destructive migration is authorized. M1 delivery status must be verified by real tests and browser operation, not inferred from this approval.

> Branch: `main` | Updated: 2026-06-09
> Target: 智库级信号分析引擎 — 确定性管线 + 跨 run 变化追踪 + 多 Agent 仿真
> Current: Core Rust product, Phase A/B/C/D/E hardening, Phase F operator readiness, Phase G roadmap/spec authority refresh, release-readiness gate, Phase H evaluation harness, Phase I source/feed management, Phase J operational reliability, and Phase K simulation replay/export with TUI replay/audit viewer complete.
> Tests: 445 cargo tests across 3 suites pass / 0 fail (replay/audit and CLI guard coverage)

---

## 1. Current State

```
M1A ████████████████████ ✅ Feed + Normalization
M1B ████████████████████ ✅ Scoring + Grouping + Backtrack
M2  ████████████████████ ✅ Storage + History CLI
M3A ████████████████████ ✅ Daemon + Local API
M3B ████████████████████ ✅ Optional Web UI
M3C ████████████████████ ✅ Bounded schedule
M3.5████████████████████ ✅ Crucix Delta Engine
TUI ████████████████████ ✅ 4 views + search + fallback + scroll
 2.1 ████████████████████ ✅ LLM Provider + Config
 2.2 ████████████████████ ✅ Worldline + Baseline
 2.3 ████████████████████ ✅ Actor Profiles (3 tiers, 8 YAML)
 2.4 ████████████████████ ✅ Hongmeng Orchestration
 2.5 ████████████████████ ✅ Nuwa Simulation Sandbox
 3.0 ████████████████████ ✅ Real LLM chat() via reqwest
 3.1 ████████████████████ ✅ CLI: predict/backtrack/baseline/watch
 3.2 ████████████████████ ✅ TUI Simulation view
 4.0 ████████████████████ ✅ Agent LLM integration (stub→real)
 4.1 ████████████████████ ✅ Rich TUI Dashboard
 4.2 ████████████████████ ✅ TUI Search/Filter
 4.3 ████████████████████ ✅ Nerd Font / ASCII fallback
 4.4 ████████████████████ ✅ Ctrl+d/u half-page scroll
 4.5 ████████████████████ ✅ TUI submodule split
 5.1 ████████████████████ ✅ Live feed watch e2e test
 5.2 ████████████████████ ✅ Worldline SQLite persistence
 5.3 ████████████████████ ✅ Human-in-the-loop pruning (TUI ↔ Sim)

Phase F ████████████████████ ✅ Product polish + operator readiness
Phase G ████████████████████ ✅ Roadmap/spec authority refresh
Phase H ████████████████████ ✅ Evaluation harness
Phase I ████████████████████ ✅ Source/feed management
Phase J ████████████████████ ✅ Operational reliability
Phase K1████████████████████ ✅ Simulation JSONL trace export
Phase K2████████████████████ ✅ Replay bundle packaging
Phase K3████████████████████ ✅ TUI trace-backed replay loading
Phase K4████████████████████ ✅ Structured agent audit viewer
```

  源码: 30,465 行 Rust / 59 源文件
  测试: 445 cargo tests across 3 suites pass / 0 fail
  构建: cargo build --release + clippy -D warnings zero
  依赖: 24 manifest dependencies
  Python: 已退役
  Release binary: 16,245,408 bytes / 15.49 MiB (< 25MB)

### Phase A — Immediate Cleanup (COMPLETE)

**A1. Input size limits** ✅
- `MAX_RAW_ITEMS` and `MAX_SCORED_EVENTS` cap oversized feeds/pipeline output.

**A2. Remove deprecated delta_memory functions** ✅
- Timestamp-injected `_at` variants are the only public alert suppression/marking path.

**A3. Unify clean_text** ✅
- `fetch` and `normalize` share `utils::clean_text` with trim/collapse semantics.

**A4. TianJiError::DataIntegrity variant** ✅
- Storage/worldline integrity failures now use a first-class error variant.

### Phase B — Code Quality (COMPLETE)

**B1. Extract time_utils module** ✅
- Consolidated ISO/RFC timestamp parsing and days-since-epoch helpers into `src/time_utils.rs`.

**B2. Async TUI data loading** ✅
- Background threads for detail/compare SQLite queries.
- mpsc channel polling in event loop, "loading..." indicator in title bar.

**B3. Structured logging** ✅
- All `eprintln!` calls replaced with `tracing::{error,warn}`.
- `tracing_subscriber::fmt` with `RUST_LOG` env-var support.

**B4. Scoring parameters configurable** ✅
- `src/scoring_params.rs`: `ScoreParams` with `Default` + YAML deserialization.
- All scoring functions threaded with `&ScoreParams`.
- Backward-compat `score_events()` uses default params.

### Phase C — Architecture (COMPLETE)

**C1. H8: serde_json::Value → strong types** ✅
- Hongmeng agent private state and board stick values use typed Rust structures.
- Legacy JSON compatibility remains at API/prompt boundaries.

**C2. TUI view state decoupling** ✅
- View state preserved through dispatch; TUI state no longer relies on one monolithic mode bag.

**C3. forward.rs deduplication** ✅
- Shared Nuwa forward tick logic extracted into `tick_simulation`.

**C4. fork_worldline unification** ✅
- Worldline branching flows through `sandbox::fork_worldline` and `WorldlineStore`.
- Failure contract documented; SQLite coupling removed from Nuwa simulation signatures.

### Phase D — Production & Features (COMPLETE)

**D1. Integration test coverage** ✅
- Added end-to-end storage history coverage for `persist_run → get_run_summary → compare_runs`.

---

## 2. Architecture (Implemented)

```
RSS/Atom XML
  │  roxmltree parse + SHA-256 canonical hash
  ▼
Vec<RawItem>
  │  LazyLock regex: keywords, actors, regions, field_scores
  ▼
Vec<NormalizedEvent>
  │  Im = actor_weight + region_weight + keyword_density + ...
  │  Fa = dominant_field_strength + dominance_margin + ...
  │  divergence_score = f(Im, Fa)
  ▼
Vec<ScoredEvent>
  │  shared signals + 24h time window → event groups
  │  dominant_field → intervention candidates
  ▼
RunArtifact JSON ──────────────────────────► stdout
  │
  ├─ [optional] SQLite persist (6 tables) → history / compare
  │
  └─ [optional] Delta Engine
       ├─ compute_delta(prev, current) → DeltaReport
       ├─ HotMemory (hot/cold storage, atomic I/O)
       ├─ AlertDecayModel (0h/6h/12h/24h cooldown)
       └─ AlertTier: Flash / Priority / Routine
```

四子系统:
- Cangjie (仓颉): Feed → Normalize (已实现)
- Fuxi (伏羲): Scoring → Backtrack → Delta (已实现)
- Hongmeng (鸿蒙): Agent 编排层 (已实现, LLM stub+real)
- Nuwa (女娲): 仿真沙盒 (已实现, forward+backward+interactive)

---

## 3. Development Roadmap (v6)

The core Rust engine, Phase F release-readiness checkpoint, and Phase K
replay/audit work are complete. Development now moves from product completion to
post-K release polish and quality governance: reproducible evaluation, source
management, operational reliability, and local-first operator documentation.

### Completed hardening

- Phase A: input limits, delta-memory cleanup, shared text normalization,
  first-class data-integrity errors.
- Phase B: shared time utilities, async TUI data loading, structured logging,
  configurable scoring parameters.
- Phase C: typed Hongmeng state, TUI view-state decoupling, Nuwa tick
  deduplication, unified worldline forking.
- Phase D: D1-D8 production features complete.
- Phase E: agent command channel, structured simulation auditability, timeline replay.
- Phase F: operator readiness, API contracts, release checklist, release gate.
- Phase G: roadmap and spec authority refresh after Phase F.
- Phase H: deterministic fixture evaluation, golden snapshots, drift reporting.
- Phase I: source registry, local fixture fan-in, live fetch opt-in, source health.
- Phase J: SQLite retention policy and daemon health/readiness probes.
- Phase K: simulation JSONL trace export, replay bundle packaging, TUI replay
  loading, and structured agent audit viewer.

### Phase D — Completed Production & Features

**D2. ActorProfile YAML validation** ✅
Files: `src/profile/types.rs`, `src/profile/registry.rs`
- Profile semantic validation at load time.
- Rejects malformed salience/capability values with path/id/field context.

**D3. SQLite connection pool** ✅
Files: `src/api.rs`, `src/daemon.rs`, `src/storage.rs`
- Long-lived API/daemon paths use a bounded SQLite pool.
- CLI path-based helpers remain available for one-shot usage.

**D4. Ollama /api/chat migration** ✅
Files: `src/llm/*`
- Ollama uses structured `/api/chat` messages instead of flattened `/api/generate` prompts.
- Provider registry and `LlmClient::chat` compatibility preserved.

**D5. LLM concurrency limiting** ✅
Files: `src/llm/*`
- `ProviderConfig.max_concurrency` enforced with per-provider semaphores.
- Deterministic/no-provider simulation paths are not serialized.

**D6. Worldline causal_graph serialization** ✅
Files: `src/worldline/types.rs`
- Explicit stable serde contract for worldline causal graphs.
- Snapshot round-trip coverage added.

**D7. Alert dispatch to external channels** ✅
Files: `src/alert_dispatch.rs`
- Telegram, Discord, and generic webhook payloads with chunking, dry-run, and secret redaction.

**D8. Fast/slow feed tier separation** ✅
Files: `src/main.rs`
- Deterministic fast/slow feed scheduling helpers.
- Existing single-feed watch contract preserved.

### Phase E — Agent Integration & Simulation Auditability (COMPLETE)

**E1. HMAC-Signed Agent Command Channel** ✅
Files: `src/api.rs`, `src/daemon.rs`, `src/hongmeng/*`
- Added `/api/v1/agent/command` to daemon axum router.
- Verifies commands with HMAC-SHA256 over timestamp + nonce + body digest.
- Rejects replayed nonce/timestamp combinations and unsigned command ingress.
- Keeps replay protection testable without external services.

**E2. Structured Agent Output / Simulation Auditability** ✅
Files: `src/hongmeng/*`, `src/nuwa/*`, TUI simulation view if needed
- Enriched `AgentAction` with structured rationale: assessment, category, confidence, drivers.
- Preserves compatibility at prompt/API boundaries.
- Makes simulation paths auditable in JSON and TUI.

**E3. TUI Snapshot Timeline Replay** ✅
Files: `src/tui/*`, `src/storage.rs`, `src/worldline/*`
- Extended TUI simulation view with replay cursor/frame metadata.
- Supports `Left`/`h` and `Right`/`l` keyboard timeline scrubbing.
- Keeps existing TUI keybindings and fallback rendering stable.

---

## 3.5 Cross-Project Borrowings (ShadowBroker v0.9.7 → TianJi)

> Full analysis: removed during the 2026-09 documentation cleanup (the former `.trellis/reviews/` tree no longer exists in the repository); recover it from Git history.
> Repo: external ShadowBroker checkout used for historical cross-project analysis

Borrowing adoption status after Phase D/E:

- Borrowing 1: Alert Dispatch to External Channels ✅
  - Landed in D7 as `src/alert_dispatch.rs`.
  - Telegram, Discord, generic webhook, chunking, dry-run, and secret redaction.

- Borrowing 2: HMAC-Signed Agent Command Channel ✅
  - Landed in E1 as `POST /api/v1/agent/command`.
  - HMAC-SHA256 over timestamp + nonce + body digest with replay protection.

- Borrowing 3: Typed Data Model reference ✅
  - Landed across Phase C/D.
  - Hongmeng private state, board stick values, worldline snapshots, and API boundaries use typed Rust structures where stable contracts matter.

- Borrowing 4: Fast/Slow Feed Tier Separation ✅
  - Landed in D8.
  - Deterministic fast/slow scheduling helpers preserve existing single-feed watch behavior.

- Borrowing 5: Structured Agent Output ✅
  - Landed in E2.
  - `AgentAction` now carries `assessment`, `category`, `confidence`, and `drivers[]`.

- Borrowing 6: Snapshot Timeline Replay ✅
  - Landed in E3.
  - Simulation TUI exposes replay cursor/frame position and keyboard scrubbing.

### Phase F — Product Polish & Operator Readiness (COMPLETE)

**F1. Config sample and doctor command** ✅
- Added `examples/config.example.yaml` as a user-safe provider template.
- Added `tianji doctor [--config <PATH>] [--sqlite-path <PATH>] [--json]` for config parse, provider reference, env-var presence, and SQLite path readiness checks without leaking secrets.

**F2. API contract fixtures for Phase D/E surfaces** ✅
- Added stable contract coverage for `/api/v1/meta` and `/api/v1/agent/command` accepted/rejected envelopes.
- Added alert dispatch dry-run/redaction and mocked webhook payload contract tests.
- Added TUI replay cursor/frame formatting contract coverage.

**F3. README operator quickstart refresh** ✅
- Refreshed README operator quickstart for deterministic fixture runs, config template + `doctor`, current LLM config behavior, daemon/API envelope, signed agent command channel, alert dispatch dry-run/redaction, and TUI replay keybindings.
- Kept examples local-first and credential-free.

**F4. Release readiness check** ✅
- Verified `cargo build --release` under the 25 MB target.
- Verified shell completions for bash/zsh/fish and a fixture-based smoke run.
- Added `RELEASE_CHECKLIST.md` (removed in the 2026-09 documentation cleanup); it tracked exact
  binary size, replay/audit smoke output, regression gates, and local-first/no-secrets notes.

### Phase G — Roadmap & Spec Authority Refresh (COMPLETE)

**G1. Roadmap and spec authority refresh** ✅
- Updated root roadmap and README visible state after Phase F.
- Audited Trellis specs for stale Phase D/F status and Python-era implementation paths.
- Marked historical Python/Rich-era references as compatibility context where retained.
- Defined Phase H as the next feature phase.

### Phase H — Evaluation Harness (COMPLETE)

Purpose: make TianJi's analysis quality measurable before deeper scoring, simulation, or feed-source expansion.

**H1. Evaluation harness first slice** ✅
- Added checked-in eval corpus manifest and golden snapshot for the representative sample feed.
- Added `tianji eval --manifest tests/fixtures/eval/corpus.yaml` JSON drift report with CI-friendly failure exit.
- Compares local deterministic fixture output against manifest expectations and golden semantic score fields.

**H2. Golden artifact snapshots** ✅
- Added a second checked-in local fixture case with economy/high semantics.
- Every corpus case has a stable semantic golden snapshot under `tests/fixtures/eval/golden/`.
- `tianji eval --manifest tests/fixtures/eval/corpus.yaml --update-golden` refreshes only manifest-listed golden paths and reports them.

**H3. Score drift reporter** ✅
- Eval JSON report includes descriptions, check counts, failed-check counts, global/per-case `max_score_delta`, and updated golden paths.
- Numeric score checks include absolute `delta` and configured `tolerance`.
- Disallowed manifest/golden drift returns CI-friendly non-zero status.

**H4. Evaluation documentation and CI gate** ✅
- README documents running eval, adding fixture cases, refreshing goldens, and interpreting drift failures.
- Added `scripts/check-eval.sh` as a local credential-free eval gate.
- Eval remains independent of live network, LLM providers, daemon/API, and external services.

**H5. Credential-free replay smoke gate** ✅
- Added `scripts/check-replay-smoke.sh` as a local `/tmp`-only gate for replay bundle export and trace-backed TUI render-once.
- The gate validates bundle file set, manifest schema, trace metadata/frame/completed records, outcome consistency, and replay/audit text signals.
- The gate runs without provider config, network, daemon/API, live feeds, secrets, or repository-local transient outputs.

### Completed follow-on phases

### Phase I — Source/feed management (COMPLETE)

Purpose: make feed inputs explicit, local-first, and operator-controllable before
adding live polling metadata or persistence.

**I1. Source registry first slice** ✅
- Added typed YAML source registry support with `schema_version: tianji.sources-report.v1`.
- Added `tianji sources --config examples/sources.example.yaml` for JSON summary.
- Added `--run-fixtures` for deterministic fan-in over enabled fixture sources only.
- Disabled sources are reported but not run/fetched.
- Added credential-free `examples/sources.example.yaml` with local fixture paths and a disabled `example.invalid` dummy remote.

**I2-I4. Health summaries, live fetch opt-in, and docs** ✅
- Source reports include aggregate `ready`, `skipped`, and `errors` counters plus per-source status/runnable/last-success/error fields.
- `--run-fixtures` runs enabled fixture sources only and never fetches network sources.
- `--fetch-live` is the only source-registry mode that fetches enabled RSS/Atom sources, using the deterministic feed pipeline and concise per-source counts/status.
- Default `tianji sources --config <PATH>` remains validation/report-only with no network I/O.
- README documents registry listing, fixture fan-in, live-fetch opt-in, safety constraints, and CI-friendly smoke commands.

**I5. Source health scheduling completion** ✅
- Added additive SQLite source-health history for source check/run outcomes.
- `tianji sources --sqlite-path <PATH>` listing reads latest persisted health and
  enriches per-source `last_success`, `last_error`, and error message metadata.
- `--run-fixtures --sqlite-path` and `--fetch-live --sqlite-path` persist health
  rows for enabled runs plus disabled/skipped sources; default listing without
  `--sqlite-path` remains no-network/no-DB.
- Operator scheduling is external: cron/systemd/Kubernetes invokes `sources
  --fetch-live --sqlite-path`, while TianJi records health history only.

### Phase J — Operational reliability (COMPLETE)

**J1. SQLite retention policy** ✅
- Added `tianji maintenance retain --sqlite-path <PATH> --keep-last-runs <N>`.
- Storage retention keeps the latest N runs by run id descending, deletes older
  runs in one transaction, relies on foreign-key cascades for run-scoped rows,
  and removes orphan canonical source items.
- Emits `tianji.retention-report.v1` JSON for operator automation.

**J2. Daemon health/readiness endpoints** ✅
- Added `GET /api/v1/health` for API process liveness without SQLite access.
- Added `GET /api/v1/ready` for SQLite-backed readiness via pooled connection
  checkout plus a trivial query.
- Daemon startup readiness polling now checks `/api/v1/ready` instead of
  inferring readiness from `/api/v1/meta`.

**J3-J6. Maintenance check, backup, export, compact** ✅
- Added read-only `tianji maintenance check` diagnostics with quick check,
  foreign-key validation, table counts, latest run id, file sizes, page/freelist
  counts, and journal mode.
- Added online-safe `tianji maintenance backup` via SQLite-native `VACUUM INTO`.
- Added portable `tianji maintenance export` in JSON or JSONL, with optional
  full run details.
- Added `tianji maintenance compact` for WAL checkpoint truncate and optional
  `VACUUM`.

### Phase K — Simulation replay/export (COMPLETE)
- JSONL trace export, replay bundle packaging, structured agent audit viewer improvements.

**K1. Simulation JSONL trace export** ✅
- Added `tianji.sim-trace.v1` JSONL export/import helpers with `metadata`, `frame`, and `completed` records.
- Added `run_forward_with_trace(...)` while preserving `run_forward(...)` and default `predict` stdout outcome JSON.
- Added `tianji predict --trace-jsonl <PATH>` for replay-friendly forward simulation traces including field changes and structured agent audit fields.

**K2. Replay bundle packaging** ✅
- Added `tianji.replay-bundle.v1` manifest metadata and `write_replay_bundle_dir(...)` helper that reuses K1 trace serialization.
- Added `tianji predict --replay-bundle-dir <DIR>` to write `manifest.json`, `trace.jsonl`, and `outcome.json` while preserving default stdout outcome JSON.
- Added focused coverage for bundle writing, manifest file references/byte sizes, trace import, outcome parsing, CLI parse, and predict bundle creation.

**K3. TUI trace-backed replay loading** ✅
- Added TUI replay loading from `--trace-jsonl <PATH>` and `--replay-bundle-dir <DIR>` without requiring provider execution.
- Trace-backed simulation replay updates selected frame display while scrubbing with `Left`/`h` and `Right`/`l`, including tick/frame metadata, field values, field changes, and event sequence length.
- Replay bundle loading is local/secret-safe and reads only `manifest.json`, `trace.jsonl`, and `outcome.json`.

**K4. Structured agent audit viewer** ✅
- TUI simulation replay renders compact structured agent audit fields from trace frames: actor id, action type, target, confidence, category, assessment, drivers, and rationale.
- Added `--render-once` for deterministic plain-text replay smoke checks without launching an interactive terminal.
- Replay render-once output includes operator-facing replay controls and audit coverage counts for the selected frame.

### Next development direction

No explicit Post-K development candidates remain in this plan. Future runtime
behavior changes should start from a new PRD and stay local-first by default.
Provider-backed simulation, live feed fetch, daemon write paths, and alert
dispatch remain optional unless that future PRD scopes them explicitly.

---

## 4. Dependencies

```toml
[dependencies]
clap = { version = "4.6", features = ["derive"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
serde_yaml = "0.9"
roxmltree = "0.21"
regex = "1.12"
sha2 = "0.11"
hmac = "0.13"
blake3 = "1"
rusqlite = { version = "0.39", features = ["bundled"] }
reqwest = { version = "0.13", default-features = false, features = ["rustls", "blocking"] }
axum = "0.8"
uuid = { version = "1", features = ["v4"] }
tokio = { version = "1", features = ["full"] }
libc = "0.2"
ratatui = "0.30"
crossterm = "0.28"
chrono = { version = "0.4", features = ["serde"] }
petgraph = { version = "0.7", features = ["serde-1"] }
anyhow = "1"
thiserror = "2"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
clap_complete = "4"

[profile.release]
opt-level = 3
lto = true
```

---

## 5. Verification Criteria

Each phase must pass:
- `cargo build` / `cargo build --release` zero error
- `cargo test` all green (currently 445 tests across 3 cargo suites)
- `cargo clippy -- -D warnings` zero warning
- `tianji run --fixture ...` output field-level consistent with contracts
- `tianji delta --latest-pair` cross-run change tracking functional
- Single binary < 25MB release (current: 16,245,408 bytes / 15.49 MiB)
