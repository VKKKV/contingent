# M2 slice 1 verification record - 2026-09-12

All commands were run locally on the development host, on branch `feat/world-simulation-lab`
(base `f69108f`). Nothing was pushed. No provider call, no legacy database and no remote service
was involved.

## Backend (`uv run --project backend --locked ...` from the repository root)

- `pytest backend/tests` -> **103 passed** (2 deprecation warnings from starlette/httpx only).
  New coverage: disturbance invariants and event ordering, clamping and no carry-forward, schedule
  bounds rejection (out-of-horizon tick, duplicate tick+kind, out-of-range and wrong-typed amounts,
  unknown kind, >10 entries), rule-label derivation and mislabelling rejection, schedule-aware goal
  search against an independent exhaustive oracle (35 randomised scheduled specs), schedule-free
  specs refusing a loss, MCP-created scheduled scenario through the official SDK, pre-slice bundle
  import plus mislabelled-schedule rejection, and schedule freezing across a later scenario revision.
- `ruff check backend` -> clean; `ruff format --check backend` -> 15 files already formatted.
- The published `scenario_create` capability schema (served to both HTTP and MCP) contains
  `disturbances` with `maxItems: 10` and a `$ref` to the `Disturbance` definition, so agent parity
  needed no new operation or adapter change.

## Frontend (`npm --prefix web ...`)

- `npm test` -> **18 passed** (was 12; the new cases cover schedule validation, draft isolation and
  the derived labels).
- `npm run format:check` -> all matched files use Prettier code style.
- `npm run build` -> ok (`dist/assets/index-DGiKQJ3I.js` 268.52 kB, 83.96 kB gzip).

## Real-browser acceptance (`scripts/check-lab-browser.py`)

Real Chromium 151.0.7922.34 against an isolated temporary data directory, one server, one MCP stdio
client. **17 checks passed** - the 16 M1 checks plus:

- the browser declares a real schedule (tick 2 需求激增 3, tick 3 供应损失 40), saves it, and the
  stored revision contains exactly that schedule;
- lowering the horizon below a declared tick shows the editor's own error, refuses the save with a
  visible message and never sends the invalid schedule to the server;
- discarding the local edits reloads the saved schedule into the editor (count 2, tick 3);
- a real forward run on the scheduled scenario returns `rule_version = supply-chain.v2`, the tick-2
  frame reports `demand 4 -> 7`, the tick-3 frame reports `declared 40, lost 40, stock 40 -> 0`,
  `lost = 40`, `shortage = 3` and `delivered + shortage = 3 * 4 + 3`;
- the timeline shows the real disturbance legend and both tick markers, and the state grid shows
  `lost = 40` at T3;
- export plus re-import through the real API keeps the schedule and replays to an identical
  trajectory;
- 768px and 390px layouts still have no horizontal overflow with the schedule editor rendered;
- no uncaught browser JavaScript errors.

Report: `research/browser-acceptance-m2.json` (copied from the run's artifact directory).

## Legacy preservation

- `git status --porcelain src/ Cargo.toml Cargo.lock profiles/ scripts/check-eval.sh
  scripts/check-replay-smoke.sh` -> empty; no Rust file was modified in this slice.
- The 8 existing `runs/*.sqlite3` files are untouched; the laboratory stores live in a separate
  temporary data directory.
