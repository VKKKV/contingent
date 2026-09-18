# M2 slice 2 verification — 2026-09-18

Status: implemented and verified offline; working tree intentionally uncommitted for maintainer
review. Starting HEAD `27cb737`, branch `feat/world-simulation-lab`. No commit/push, provider calls,
baseline/sensitivity harness, legacy migration or remote deployment was performed.

## Delivered behavior

- Typed, deeply immutable retailer/supplier observations bound to frozen branch/revision/spec/tick
  and audit identity, with deterministic projection/envelope hashes and explicit role allowlists.
  Retailers do not receive supplier stock or supplier loss accounting. No full-state hash is exposed
  in participant projections; hashes are integrity checks, not authentication.
- One proposal per independent kernel adjudication. Supplier may only wait; forbidden/illegal/stale
  proposals are rejected without substituted actions. Rejection binds unchanged pre/post-state hashes.
  Malformed/cross-identity/self-adjudicated requests fail validation.
- Five durable director operations shared by HTTP and official MCP: observation create/get;
  adjudication create/get/list. Records survive restart; request IDs are transactional/idempotent;
  each branch is capped at 100 observations and 100 adjudications. Reads check receipt hashes,
  next-state hashes and relational identity. Branches/jobs/workspace are not mutated by previews.
- Director Web panel with exact projection JSON, manual proposals, real persisted readback,
  accepted/rejected previews, history refresh/reconnect and selection-scoped stale-response guards.
  Role/actor/referee are audit labels, not authenticated participants. No product FakeActor call.

## Main-agent execution

All commands ran in the real repository, using isolated temporary databases for tests:

```sh
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend scripts/check-lab-browser.py
uv run --project backend --locked ruff format --check backend scripts/check-lab-browser.py
npm --prefix web test
npm --prefix web run format:check
npm --prefix web run build
uv run --project backend --group browser python scripts/check-lab-browser.py
git diff --check
```

Results:

- Backend: **197 passed**, including pure kernel/core, real HTTP, persistence/restart, caps,
  idempotency/rollback, frozen/import/fork identity, corruption rejection and official MCP stdio.
- Frontend: **44 passed** across three test files; deferred responses, changed scope, rejected
  actions, readback failure, capability absence and control rendering covered.
- Ruff check/format: pass for backend plus browser script; Prettier, TypeScript and Vite build pass.
- Real Chromium `151.0.7922.34`: **23 checks passed**, **21 shared API/MCP operations**. Raw report:
  [browser-acceptance-m2.json](browser-acceptance-m2.json).
- Regenerable screenshots/download artifact: `/tmp/tianji-browser-qbiesjz1/`; prior independent
  browser run: `/tmp/tianji-browser-pnt35e8a/`. Both runs passed the expanded workflow.

The browser test uses actual service responses, real kernel transitions and real official MCP
calls. It checks exact role projection allowlists, accepted preview equality with `kernel.step`,
supplier rejection, unchanged source branch and branch list, refresh/reload history, and observes
consumption of held stale branch/observation responses before asserting the newer selection wins.
Populated panel and full page have no horizontal overflow at 1440/768/390px. No uncaught JavaScript
errors occurred. Auxiliary visual-model inspection returned 503 and is **not claimed**; screenshots,
DOM geometry and interaction checks succeeded.

Two upstream Python deprecation warnings remain: Starlette TestClient's httpx path and AnyIO's
BlockingPortal alias. They did not fail any tests; dependencies were not opportunistically upgraded.

## Independent review and fixes

Read-only core/service review found no blocking supported-API bug. Additional isolated probes covered
concurrent identical request IDs, caps under concurrent writes, injected transactional failures,
disturbance preview parity and source-branch replay corruption. The reviewer identified an optional
storage integrity gap: corrupted receipt JSON bypassed validation on get/list. The parent implemented
shared readback validation and six corruption regressions, then reran the entire backend suite.

Frontend integration initially had two stale type assumptions (retailer `lost`, nullable rejection
post-state hash); these were aligned with the backend and production TypeScript was rerun. The browser
script's existing nested MCP context-manager Ruff warning was fixed while verifying the full script.

## Preservation and next gate

An 80-file SHA-256 snapshot of `src/`, `profiles/`, Cargo files and existing `runs/*.sqlite3` was
unchanged after implementation; the legacy Git diff is empty. Tests never use those databases.
The public v1 branch export schema is unchanged; adjudication sidecars are deliberately not exported.

This verifies the offline slice, not the entire model-assisted M2 milestone. Continuing to a real
provider requires an explicit provider/model/budget decision and permission for a live smoke call.
Participant credentials, simultaneous turn/conflict rules, new supplier commands, remote deployment,
legacy data migration and real-world actions require separate contracts/approval. The next agent
must preserve the current no-commit/no-push and no-baseline/sensitivity-harness boundaries.
