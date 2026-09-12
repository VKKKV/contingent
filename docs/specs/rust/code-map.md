# Legacy Rust code map

Quick orientation for the preserved Rust implementation. `plan.md` remains the architecture authority
for this code; the direction for new work is the Web-first laboratory in `backend/` and `web/`.

## Current state

- All Rust milestones (M1A–M4, Crucix Delta, M3.5, Phase 6) are complete: a pure Rust binary with no
  Python dependency. Rust source and the existing `runs/*.sqlite3` databases are preserved read-only;
  no migration is authorized.

## Structure

```text
tianji/
├── src/                       # Rust implementation
├── Cargo.toml                 # crate manifest
├── tests/fixtures/            # sample_feed.xml + contract fixtures
├── plan.md                    # architecture authority for the Rust baseline
└── docs/specs/rust/           # guidelines, contracts and specs for this code
```

## Where to look

| Task | Location |
|------|----------|
| Architecture and build phases | `plan.md` |
| CLI entry | `src/main.rs` (17 shipped top-level subcommands) |
| Data structures | `src/models.rs` |
| Feed parsing | `src/fetch.rs` |
| Normalization | `src/normalize.rs` |
| Scoring (Im/Fa/divergence) | `src/scoring.rs` |
| Grouping and causal ordering | `src/grouping.rs` |
| Backtracking candidates | `src/backtrack.rs` |
| Storage (6 SQLite tables) | `src/storage.rs` |
| TUI | `src/tui/` |
| Delta engine | `src/delta.rs`, `src/delta_memory.rs` |
| Development plan | `docs/specs/rust/development-plan.md` |
| Scoring model spec | `docs/specs/rust/scoring-spec.md` |
| Daemon / API / TUI / web contracts | `docs/specs/rust/contracts/` |

## Code map

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `main` | function | `src/main.rs` | CLI entry |
| `RawItem` | struct | `src/models.rs` | Parsed feed item |
| `NormalizedEvent` | struct | `src/models.rs` | Extracted event with keywords/actors/regions |
| `ScoredEvent` | struct | `src/models.rs` | Event with Im/Fa/divergence scores |
| `RunArtifact` | struct | `src/models.rs` | Pipeline output contract |
| `parse_feed` | function | `src/fetch.rs` | RSS/Atom parsing |
| `normalize_items` | function | `src/normalize.rs` | Event extraction and field scoring |
| `score_events` | function | `src/scoring.rs` | Im/Fa scoring + rationale |
| `group_events` | function | `src/grouping.rs` | Event grouping + causal ordering |
| `backtrack_candidates` | function | `src/backtrack.rs` | Intervention candidate generation |
| `persist_run` | function | `src/storage.rs` | SQLite persistence |
| `list_runs` | function | `src/storage.rs` | History list with filters |
| `AppState` | struct | `src/api.rs` | axum shared state (sqlite_path) |
| `build_router` | function | `src/api.rs` | axum Router (8 GET routes + 1 POST command ingress) |
| `DaemonState` | struct | `src/daemon.rs` | In-memory job queue (Mutex + Condvar) |
| `serve` | function | `src/daemon.rs` | tokio runtime: socket + API + worker |
| `WebUiState` | struct | `src/webui.rs` | axum state (api_base_url, socket_path) |
| `serve_webui` | function | `src/webui.rs` | Static file serve + API proxy + `/queue-run` |
| `compute_delta` | function | `src/delta.rs` | Cross-run delta computation |
| `HotMemory` | struct | `src/delta_memory.rs` | Alert tier + hot-run tracking |

## Conventions and anti-patterns

- `plan.md` is the architecture authority; when in doubt, follow it.
- Do not add async runtimes, web frameworks, TUI crates or LLM crates before the milestone that uses
  them, and do not design for daemon/IPC/web UI before the one-shot flow stays correct.
- Do not bypass CLI input rules: no run without `--fixture` plus at least one resolved source.
- Historical Python-oracle references must be explicitly labelled historical; the Python oracle was
  retired in Phase 6 (v0.2.0).

## Commands

```bash
cargo build
cargo test
cargo fmt --check
cargo clippy -- -D warnings
cargo run -- run --fixture tests/fixtures/sample_feed.xml
tianji completions bash
```

The Rust TUI uses ratatui with the Kanagawa Dark palette per `plan.md` §9.
