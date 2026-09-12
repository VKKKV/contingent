# TianJi handoff

## M2 slice 1 delivered - exogenous disturbances with recorded replay (2026-09-12)

Status: implemented, verified and committed on branch `feat/world-simulation-lab`. Nothing was
pushed. Task record (prd, executable contract, verification, browser report) is archived at
`.trellis/tasks/archive/2026-09/09-12-m2-exogenous-disturbances/`.

### What this slice delivers

- Scenario specification gains a bounded, explicit `disturbances` schedule: `demand_spike` (1..20) and
  `supplier_loss` (1..200), at most ten entries, at most one per tick and kind, and no tick beyond
  the horizon. There is no random number generator and no seed, so replay never needs a draw log.
- Kernel order inside a turn: the actor's action executes, the clock advances and due shipments
  arrive, the exogenous events declared for that tick apply, then demand for that tick is served.
  A declared loss is clamped to the remaining supplier stock and never carries forward. Because the
  order executes first, buying ahead of a declared disruption protects those goods - intended
  planning pressure, documented in `docs/laboratory.md`.
- Conservation gained the explicit `lost` account, and cumulative-demand accounting now includes
  declared spikes, so the executable invariants stay exact.
- The rule label is derived from the frozen specification: empty schedule = `supply-chain.v1`,
  non-empty = `supply-chain.v2`. `_verify_branch` rejects a branch whose label or provenance
  contradicts its specification instead of relabelling it.
- No new operations: HTTP, MCP and the browser editor all read the same capability schema, and the
  browser's schedule editor validates locally while the server stays authoritative.
- Pre-slice bundles still import and replay under v1 semantics (the digest covers the supplied branch
  object, so missing `disturbances`/`lost` keys remain valid).

### Verification evidence (2026-09-12)

- backend: 103 pytest passed; `ruff check` + `ruff format --check` clean.
- frontend: 18 vitest passed; prettier clean; real `npm run build` ok.
- real browser acceptance (Chromium 151.0.7922.34, isolated data directory): 17 checks passed - the
  16 M1 checks plus the schedule editor, client-side rejection, timeline markers, `lost`, the real
  forward run on a scheduled scenario, and export/import round-trip. Report:
  `.trellis/tasks/archive/2026-09/09-12-m2-exogenous-disturbances/research/browser-acceptance-m2.json`.
- MCP path verified through the official SDK: scheduled scenario created and run through the adapter
  returns `rule_version = supply-chain.v2` with the real loss.
- Legacy Rust tree untouched; the 8 existing `runs/*.sqlite3` files untouched.

### Known limits of this slice

- Disturbances are an explicit schedule only. No stochastic draws, no probability output, and no
  claim that a schedule describes the real world.
- Still a single director actor: kernel `observe` role projections exist but are not deployed
  authorization, and there is no adjudication record.
- The schedule cannot reference anything but the two declared event kinds; scenario packs, evidence
  initialization and maps remain M3 work.

### Next slice (not started)

Multi-actor private observation with independent adjudication, keeping the same-model forward
verification for goal plans, plus baseline/sensitivity experiments across schedules. Confirmation
gates remain: model provider/budget, legacy data migration, remote deployment and real-world action
integration.

---

## M1 delivered - bidirectional world simulation laboratory (2026-09-10)

Status: the approved TypeScript/Python first slice (M1) is implemented and verified on branch `feat/world-simulation-lab` (base `a5a3c656`). **Committed on 2026-09-12** as `b3ddef8`, `8532815`, `39aeef8`, `b8ed4ff`, `cd1f616` (see the M2 slice-1 section above); nothing was pushed. Legacy Rust (`src/`, Cargo files, `profiles/`) and `runs/*.sqlite3` remain untouched.

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

### Commit plan (executed 2026-09-12)

The five planned commits were executed on branch `feat/world-simulation-lab` with no push:
`b3ddef8` (backend), `8532815` (web), `39aeef8` (browser acceptance script), `b8ed4ff`
(root docs, guide, ignore rules), `cd1f616` (Trellis task and lab spec). The follow-up documentation
cleanup commit is `f69108f`.

### Resume

- Task: `.trellis/tasks/09-10-world-simulation-lab/` (status `in_progress`; `python3 .trellis/scripts/task.py list` shows it).
- Run: see `docs/laboratory.md` (build, serve, MCP setup, browser acceptance).
- Next slice: exogenous disturbances were delivered by `09-12-m2-exogenous-disturbances` (see the top
  section). Multi-actor private observation/adjudication remains next, keeping same-model forward
  verification for goal plans. Confirmation gates remain: model provider/budget, legacy data
  migration, remote deployment, real-world action integration.

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
