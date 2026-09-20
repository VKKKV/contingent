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
- `TIANJI_RESEARCH_DNS=cloudflare` is an explicit opt-in for environments with fake-IP DNS; otherwise
  the system resolver is used and non-public answers fail closed.

Run `./start.sh`; use [bounded analysis](docs/bounded-analysis.md) and
[online research](docs/research-integration.md) for canonical details. Preserve existing user data.