# Directory Structure

> How backend code is organized in this project.

---

## Overview

TianJi is a **pure Rust project**. The authoritative project structure is defined
in `plan.md` §10. Python oracle code was retired in Phase 6 (v0.2.0).

---

## Historical Target Layout

Older roadmap drafts described a future subsystem-directory split (`cangjie/`,
`fuxi/`, `cli/`, `daemon/`, `output.rs`). That layout is historical context only.
The shipped Rust product currently uses the source layout below; root `plan.md`
and `README.md` are authoritative for operator-facing structure.

### Current State (All Milestones Complete)

The Rust crate implements all shipped milestones. Current source layout:

```
src/
├── main.rs          # CLI entry (17 shipped top-level subcommands)
├── lib.rs           # Pipeline orchestration + integration tests
├── models.rs        # RawItem, NormalizedEvent, ScoredEvent, RunArtifact, etc.
├── fetch.rs         # RSS/Atom parsing + canonical hashing (Cangjie)
├── normalize.rs     # Keyword/actor/region extraction + field scores (Cangjie)
├── scoring.rs       # Im/Fa scoring + rationale (Fuxi)
├── grouping.rs      # Event grouping + causal ordering (Fuxi)
├── backtrack.rs     # Intervention candidate generation (Fuxi)
├── storage.rs       # SQLite history/source-health/maintenance CRUD
├── daemon.rs        # UNIX socket + job queue + serve
├── api.rs           # axum /api/v1 routes (8 GET + 1 POST command ingress)
├── webui.rs         # Embedded static files + API proxy + /queue-run
├── tui/             # ratatui history/simulation browser (Kanagawa Dark)
├── hongmeng/        # Agent orchestration, board, referee, config, checkpoint
├── nuwa/            # Forward/backward simulation, pruning, trace/bundle export
├── llm/             # Provider config, registry, and reqwest client
├── profile/         # Actor profile registry, dynamic memory, typed profiles
├── worldline/       # Baseline, dependency graph, store, typed worldline state
├── source_registry.rs
├── eval.rs
├── alert_dispatch.rs
├── delta.rs
├── delta_memory.rs
├── scoring_params.rs
├── time_utils.rs
└── utils.rs
```

Root `plan.md` and `README.md` are authoritative for current operator-facing
structure. Historical phase specs may still mention pre-split files such as
`src/tui.rs` as implementation history, not as current paths.

---

## Rust Module Organization

### Stage-Oriented Modules

Each pipeline stage gets its own module, grouped under subsystem namespaces:

- `cangjie::feed` → `cangjie::normalize` (Milestone 1A, currently flat in `src/`)
- `fuxi::scoring` → `fuxi::grouping` → `fuxi::backtrack` (Milestone 1B, currently flat in `src/`)

### Naming Conventions

| Convention | Pattern | When to Use |
|------------|---------|-------------|
| Stage modules | `{stage}.rs` | One file per pipeline stage (`scoring.rs`, `backtrack.rs`) |
| Subsystem dirs | `{subsystem}/mod.rs` + `*.rs` | When a subsystem has 3+ modules (`cangjie/`, `fuxi/`) |
| CLI commands | `cli/{command}.rs` | One file per CLI command (`cli/run.rs`, `cli/history.rs`) |
| Test modules | `#[cfg(test)] mod tests` inside each module | Unit tests co-located with code |
| Integration tests | Tests in `src/lib.rs` | End-to-end pipeline tests |

### Spec Document Naming

Specification documents under `.trellis/spec/` use **lowercase kebab-case** filenames.

```text
.trellis/spec/backend/scoring-spec.md
.trellis/spec/backend/contracts/local-api-contract.md
```

### Forbidden Patterns

- **No `utils.rs` catch-all** — every file has a specific purpose and name
- **No premature subsystem directories** — create `cangjie/` when it has 3+ files, not before
- **No root-doc uppercase names inside `.trellis/spec/`** — use lowercase kebab-case

---

## Examples of Well-Organized Rust Modules

- **Models**: `src/models.rs` — flat struct definitions for all pipeline data types
- **Scoring**: `src/scoring.rs` — `compute_im`, `compute_fa`, `compute_divergence_score`, `build_rationale`, `score_events`
- **Grouping**: `src/grouping.rs` — `group_events`, `summarize_group`, `build_evidence_chain`
- **Backtracking**: `src/backtrack.rs` — `backtrack_candidates`, `infer_intervention_type`, `build_reason`

---

**Language**: English
