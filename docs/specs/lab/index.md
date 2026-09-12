# Laboratory development guidelines

Scope: new `backend/` Python and `web/` TypeScript code. The user selected TypeScript + Python for the Web-first bidirectional world simulation laboratory. Legacy Rust remains preserved; never mutate runs/*.sqlite3 or remove src/Cargo files.

## Before development

Read the [M1 slice record](../../milestones/2026-09-m1-world-simulation-lab/prd.md), especially
[m1-contract.md](../../milestones/2026-09-m1-world-simulation-lab/m1-contract.md), then
[architecture.md](../../milestones/2026-09-m1-world-simulation-lab/architecture.md) for long-term
intent. Read [execution-contract.md](execution-contract.md) for current schemas, lifecycle, errors and
executable regression gates. The M1 contract governs exact models, operation names and bounded
acceptance; do not silently expand APIs or substitute demo responses. Read
[../guides/cross-layer-thinking-guide.md](../guides/cross-layer-thinking-guide.md). Milestone records
live under `docs/milestones/`; docs own only the paths assigned to them.

## Conventions

- Python >=3.12 with uv, Pydantic v2 strict bounded schemas, explicit typed errors and canonical state serialization. No eval/exec/imported scenario code. FastAPI request handling must not run CPU search on the event loop.
- TypeScript strict, React/Vite, no fabricated server state or unlabeled mock responses; real HTTP only for product data. Effects have cleanup/stale-result protection; keep browser state and agent workspace commands consistent.
- Human and MCP clients use one capability registry and service dispatch, same validation/auth/role projection. Separate desired workspace state from actual browser acknowledgement.
- Pure kernel, immutable input state, executable conservation constraints, bounded search, explicit search completeness. A candidate is feasible only after forward replay; no heuristic probability claims.
- SQLite transactions/idempotency and revision guards at mutation boundaries. Separate new data directory; no legacy migrations by default. Import verifies semantics, not only hashes, and uses bounded content with no arbitrary paths.
- Rule-driven characters are explicitly labeled; do not write pseudo-chat that pretends a model exists. API/MCP operability is required in M1, paid/model-backed agents are a later approved slice.

## Quality gate

Run uv pytest + ruff on backend, npm build/typecheck and frontend tests, actual FastAPI and official MCP SDK integration, and browser end-to-end flow. Test invalid inputs, stale revisions, auth/origin limits, role isolation, job interruption/cancel, bundle corruption, fork and replay. Compare goals/search with small finite-model oracles. Parent verifies all runtime claims and exact Git diff; implementation agents do not commit/push.
