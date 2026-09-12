# TianJi M2 slice 1 — exogenous disturbances with recorded replay

Status: implementation authorized 2026-09-12 by the repository owner ("continue dev"). This slice
extends the verified M1 laboratory. It needs no paid model provider, no legacy data migration and no
remote deployment, so it stays inside the standing confirmation gates recorded in
`09-10-world-simulation-lab/architecture.md`.

## Why

M1's kernel has no exogenous events at all, and `docs/laboratory.md` states that explicitly: "There
are no random disturbances in M1, so a seed would be misleading bookkeeping." That makes forward
exploration and goal planning too easy: a plan never has to survive anything the actor did not
choose, and the "conditional future" the product promises is only conditional on the actor's own
actions.

Real conditional futures need a second source of variation that is (a) explicit, (b) operator
visible, (c) frozen with the scenario, and (d) exactly replayable without a model call. The M2
direction recorded in `handoff.md` is "exogenous disturbances and multi-actor private
observation/adjudication while keeping same-model forward verification for goal plans". This slice
delivers the first half; the multi-actor half stays a separate slice.

Deliberate design choice: **no random number generator and no seed.** Disturbances are an explicit
schedule in the scenario specification, so "reproducible" never depends on hidden bookkeeping and
"replay" does not need a draw log. A seeded PRNG is a later slice, and only with a recorded draw log
that the import verifier consumes.

## User-approved requirements carried over

- Keep the bidirectional core (forward exploration plus backward goal planning) rather than
  regressing into a dashboard.
- Every product capability stays reachable through the shared operation registry, so Web, HTTP and
  MCP keep parity; the browser is not a privileged implementation.
- Never label model-conditional results as predictions or probabilities.
- Preserve the legacy Rust source and the existing databases; no destructive migration.

## Scope of this slice

In scope:

- Scenario specification gains a bounded, explicit disturbance schedule.
- Kernel applies it deterministically, with conservation and demand accounting extended so the
  executable invariants still hold exactly.
- Goal search plans against the schedule with the same forward model; no new search shortcut.
- HTTP/MCP expose the schedule through the existing scenario operations and capability schema.
- Browser workbench can edit the schedule, shows it on the timeline and shows the applied events.
- Export/import keeps working, including bundles produced under the pre-disturbance rules.

Out of scope (still gated or deferred):

- Seeded randomness, stochastic draws, probability estimates.
- Multi-actor decision ownership, private observation barriers between actors, adjudication records.
- Model/LLM-backed director loops, provider spend, remote deployment, real-world action integration.

## Acceptance criteria

- [ ] Backend quality gates pass: `uv run --project backend --locked pytest backend/tests`, `ruff
      check`, `ruff format --check`.
- [ ] Frontend quality gates pass: `npm --prefix web test`, `npm run format:check`, `npm run build`.
- [ ] Real-browser acceptance (`scripts/check-lab-browser.py`) passes with new disturbance checks.
- [ ] A goal plan that only succeeds by ignoring the schedule is rejected by forward verification;
      a plan that adapts to the schedule is returned as `found`.
- [ ] Pre-disturbance bundles still import and replay; a schedule-bearing bundle labelled with the
      pre-disturbance rules is rejected.
- [ ] Documentation matches the delivered behavior: `docs/laboratory.md`, `README.md`,
      `.trellis/spec/lab/execution-contract.md`, and this task's contract.
- [ ] Legacy Rust files and existing `runs/*.sqlite3` remain untouched.

## Sources

- `.trellis/tasks/09-10-world-simulation-lab/m1-contract.md` — current executable M1 contract.
- `.trellis/tasks/09-10-world-simulation-lab/architecture.md` — milestone definitions and gates.
- `docs/laboratory.md` — operator guide for the delivered M1 behavior.
- `.trellis/spec/lab/execution-contract.md` — current schemas, lifecycle, errors, regression gates.
