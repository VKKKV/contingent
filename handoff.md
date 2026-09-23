# Current development state

Product: Contingent. Repository: https://github.com/VKKKV/contingent.
Product intent is [goal.md](goal.md); this file records current behavior only.

Implemented:

- Durable goal-directed analysis runs use separate bounded same-model calls for framing, strategies,
  critique, optional revision and synthesis. Task dependencies and issue relations are distinct
  React Flow/Dagre views.
- `analysis_start_v2` performs bounded public search/fetch before downstream analysis, stores source
  snapshots, exact passages and task-visible citations atomically, and supports explicit online/offline
  mode. `analysis_start`/`analysis_list` remain offline v1.
- `research_evidence` provides an authenticated cursor-paginated read model for v2 source snapshots
  and exact passages. It is additive: `analysis_get` still returns the complete bounded v2 snapshot,
  and old v1/v2 projects remain readable.
- `research_frontier` exposes the bounded v2 query frontier as an authenticated cursor-paginated read
  model. It records framing queries, priority, attempted/skipped/stop state and explicit gaps without
  claiming query-level source attribution.
- The old supply-chain Web page is removed. Its deterministic kernel, stored data and HTTP/CLI/MCP
  operations remain compatible; legacy `vision_*` analysis remains single-call and explicitly saved.
- The UTC nixie clock, local particle background, shared graph controls and responsive analysis UI are
  implemented. Full cross-state visual reproduction is still an acceptance boundary.
- Web, CLI and MCP use the same authenticated operation registry. Projects retain structured results,
  not raw prompts, completions, hidden reasoning or per-event traces.

Known boundaries:

- Research is bounded and does not prove facts, causality or source independence. DDGS Brave search
  has no exact provider-response byte accounting; public fetch validates and pins addresses.
- Critique-triggered follow-up research, resumable reruns, user-material attachment, human review,
  assumption branches and portable packages are not implemented.
- The paginated evidence read model currently mirrors the bounded v2 snapshot; it does not yet add a
  source-version deduplication beyond a run, lexical passage selection, or critique-triggered follow-up
  collection. The frontier is currently projected from one bounded run, not a resumable cross-run queue.
- `TIANJI_RESEARCH_DNS=cloudflare` is an explicit opt-in for environments with fake-IP DNS; otherwise
  the system resolver is used and non-public answers fail closed.

Run `./start.sh`; use [docs/README.md](docs/README.md) as the documentation index. Preserve existing
user data.