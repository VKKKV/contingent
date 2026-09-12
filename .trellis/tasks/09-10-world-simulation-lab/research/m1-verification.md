# M1 verification record - 2026-09-10

Re-run on branch `feat/world-simulation-lab` after the review fixes. All commands run locally on the development host.

## Backend (`uv run --project backend --locked ...` from repo root)

- `pytest backend/tests` -> **87 passed** (kernel oracles and conservation, service/idempotency/frozen specs, import metadata bounds, lifecycle single-owner + real cancel, workspace CAS + null semantics, real CLI HTTP subprocess + official MCP SDK stdio).
- `ruff check` and `ruff format --check` -> clean.
- `uv lock` in sync; `uvx pip-audit` against exported requirements (no-deps) -> no known vulnerabilities.

## Frontend (`npm --prefix web ...`)

- `npm ci` (fresh snapshot, no node_modules/dist) -> ok; `npm run build` (tsc + vite) -> ok.
- `npm test` -> **12 passed**.
- `npm run format:check` -> clean.
- `npm audit` -> 0 vulnerabilities.

## Real-browser acceptance (`scripts/check-lab-browser.py`)

Real Chromium 151.0.7922.34 against an isolated temporary data directory; 16 checks:

- connect and capability-generated scenario constraints
- browser creates, edits and reads back scenario
- browser forward trajectory, actual time cursor and shortage display
- browser goal search, same-model verified candidates and comparison
- browser recorded-tick fork, changed action, unchanged parent
- browser real JSON download, upload and semantic replay import
- official MCP selects a comparison target rendered by the browser
- official MCP selects an empty scenario without inventing a branch
- MCP registry matches API; external branch/tick/panel visibly applied
- reconnect preserves MCP workspace instead of replaying old job selections
- concurrent scenario edit returns 409 and preserves unsaved human draft
- browser distinguishes incomplete budget from finite-model no solution
- malformed browser import visibly rejected
- browser cancels actual queued/running work
- desktop/768px/390px layout without horizontal page overflow
- no uncaught browser JavaScript errors

Result: all checks passed; `search_expanded=306`; goal plan ends at shortage 0 / spent 32; report copied to `research/browser-acceptance-m1.json`.

## Legacy preservation

- 94-file sha256 baseline over `src/`, Cargo files, `profiles/`, `scripts/` -> unchanged.
- No legacy database opened, migrated or deleted; laboratory stores live in a separate data directory with an exclusive owner lock.
