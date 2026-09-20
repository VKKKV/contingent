# Contingent documentation

Read documents in this order:

1. [Product goal](../goal.md) — product identity, user promise and non-negotiable boundaries.
2. [Laboratory guide](laboratory.md) — run the service, use the Web/CLI/MCP and understand legacy
   deterministic operations.
3. [Bounded analysis](bounded-analysis.md) — current v1/v2 analysis behavior, lifecycle, graphs and
   resource limits.
4. [Online research](research-integration.md) — current public search/fetch/citation implementation,
   privacy and known limitations.
5. [Execution contract](specs/lab/execution-contract.md) — cross-layer operation and compatibility
   contract; authoritative when implementation changes it.
6. [Development conventions](specs/lab/index.md) — short engineering rules.

Planning and state:

- [Current state](../handoff.md) — concise implementation snapshot, not a session log.
- [Next development](next-development.md) — future product increments only.
- [Development plan](development-plan.md) — short architecture decisions and accepted boundaries.
- [Worldlines and adaptive research](worldlines-and-research.md) — future evidence-frontier design and
  interaction direction; source-level references are design inputs, not installation or benchmark claims.

Keep current behavior in the implementation documents above. Do not duplicate command lists,
contracts or transient test totals across documents; link to the canonical document instead.
Third-party/vendor README files retain their upstream notices and are outside this documentation map.