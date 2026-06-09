# PROJECT KNOWLEDGE BASE

**Updated:** 2026-06-09
**Version:** v0.2.0

## OVERVIEW

TianJi is a pure Rust geopolitical intelligence engine. The authoritative
architecture document is root `plan.md`, which defines four subsystems
(Cangjie, Fuxi, Hongmeng, Nuwa), the project structure, TUI design, and
phased build order.

**Current state:**
- Rust: All milestones (M1A–M4, Crucix Delta, M3.5, Phase 6) complete.
- Pure Rust binary. Python oracle retired in Phase 6 (v0.2.0).

## STRUCTURE
```text
tianji/
├── src/                    # Rust implementation
├── Cargo.toml              # Rust crate manifest (24 deps)
├── tests/
│   └── fixtures/           # sample_feed.xml + contract fixtures
├── plan.md                 # Authoritative Rust architecture + build phases
└── .trellis/spec/backend/  # Development guidelines and contracts
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Rust architecture | `plan.md` | Authority for all subsystems, phases, structure |
| Rust implementation | `src/main.rs`, `src/lib.rs` | Current Rust entry |
| Rust models | `src/models.rs` | Data structures |
| Rust feed parsing | `src/fetch.rs` | RSS/Atom fixture loading |
| Rust normalization | `src/normalize.rs` | Keyword/actor/region extraction |
| Rust scoring | `src/scoring.rs` | Im/Fa scoring + rationale |
| Rust grouping | `src/grouping.rs` | Event grouping + causal ordering |
| Rust backtracking | `src/backtrack.rs` | Intervention candidate generation |
| Rust storage | `src/storage.rs` | SQLite 6 tables + history CRUD |
| Rust TUI | `src/tui/` | ratatui history/simulation browser (Kanagawa Dark) |
| Rust delta engine | `src/delta.rs`, `src/delta_memory.rs` | Cross-run change tracking + alert tier |
| Development plan | `.trellis/spec/backend/development-plan.md` | Milestones and guardrails |

## CODE MAP (Rust)
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `main` | function | `src/main.rs` | CLI entry (17 shipped top-level subcommands) |
| `RawItem` | struct | `src/models.rs` | Parsed feed item |
| `NormalizedEvent` | struct | `src/models.rs` | Extracted event with keywords/actors/regions |
| `ScoredEvent` | struct | `src/models.rs` | Event with Im/Fa/divergence scores |
| `RunArtifact` | struct | `src/models.rs` | Pipeline output contract |
| `parse_feed` | function | `src/fetch.rs` | RSS/Atom parsing |
| `normalize_items` | function | `src/normalize.rs` | Event extraction and field scoring |
| `score_events` | function | `src/scoring.rs` | Im/Fa scoring + rationale |
| `group_events` | function | `src/grouping.rs` | Event grouping + causal ordering |
| `backtrack_candidates` | function | `src/backtrack.rs` | Intervention candidate generation |
| `persist_run` | function | `src/storage.rs` | SQLite persistence (6 tables) |
| `list_runs` | function | `src/storage.rs` | History list with filters |
| `AppState` | struct | `src/api.rs` | axum shared state (sqlite_path) |
| `build_router` | function | `src/api.rs` | axum Router (8 GET routes + 1 POST command ingress) |
| `DaemonState` | struct | `src/daemon.rs` | In-memory job queue (Mutex+Condvar) |
| `serve` | function | `src/daemon.rs` | tokio runtime: socket + API + worker |
| `WebUiState` | struct | `src/webui.rs` | axum state (api_base_url, socket_path) |
| `serve_webui` | function | `src/webui.rs` | Static file serve + API proxy + /queue-run |
| `compute_delta` | function | `src/delta.rs` | Cross-run delta computation |
| `HotMemory` | struct | `src/delta_memory.rs` | Alert tier + hot-run tracking |

## CONVENTIONS
- `plan.md` is the architecture authority. When in doubt, follow it.
- Rust implementation goes under `src/` per `plan.md` §10 project structure.
- Rust build/test: `cargo build`, `cargo test`, `cargo fmt --check`, `cargo clippy -- -D warnings`.

## ANTI-PATTERNS
- Do not add async runtimes, web frameworks, TUI crates, or LLM crates before the milestone that uses them.
- Do not design for daemon/IPC/web UI before the one-shot flow stays correct.
- Do not bypass CLI input rules: no run without `--fixture` plus at least one resolved source.
- Do not implement Hongmeng or Nuwa before Cangjie/Fuxi + storage parity.

## COMMANDS
```bash
cargo build
cargo test
cargo fmt --check
cargo clippy -- -D warnings
cargo run -- run --fixture tests/fixtures/sample_feed.xml
tianji completions bash  # shell completion generation
```

## NOTES
- The Rust TUI uses ratatui with Kanagawa Dark palette per `plan.md` §9.
- The local API contract is documented in `.trellis/spec/backend/contracts/local-api-contract.md`.
- Scoring model spec: `.trellis/spec/backend/scoring-spec.md`.
