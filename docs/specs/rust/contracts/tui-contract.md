# TianJi TUI Contract

> **Status: Historical / superseded.** This document preserves the Python Rich-era
> TUI contract for compatibility context only. Current shipped TianJi uses the
> Rust `src/tui/` ratatui implementation with Kanagawa Dark styling, history,
> detail, compare, search/filter, simulation, and replay scrubbing. Use root
> `plan.md`, README, and current Rust tests as the authority for new work.

## Purpose

This document defines the shipped contract for TianJi's terminal UI.

TianJi previously shipped a read-only Python Rich slice. The current product ships
a Rust ratatui TUI; the Python-era text below is retained only to explain the
historical read-only navigation contract.
The goal here is to preserve alignment between:

- the current CLI-first operator workflow
- the current SQLite-backed persisted read surface
- a later Vim-style terminal UI that reuses those existing concepts without
  inventing a second domain model

## Scope

This contract is intentionally narrow.

It covers only a **read-only persisted-run browser** built on top of the current
`history`, `history-show`, and `history-compare` semantics.

The TUI should browse:

- persisted run history
- one persisted run in detail
- two persisted runs in comparison

## Shipped Now vs Planned Later

### Historical Python slice

The earlier Python implementation provided these read-only semantics, implemented
in `tianji/tui.py` and dispatched from `tianji/cli.py` before the Rust port:

- launch from `python3 -m tianji tui --sqlite-path ...`
- browse a persisted run list
- open a persisted detail panel
- stage a left run for comparison, then browse a compare panel against a selected right run
- move through persisted runs with keyboard-first navigation backed by storage read semantics
- keep compare staging visible in TUI state
- treat storage-backed read payloads as the semantic source of truth

Representative verification already exists in `tests/test_tui.py`.

### Planned later

This contract still reserves room for a fuller Vim-style operator experience, but that later work should extend the shipped read-only browser instead of replacing it with a different domain model.

## Non-Goals

This contract does **not** define:

- live run execution screens
- progress/status polling
- daemon, scheduler, or IPC behavior
- web/API transport requirements
- new scoring logic or storage schema changes
- exact keybinding maps beyond high-level Vim-style navigation intent

## Implementation

The shipped implementation uses `rich` (`Console`, `Live`, `Layout`) plus a small stdlib raw-key loop for keyboard-first navigation. This keeps the current slice lightweight and local-first while preserving room to revisit the framework choice later if the browser grows beyond Rich's comfortable scope.

## Design Principles

1. **CLI/storage remain the source of truth**
   - The TUI should reuse current read semantics rather than inventing a new
     backend contract.

2. **Persisted truth stays distinct from projected lenses**
    - Stored run-summary fields still describe the persisted run.
    - Filters, limits, and compare projections only shape the operator view.
    - This applies equally to the shipped CLI read surface and the shipped TUI read surface.

3. **Read-only first**
   - The first TUI contract should browse persisted data only.
   - Running pipelines remains a CLI and daemon concern. The TUI does not become a write surface.

4. **Vim-style navigation without new business logic**
   - The TUI may add keyboard-first movement and selection.
   - It should not duplicate scoring, grouping, comparison, or filtering logic.

## Source-of-Truth Surfaces

Current Rust source-of-truth surfaces:

- `tianji history --sqlite-path ...`
  - persisted run list / triage view

- `tianji history-show --sqlite-path ...`
  - persisted single-run detail view
  - supports latest / previous / next navigation
  - supports scored-event and event-group projection lenses

- `tianji history-compare --sqlite-path ...`
  - persisted run compare view
  - supports explicit pair and relative/latest presets
  - supports the same projection lenses as `history-show`

- `src/storage.rs`
  - canonical read-model implementation for list/detail/compare payloads
  - persisted truth lives here, while TUI panels render projected read lenses on top

## Core Entities and IDs

The TUI should reuse current identifiers and payload vocabulary:

- `run_id` — primary persisted run identity
- `schema_version` — artifact contract version
- `event_id` — scored event identity
- `headline_event_id` — top event-group identity
- `top_scored_event` — compare/list triage anchor
- `top_event_group` — grouped-analysis triage anchor

## Operator Workflows

### 1. Run History List

Purpose:
- browse persisted runs
- triage by mode, field, risk, score, and grouped-analysis signals
- choose one run for detail or two runs for comparison

Stable row fields:

- `run_id`
- `schema_version`
- `mode`
- `generated_at`
- `raw_item_count`
- `normalized_event_count`
- `dominant_field`
- `risk_level`
- `headline`
- `event_group_count`
- `top_event_group_headline_event_id`
- `top_event_group_dominant_field`
- `top_event_group_member_count`
- `top_scored_event_id`
- `top_scored_event_dominant_field`
- `top_impact_score`
- `top_field_attraction`
- `top_divergence_score`

### 2. Run Detail

Purpose:
- inspect one stored run with optional scored-event and event-group lenses
- optionally align interventions to the visible scored-event selection

Stable root payload:

- `run_id`
- `schema_version`
- `mode`
- `generated_at`
- `input_summary`
- `scenario_summary`
- `scored_events`
- `intervention_candidates`

Stable detail behaviors:

- latest / previous / next navigation is storage-backed persisted-run navigation, not merely movement inside the current loaded list window
- `scenario_summary` remains persisted truth even when projected lists narrow
- scored-event filtering and event-group filtering are independent
- `only_matching_interventions` aligns interventions to the final visible
  scored-event set after filters and limits

### 3. Run Compare

Purpose:
- compare two persisted runs under one operator lens
- inspect both side summaries plus explicit diff fields
- surface a compact top-group evidence diff subsection inside the compare panel

Stable compare payload:

- `left_run_id`
- `right_run_id`
- `left`
- `right`
- `diff`

Stable compare selection modes:

- explicit `left_run_id` / `right_run_id`
- latest pair
- run against latest
- run against previous

These presets remain mutually exclusive.

Stable compare navigation behavior:

- staged compare selection stays read-only and storage-backed
- compare target stepping resolves against persisted previous/next run semantics, not merely the currently loaded list window
- compare-target stepping skips the staged left run until it finds a valid persisted right-hand target or reaches a true persisted boundary

## Lens and Projection Semantics

The shipped TUI already exposes shared in-TUI projection controls for the
read-only detail and compare panes while keeping the history list on persisted
truth.

The remaining Phase 5 work should treat those shared projection rules as shipped
behavior. The history list now also shows the richer persisted triage fields from
storage while still remaining persisted truth, so the next emphasis is stronger
storage-backed verification and regression hardening rather than a separate
TUI-only projection model or new list semantics.

### Scored-event lens

Shipped shared lens controls:

- `dominant_field`
- `limit_scored_events`

Explicitly deferred from this slice:

- direct numeric score-window entry for `min_impact_score` / `max_impact_score`
- direct numeric score-window entry for `min_field_attraction` / `max_field_attraction`
- direct numeric score-window entry for `min_divergence_score` / `max_divergence_score`

### Event-group lens

Shipped shared lens controls:

- `group_dominant_field`
- `limit_event_groups`

### Intervention alignment lens

Shipped shared lens control:

- `only_matching_interventions=false`
  - keep full persisted intervention list

- `only_matching_interventions=true`
  - keep only interventions whose `event_id` remains in the final visible
    scored-event set

This Phase 5 work should keep those shipped controls shared across detail and
compare panes, preserve the list as persisted truth, and avoid adding list-pane
filtering, text entry, or any new storage semantics.

### Persisted truth vs projected view

- `history-show`
  - run-level summary fields remain persisted truth
  - projected `scored_events`, `event_groups`, and aligned interventions are
    read-time lenses

- `history-compare`
  - compare-side projected fields such as `top_scored_event`,
    `intervention_event_ids`, `event_group_count`, and `top_event_group` depend
    on the active lens
  - stored run-summary fields like `headline`, `dominant_field`, and
    `risk_level` still describe the persisted run itself

Those projected lenses remain a read-time operator view over storage-backed
truth. Storage and CLI semantics stay authoritative, projection and cache
preparation shape detail and compare payloads before render formatting, and the
history list continues to show persisted truth rather than a separately
filtered list pane.

## Navigation and State Model

The first shipped slice already has concrete navigation behavior, but this
contract only locks the high-level navigation nouns, not every final keybinding
detail.

Minimum state:

- selected `run_id` in history list
- selected compare pair, including a visible staged left run before compare activates
- active scored-event lens
- active event-group lens
- intervention alignment toggle
- active panel/view (`list`, `detail`, `compare`)

The current implementation already carries these ideas in state, including a visible staged left compare run before compare activation.

The remaining Phase 5 work is to keep hardening verification around those
shipped behaviors, especially storage-backed coverage for persisted-run
navigation, compare-target stepping, and shared lens behavior, instead of
adding new list semantics or a second TUI-only read model.

Minimum Vim-style navigation intent:

- move selection within a list/table
- open selected run detail
- switch back to history list
- move to previous / next persisted run from detail view
- stage a left/right compare pair from list selection with visible staged-pair feedback
- switch focus between compare left/right/diff panes
- apply or clear filter lenses without mutating stored data

Shipped navigation parity requirement:

- previous / next stepping from detail view resolves against SQLite-backed persisted previous/next run semantics, even when the adjacent run falls outside the currently loaded list window
- compare-target stepping resolves against the same persisted previous/next run semantics, skipping the staged left run until a valid right-hand target exists or a true persisted boundary is reached
- first/last persisted boundaries surface explicit navigation errors instead of silently stopping at the current list window edge

## Empty and Error States

The TUI is a read-only surface and treats current CLI/storage semantics as
authoritative.

Valid empty states:

- no persisted runs available
- no scored events remain after projection
- no event groups remain after projection
- no intervention candidates remain after alignment

Validation/error states to preserve:

- negative limits are invalid
- inverted score windows are invalid
- compare preset mixes are invalid
- non-positive explicit run IDs are invalid
- missing previous/next/latest runs should surface as navigation errors, not as
  silent fallback behavior

## Relationship to Local API Planning

This document is intentionally separate from `local-api-contract.md`.

- `tui-contract.md` defines a shipped read-only terminal surface plus later terminal planning over current in-process storage/artifact semantics.
- `local-api-contract.md` defines a future process boundary for an optional local
  service/API layer.

The shipped TUI does not require a local API, and later TUI work should not require one either.

## Recommended Later Implementation Order

When TianJi extends the terminal UI further, keep the next slices in this order:

1. history list view
2. single-run detail view
3. run compare view
4. only then consider run-triggering or live-runtime concerns

This keeps Phase 5 aligned with current product reality: local-first, deterministic, persisted-analysis-first, and read-only by default.

## Rust TUI MVP Contract

### 1. Scope / Trigger

- Trigger: Milestone 4 introduces the first Rust terminal UI surface.
- Scope: read-only persisted-run history browser only.
- Out of scope: run detail, run compare, filters, search, simulation monitoring, profile browsing, live run execution, daemon control.

### 2. Signatures

Rust CLI command:

```bash
tianji tui --sqlite-path <path> [--limit <N>]
```

Rust module boundary:

```rust
pub fn run_history_browser(sqlite_path: &str, limit: usize) -> Result<String, TianJiError>
```

Storage dependency:

```rust
list_runs(sqlite_path, limit, &RunListFilters::default())
```

### 3. Contracts

- `--sqlite-path` is required and points to the SQLite read model used by `history`.
- `--limit` defaults to `20` and is passed through to existing storage list semantics.
- The TUI must not mutate SQLite, queue runs, call daemon IPC, or fetch feeds.
- The history list renders rows derived from persisted run-list payload fields, especially `run_id`, `generated_at`, `mode`, `dominant_field`, `risk_level`, `top_divergence_score`, and `headline`.
- The terminal view uses ratatui + crossterm, Kanagawa Dark colors from `plan.md` §9, `Block::bordered()`, non-blocking `event::poll(Duration::from_millis(100))`, and a status bar that exposes navigation keys.
- `run_history_browser` returns an empty string after an interactive session exits successfully so the CLI does not print an extra blank payload.

### 4. Validation & Error Matrix

| Condition | Behavior |
|-----------|----------|
| SQLite path does not exist | Return the empty-state message instead of creating or mutating a database |
| SQLite exists but no `runs` table | Return the empty-state message |
| SQLite exists and run list is empty | Return the empty-state message |
| Storage query fails for other reasons | Propagate `TianJiError` |
| Terminal setup fails after raw mode is enabled | Disable raw mode and leave alternate screen via cleanup guard |
| User presses `q` | Exit cleanly without mutating storage |
| User presses `j` or Down | Move selection down, clamped at the final row |
| User presses `k` or Up | Move selection up, clamped at the first row |

### 5. Good/Base/Bad Cases

- Good: `tianji tui --sqlite-path runs/tianji.sqlite3` opens a read-only history list when persisted runs exist.
- Base: `tianji tui --sqlite-path empty.sqlite3` prints `No persisted runs are available for the TUI browser.` and exits successfully when no persisted runs are available.
- Bad: adding detail/compare/filter/search behavior in the first Rust slice hides the MVP boundary and duplicates existing CLI projection logic too early.

### 6. Tests Required

- Unit-test storage payload to TUI row mapping without requiring an interactive terminal.
- Unit-test row formatting includes run id, mode, dominant field, divergence, and headline.
- Unit-test selection clamps at list boundaries.
- Unit-test key handling for `j`, `k`, Up, Down, and `q`.
- Run `cargo fmt --check`, `cargo test`, and `cargo clippy -- -D warnings` after TUI changes.

### 7. Wrong vs Correct

#### Wrong

```rust
// A TUI handler that writes data or queues work violates the read-only MVP.
daemon::send_daemon_request(socket_path, queue_run_payload)?;
```

#### Correct

```rust
// The MVP reads persisted run rows through the existing storage read model.
let rows = list_runs(sqlite_path, limit, &RunListFilters::default())?;
```

## Rust TUI Dashboard Contract

### 1. Scope / Trigger

- Trigger: Phase 4 extends the Rust TUI from a history-only browser to a read-only dashboard/home view.
- Scope: dashboard plus existing history browser, both backed by existing persisted run and hot-memory delta read models.
- Out of scope: live simulation monitoring, profile browsing, Hongmeng/Nuwa runtime state, daemon control, run queueing, feed fetching, and any storage mutation.

### 2. Signatures

Rust CLI command remains unchanged:

```bash
tianji tui --sqlite-path <path> [--limit <N>]
```

Rust module boundary remains unchanged:

```rust
pub fn run_history_browser(sqlite_path: &str, limit: usize) -> Result<String, TianJiError>
```

Read dependencies:

```rust
list_runs(sqlite_path, limit, &RunListFilters::default())
HotMemory::load(&delta_memory_path(sqlite_path))
get_latest_run_id(sqlite_path)
get_run_summary(
    sqlite_path,
    latest_run_id,
    &ScoredEventFilters::default(),
    false,
    &EventGroupFilters::default(),
)
```

### 3. Contracts

- The TUI remains read-only and must not write SQLite, queue daemon jobs, call daemon IPC, fetch feeds, or start simulations.
- The dashboard loads the latest run summary via `get_latest_run_id` + `get_run_summary` in addition to history rows and hot-memory delta.
- `DashboardState` fields:
  - Run metadata: `latest_run_id`, `latest_generated_at`, `latest_mode`, `headline` (from scenario_summary if run summary available, else from history row).
  - Field breakdown: `field_summary: Vec<FieldStat>` (grouped by `dominant_field`, count + avg `impact_score`, sorted by count desc), `total_scored_events: usize`.
  - Top events: `top_events: Vec<TopEvent>` (top 5 by `impact_score` desc, each with `title`, `impact_score`, `dominant_field`).
  - Delta: `alert_tier`, `delta_summary`, `delta_direction` (from hot memory, unchanged).
  - Removed fields: `dominant_field`, `risk_level`, `top_divergence_score`, `baseline_status`, `worldline_status` (field/risk shown in metadata line; baseline/worldline deferred).
- When no run summary is available (no SQLite, no runs), `field_summary` and `top_events` are empty, `total_scored_events` is 0.
- The dashboard renders styled `Span`s with Kanagawa colors (field labels blue, impact green>10/yellow>5, alert tier peach/yellow/default).
- `format_dashboard` (CLI text output) mirrors the same sections in plain text for non-TUI use.

### 4. Validation & Error Matrix

| Condition | Behavior |
|-----------|----------|
| SQLite path does not exist | Return the existing empty-state message before launching the terminal |
| SQLite exists but has no persisted runs | Return the existing empty-state message before launching the terminal |
| Hot-memory file is missing/corrupt | Render dashboard delta placeholders via `HotMemory::default()` behavior |
| Run summary query fails or returns None | Render dashboard with empty field_summary/top_events |
| User presses dashboard selector | Switch to dashboard view without changing selected history row |
| User presses history selector | Switch to history view without resetting selected history row |
| User presses history navigation while dashboard is active | Keep selection unchanged |

### 5. Good/Base/Bad Cases

- Good: `tianji tui --sqlite-path runs/tianji.sqlite3` opens on a dashboard showing latest run metadata, field breakdown with per-field counts/avg impact, top 5 scored events, and recent delta information; can switch to history with `h`.
- Base: a database with persisted runs but no hot-memory delta shows latest run fields, field summary, top events, and a stable "No recent delta available." placeholder.
- Bad: showing fabricated baseline/worldline numbers before worldline storage exists, or adding daemon/write controls to the dashboard.

### 6. Tests Required

- Unit-test dashboard mapping from history rows, default hot memory, and run summary JSON.
- Unit-test dashboard mapping from hot-memory delta summary and alert tier.
- Unit-test FieldStat and TopEvent extraction from scored_events JSON.
- Unit-test dashboard formatting includes latest run, field summary, top events, and delta sections.
- Unit-test view switching keys and verify history navigation is inactive while dashboard is active.
- Unit-test empty dashboard with no run summary shows zero fields/events.
- Re-run existing history row/key handling tests to ensure history behavior remains intact.
- Run `cargo fmt --check`, `cargo test`, and `cargo clippy -- -D warnings` after TUI changes.

### 7. Wrong vs Correct

#### Wrong

```rust
// A dashboard must not fabricate future worldline state before storage exists.
let baseline = format!("run #{}", latest_run_id - 41);
```

#### Correct

```rust
// Field summary derived from actual scored_events data, not fabricated.
let field_summary = extract_field_summary(&scored_events);
// Top events from actual impact_score, capped at 5.
let top_events = extract_top_events(&scored_events, 5);
```

## Rust TUI Detail Contract

### 1. Scope / Trigger

- Trigger: Phase 4 extends the Rust TUI from dashboard/history browsing to a read-only single-run detail panel.
- Scope: detail-only MVP for the selected history row, backed by the existing `history-show` storage read model.
- Out of scope: run compare, search/filter entry, detail previous/next persisted-run stepping, projection lens controls, live simulation monitoring, profile browsing, daemon control, run queueing, feed fetching, and any storage mutation.

### 2. Signatures

Rust CLI command remains unchanged:

```bash
tianji tui --sqlite-path <path> [--limit <N>]
```

Rust module boundary remains unchanged:

```rust
pub fn run_history_browser(sqlite_path: &str, limit: usize) -> Result<String, TianJiError>
```

Read dependencies:

```rust
list_runs(sqlite_path, limit, &RunListFilters::default())
get_run_summary(
    sqlite_path,
    selected_run_id,
    &ScoredEventFilters::default(),
    false,
    &EventGroupFilters::default(),
)
```

### 3. Contracts

- The TUI remains read-only and must not write SQLite, queue daemon jobs, call daemon IPC, fetch feeds, or start simulations.
- The detail view is reachable only from the history view for the currently selected persisted run.
- `Enter` from history opens detail for the selected row.
- `Esc` or `h` from detail returns to history without changing the selected history row.
- The detail payload uses existing `get_run_summary` semantics with default scored-event filters, default event-group filters, and `only_matching_interventions=false`.
- Detail formatting surfaces stable `history-show` root fields: `run_id`, `schema_version`, `mode`, `generated_at`, `input_summary`, `scenario_summary`, `scored_events`, and `intervention_candidates`.
- Event groups are read from `scenario_summary.event_groups`, preserving the storage read model where event groups are recomputed on read rather than persisted as a separate table.
- Missing or empty detail sections render stable placeholder text instead of panicking or fabricating state.

### 4. Validation & Error Matrix

| Condition | Behavior |
|-----------|----------|
| SQLite path does not exist before launching TUI | Return the existing empty-state message before launching the terminal |
| SQLite path is missing while loading detail | Return a missing-detail placeholder and do not create a SQLite file |
| Selected run is not found by `get_run_summary` | Render a missing-detail placeholder for that run id |
| `get_run_summary` returns a storage or JSON error | Render a detail error placeholder for that run id |
| User presses `Enter` outside history | Do not open detail; keep the current view |
| User presses `Esc` in detail | Return to history |
| User presses `h` in detail | Return to history |
| User presses history navigation while detail is active | Keep history selection unchanged |

### 5. Good/Base/Bad Cases

- Good: `tianji tui --sqlite-path runs/tianji.sqlite3` opens dashboard, `h` switches to history, and `Enter` opens detail for the selected persisted run.
- Base: a selected run with no scored events, event groups, or interventions renders explicit `No ... available.` placeholders.
- Bad: opening detail by querying SQLite without checking path existence first can create an empty database file and violates read-only TUI behavior.

### 6. Tests Required

- Unit-test detail mapping from a `get_run_summary`-shaped JSON payload.
- Unit-test detail formatting includes run metadata, input/scenario summary, scored events, event groups, and intervention candidates.
- Unit-test `Enter` opens detail only from history.
- Unit-test `Esc` and `h` return from detail to history.
- Unit-test missing detail path handling does not create a SQLite file.
- Re-run existing dashboard/history selection and key-handling tests to ensure behavior remains intact.
- Run `cargo fmt --check`, `cargo test`, and `cargo clippy -- -D warnings` after TUI detail changes.

### 7. Wrong vs Correct

#### Wrong

```rust
// Connection::open can create a new empty database file, violating read-only TUI behavior.
let detail = get_run_summary(sqlite_path, selected_run_id, filters, false, group_filters)?;
```

#### Correct

```rust
if !Path::new(sqlite_path).exists() {
    return DetailState::missing(selected_run_id);
}

let detail = get_run_summary(
    sqlite_path,
    selected_run_id,
    &ScoredEventFilters::default(),
    false,
    &EventGroupFilters::default(),
)?;
```

## Rust TUI Compare Contract

### 1. Scope / Trigger

- Trigger: Phase 4 extends the Rust TUI from dashboard/history/detail browsing to a read-only run compare panel.
- Scope: staged-pair compare MVP for two selected history rows, backed by the existing `history-compare` storage read model.
- Out of scope: search/filter entry, projection lens controls, detail previous/next stepping, compare previous/next target stepping, live simulation monitoring, profile browsing, daemon control, run queueing, feed fetching, and any storage mutation.

### 2. Signatures

Rust CLI command remains unchanged:

```bash
tianji tui --sqlite-path <path> [--limit <N>]
```

Rust module boundary remains unchanged:

```rust
pub fn run_history_browser(sqlite_path: &str, limit: usize) -> Result<String, TianJiError>
```

Read dependencies:

```rust
list_runs(sqlite_path, limit, &RunListFilters::default())
compare_runs(
    sqlite_path,
    staged_left_run_id,
    selected_right_run_id,
    &ScoredEventFilters::default(),
    false,
    &EventGroupFilters::default(),
)
```

### 3. Contracts

- The TUI remains read-only and must not write SQLite, queue daemon jobs, call daemon IPC, fetch feeds, or start simulations.
- The compare flow is reachable only from the history view.
- `c` in history stages the selected run as the left side of a compare pair.
- `Enter` in history opens detail when no left run is staged.
- `Enter` in history opens compare when a left run is staged, using the staged left run and the currently selected right run.
- Compare payloads use existing `compare_runs` semantics with default scored-event filters, default event-group filters, and `only_matching_interventions=false`.
- The history view must surface visible staged-left feedback before compare activates.
- Compare formatting surfaces stable `history-compare` fields: `left_run_id`, `right_run_id`, side summaries (`left`, `right`), and `diff` fields.
- Missing, invalid, or failed compare loads render stable placeholder/error text instead of panicking or fabricating state.

### 4. Validation & Error Matrix

| Condition | Behavior |
|-----------|----------|
| SQLite path does not exist before launching TUI | Return the existing empty-state message before launching the terminal |
| SQLite path is missing while loading compare | Return a missing-compare placeholder and do not create a SQLite file |
| `c` pressed outside history | Do not stage a compare run |
| `Enter` pressed in history without staged left | Open selected run detail |
| `Enter` pressed in history with staged left | Open compare for staged left vs selected right |
| Staged left and selected right are the same run | Render a stable invalid-pair placeholder |
| Either compare run is not found by `compare_runs` | Render a missing-compare placeholder for the pair |
| `compare_runs` returns a storage or JSON error | Render a compare error placeholder for the pair |
| User presses `Esc` or `h` in compare | Return to history without mutating storage |
| User presses history navigation while compare is active | Keep history selection unchanged |

### 5. Good/Base/Bad Cases

- Good: `tianji tui --sqlite-path runs/tianji.sqlite3` opens dashboard, `h` switches to history, `c` stages a left run, and `Enter` compares it against the selected right run.
- Base: a compare payload with empty diff or missing optional side fields renders explicit placeholders rather than panicking.
- Bad: computing compare diffs in the TUI duplicates storage/CLI logic and risks drift from `history-compare` semantics.

### 6. Tests Required

- Unit-test compare mapping from a `compare_runs`-shaped payload.
- Unit-test compare formatting includes left/right run IDs, side summaries, and diff fields.
- Unit-test `c` stages only from history.
- Unit-test `Enter` opens detail without a staged left run and opens compare with a staged left run.
- Unit-test invalid same-run pairs and missing paths render stable placeholders without creating SQLite files.
- Re-run existing dashboard/history/detail selection and key-handling tests to ensure behavior remains intact.
- Run `cargo fmt --check`, `cargo test`, and `cargo clippy -- -D warnings` after TUI compare changes.

### 7. Wrong vs Correct

#### Wrong

```rust
// Duplicates history-compare logic inside the TUI and can drift from storage semantics.
let diff = build_tui_only_diff(left_detail, right_detail);
```

#### Correct

```rust
if !Path::new(sqlite_path).exists() {
    return CompareState::missing(left_run_id, right_run_id);
}

let result = compare_runs(
    sqlite_path,
    left_run_id,
    right_run_id,
    &ScoredEventFilters::default(),
    false,
    &EventGroupFilters::default(),
)?;
```
