# TianJi handoff

## M1 delivered - bidirectional world simulation laboratory (2026-09-10)

Status: the approved TypeScript/Python first slice (M1) is implemented and verified on branch `feat/world-simulation-lab` (base `a5a3c656`). **Nothing is committed yet; the task worktree is intentionally uncommitted** - commit plan below. Legacy Rust (`src/`, Cargo files, `profiles/`) and `runs/*.sqlite3` are untouched.

### What M1 delivers

- `backend/` (Python 3.12, FastAPI + Pydantic v2 + SQLite + official MCP stdio adapter): deterministic fictional supply-chain kernel (`supply-chain.v1`) with forward simulate/replay, conservation invariants, bounded model-conditional goal search re-verified by the same forward model, and role observation projections. One validated operation registry (16 operations) shared by HTTP and MCP; durable bounded jobs (queue cap 32, 50k search nodes, 30 s subprocess limit; cancel prevents result commit; restart marks running jobs interrupted); revision-guarded workspace desired-state; versioned JSON export/import with semantic replay and provenance preservation.
- `web/` (React 19 + TypeScript strict + Vite): the workbench - scenario editor, per-tick action forward runs, goal search with budget statuses, recorded-tick forks, comparison, time cursor + SVG trace + event log, real JSON import/export, job polling/cancel, frozen-vs-current revision warnings, and workspace polling that mirrors external MCP selection (scenario/branch/comparison/tick/panel).
- `scripts/check-lab-browser.py`: real Chromium acceptance against an isolated temp data directory, including an official MCP client controlling the visible browser.
- `docs/laboratory.md`: operator/developer guide (model semantics, API/MCP contract, quality gates, limitations).
- `.trellis/tasks/09-10-world-simulation-lab/`: prd, m1-contract, architecture, research (language choice/evidence, `m1-verification.md`); `.trellis/spec/lab/{index,execution-contract}.md`.

### Verification evidence (re-run 2026-09-10 after the fixes below)

- backend: 87 pytest passed; ruff check + format clean (includes real CLI service and official MCP SDK stdio tests).
- frontend: fresh-snapshot `npm ci` + build + 12 vitest passed; prettier clean; `npm audit` 0 vulnerabilities; uv lock in sync; pip-audit no known vulnerabilities.
- browser e2e (Chromium 151, isolated local server): 16 checks passed - scenario create/edit/readback, forward with real time cursor, goal search + comparison, recorded-tick fork without parent mutation, JSON download/upload replay import, MCP-driven comparison/empty-scenario/branch selection visibly applied, reload without stale job replays, concurrent-edit 409 preserving the user draft, budget-exhausted vs finite no-solution, malformed import rejection, real cancellation, no console errors, layout at 1440/768/390 px.
- legacy: 94-file sha256 baseline unchanged; no legacy database opened or migrated.

### Fixed during review (reproduced, then fixed with regression tests)

- A second `Service` on the same data directory could relabel a running job `interrupted` -> exclusive ownership lock acquired before restart recovery; real running-cancel and restart covered by `test_lifecycle.py`.
- Import accepted unbounded revisions (HTTP 500) -> revisions bounded to int32; repeated import preserves `imported_parent_id`; forged fork start snapshots rejected by prefix replay.
- Stale-branch window on external switch (fork/compare could act on a workspace/branch mismatch) -> the browser clears the branch while a new one loads; MCP-driven switching re-verified end to end.
- Published workspace schema accepted null but dispatch rejected it -> explicit null now equals omitted for scenario/tick/panel; branch/comparison null clears that selection.
- Non-uniform error envelope for 405 -> unified JSON envelope.

### Known limits (not claimed)

Fictional deterministic model; no probabilities, LLM or chat; single local director token (kernel role projections are not deployed authorization); no SSE/pause-resume; loopback single user. Suggested follow-up: a delayed-`branch_get` regression for the stale-branch class (currently covered by design + spec, not an automated browser check).

### Uncommitted worktree and proposed commit plan

`git status`: modified `.gitignore`, `.trellis/spec/backend/index.md`, `README.md`, `handoff.md`, `plan.md`; untracked `.trellis/spec/lab/`, `.trellis/tasks/09-10-world-simulation-lab/`, `backend/`, `docs/`, `scripts/check-lab-browser.py`, `web/`.

Proposed commits (execute only after one-shot confirmation; never push):

1. `feat(lab): add Python simulation service, HTTP API and MCP adapter` - backend/
2. `feat(lab): add React workbench for forward/goal/branch workflows` - web/
3. `feat(lab): add real-browser acceptance script` - scripts/check-lab-browser.py
4. `docs: record laboratory direction and operator guide` - README.md, plan.md, handoff.md, docs/, .gitignore
5. `chore(trellis): record world-simulation-lab task and lab spec` - .trellis/

### Resume

- Task: `.trellis/tasks/09-10-world-simulation-lab/` (status `in_progress`; `python3 .trellis/scripts/task.py list` shows it).
- Run: see `docs/laboratory.md` (build, serve, MCP setup, browser acceptance).
- Next slice (M2, not started): exogenous disturbances and multi-actor private observation/adjudication while keeping same-model forward verification for goal plans. Confirmation gates remain: model provider/budget, legacy data migration, remote deployment, real-world action integration.

---

The remainder of this file is the retained legacy Rust handoff (historical).

Date: 2026-06-09
Repo: `/home/kita/code/tianji`
Branch: `main`
Agent workflow: Hermes plans/verifies/commits; OpenCode implements non-trivial Rust code changes with model `jun/gpt-5.5`. Do not let OpenCode commit unless explicitly requested.

## Current status

Active task: none. Last completed task: `.trellis/tasks/archive/2026-06/06-09-roadmap-closure/`.

The explicit Post-K roadmap in `plan.md` is complete. Future runtime behavior changes should start from a new PRD and remain local-first by default.

## Completed Post-K closure

- Refreshed release/readiness handoff after K3/K4 was already committed.
- Added `scripts/check-replay-smoke.sh` as a credential-free `/tmp`-only replay bundle + TUI render-once gate.
- Improved replay/audit ergonomics with replay controls, selected-frame replay summary, and audit coverage counts in TUI replay output.
- Closed `plan.md` so it no longer advertises unfinished explicit Post-K candidate directions.

## Current shipped Phase K behavior

- `tianji predict --trace-jsonl <PATH>` writes `tianji.sim-trace.v1` JSONL traces.
- `tianji predict --replay-bundle-dir <DIR>` writes a local replay bundle containing `manifest.json`, `trace.jsonl`, and `outcome.json`.
- `tianji tui --trace-jsonl <PATH> [--render-once]` loads trace-backed simulation replay without provider execution.
- `tianji tui --replay-bundle-dir <DIR> [--render-once]` reads only the three replay bundle files above.
- Replay bundle validation checks schema version, fixed file names, trace/outcome sizes, frame counts, and manifest mode/target/horizon against trace metadata.
- Simulation replay scrubbing with `Left`/`h` and `Right`/`l` updates the selected frame display, including field metadata, replay controls, field changes, event sequence length, structured agent audit fields, and audit coverage counts.
- Trace strings are sanitized before rendering.
- Replay flags conflict with each other and with `--simulate`.
- Plain `tianji tui` defaults to `runs/tianji.sqlite3`.

## Verified counters

Measured on 2026-06-09:

```text
Rust lines/files: 30,465 / 59
cargo test -- --list: 445 tests
```

## Recommended verification before commit

```bash
cargo fmt --check
bash scripts/check-eval.sh
bash scripts/check-replay-smoke.sh
cargo test --quiet
cargo clippy -- -D warnings
git diff --check
```

## Optional local replay smoke

```bash
bash scripts/check-replay-smoke.sh
```

Expected output is a compact JSON summary with bundle files, schema version, frame count, trace record count, and TUI render byte count. The script writes transient files only under `/tmp` and does not use provider config, network, daemon/API, live feeds, or secrets.
