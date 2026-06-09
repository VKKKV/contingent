# Documentation alignment review

## Goal

Review TianJi's project documentation against the current Rust implementation and align stale or contradictory docs.

## Scope

Documentation-only unless a verification command reveals an actual code bug that blocks documentation truth.

Audit and update:

- `README.md`
- `plan.md`
- `handoff.md`
- relevant `.trellis/spec/**` guidance if stale enough to mislead future agents
- release/readiness counters that docs record

Focus areas:

- CLI subcommands and flags match `src/main.rs`.
- README repository layout matches current `src/` files.
- dependency lists match `Cargo.toml`.
- test counts and Rust line/file counts are generated from real commands.
- roadmap/handoff state does not mention stale dirty worktree or unfinished explicit candidates.
- local-first/no-secrets safety language remains correct.

## Verification

Run:

```bash
cargo fmt --check
bash scripts/check-eval.sh
bash scripts/check-replay-smoke.sh
cargo test --quiet
cargo clippy -- -D warnings
git diff --check
```
