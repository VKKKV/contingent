# AGENTS.md — working notes for AI agents

TianJi keeps two stacks in one repository. Know which one you are touching.

- **Active product**: a local-first bidirectional world simulation laboratory in `backend/` (Python
  3.12, FastAPI, Pydantic v2, SQLite, official MCP stdio adapter) and `web/` (React 19, TypeScript
  strict, Vite).
- **Preserved legacy**: the Rust geopolitical intelligence pipeline in `src/`, `Cargo.toml`,
  `Cargo.lock`, `profiles/` and the existing `runs/*.sqlite3`. Treat all of it as read-only: do not
  modify, migrate or delete it without an explicit request from the maintainer.

## Where the knowledge lives

- `docs/README.md` — documentation index.
- `docs/laboratory.md` — operator/developer guide: build, serve, MCP setup, model semantics, limits.
- `docs/specs/lab/` — engineering contract for the active stack. Read it before changing schemas,
  operations, job lifecycle or the browser workflow.
- `docs/milestones/` — approved requirements, executable slice contracts and verification records.
- `docs/specs/rust/` — specs and code map for the preserved Rust code.
- `handoff.md` — current session state, delivered slices and the next slice. Update it when a slice
  lands or a session ends.

## Commands

```bash
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run format:check
npm --prefix web run build
uv run --project backend --group browser python scripts/check-lab-browser.py   # real Chromium
```

## Working agreements

- Commit work on the feature branch; never push or publish on your own initiative.
- Claims must come from real runs: tests, the browser acceptance script, or actual API/MCP calls.
  Never describe unverified behavior as delivered, and never substitute plausible-looking output for
  a result you could not produce.
- Determinism and honesty about the model matter more than feature volume: no fabricated data, no
  probability claims, no silent relabelling of results, no mock responses in the workbench.
- Keep the durable documents in step with behavior in the same change (`docs/`, `README.md`,
  `handoff.md`).
