# TianJi documentation

Hand-maintained documentation for this repository. No tool generates or owns these files.

## Start here

- [laboratory.md](laboratory.md) — operator/developer guide for the local laboratory: build, serve,
  MCP setup, model semantics, shared operation API, quality gates and known limits.
- [specs/lab/index.md](specs/lab/index.md) — engineering contract for `backend/` and `web/` (schemas,
  job lifecycle, error matrix, required regression tests) plus the laboratory conventions.
- [milestones/](milestones/) — approved requirements, executable slice contracts and verification
  records for each delivered slice.

## Reference

- [specs/rust/index.md](specs/rust/index.md) — the preserved legacy Rust implementation: scoring
  model, database/error/logging guidelines, contracts, development plan and
  [code map](specs/rust/code-map.md).
- [specs/guides/index.md](specs/guides/index.md) — cross-layer and code-reuse thinking guides used by
  both stacks.

## Milestones

| Slice | Date | Record |
|-------|------|--------|
| M1 — bidirectional laboratory: forward runs, goal search, fork, compare, replay | 2026-09-10 | [prd](milestones/2026-09-m1-world-simulation-lab/prd.md), [contract](milestones/2026-09-m1-world-simulation-lab/m1-contract.md), [architecture](milestones/2026-09-m1-world-simulation-lab/architecture.md), [verification](milestones/2026-09-m1-world-simulation-lab/research/m1-verification.md) |
| M2 slice 1 — exogenous disturbances with recorded replay | 2026-09-12 | [prd](milestones/2026-09-m2-exogenous-disturbances/prd.md), [contract](milestones/2026-09-m2-exogenous-disturbances/m2-contract.md), [verification](milestones/2026-09-m2-exogenous-disturbances/research/m2-verification.md) |

Each slice directory keeps its real browser acceptance report under `research/`. The next slice
(multi-actor private observation with independent adjudication) has not started; the confirmation
gates for model providers, legacy data migration, remote deployment and real-world action integration
are recorded in [laboratory.md](laboratory.md) and `handoff.md`.
