# Development plan: bounded scenario analysis

This document records architecture decisions and acceptance boundaries. Current behavior belongs in
[bounded-analysis.md](bounded-analysis.md); future increments belong in
[next-development.md](next-development.md). The repository is `VKKKV/contingent`; compatibility
identifiers remain `tianji_lab`, `./tianji` and `TIANJI_*`.

## Decisions

Keep FastAPI, SQLite, PydanticAI, React Flow/Dagre, Query core and the shared Web/CLI/MCP operation
registry. Use separate bounded same-model tasks for framing, strategies, critique, optional revision
and synthesis. Do not add a manager model, second runner, ORM, Redis, Celery or LangGraph without a
specific requirement that existing components cannot satisfy.

The deterministic kernel remains authoritative. Model output is structured proposal data and cannot
mutate state without validation and explicit operations. Task dependencies are acyclic; the issue
graph may contain feedback. Claims retain producing-task identity and evidence links; agreement never
sets a `verified` flag. Legacy single-call drafts remain readable without invented task histories.

The supply-chain page is removed, but its kernel, stored objects and HTTP/CLI/MCP operations remain.
The new analysis action explicitly creates a durable project; `vision_generate` remains ephemeral and
`vision_save` remains explicit. Network calls stay outside SQLite transactions. Cancellation prevents
later work and late commits; restart marks in-flight analysis interrupted rather than replaying it.

## UI boundary

The nixie assets are locally bundled from the pinned GPL source chain and display device UTC. The
meter is not a prediction score. React Flow/Dagre renders task and issue graphs; candidate paths are
not chronological timelines. Keep keyboard selection, focus, responsive layouts, reduced motion and
visible errors. Do not retain prompts, raw completions, hidden reasoning, mandatory reports or
screenshot archives.

## Research boundary

V2 adds bounded public search, controlled fetch, exact retained passages and task-visible citations.
This provides traceability, not fact checking, causal validity or independent corroboration. Retrieved
content is untrusted data. Enforce query/page/byte/time limits, DNS/redirect/SSRF controls, cancellation,
source pinning and atomic checkpoints. Follow-up research, user material, review, branching and export
are future increments; see [research-integration.md](research-integration.md).

## Acceptance

A change is complete only when real behavior, not fixtures alone, demonstrates:

1. Web, HTTP, CLI and MCP expose the same validated operation and error semantics.
2. Existing databases and compatibility operations still load; writes are idempotent and atomic.
3. Analysis shows actual task state, partial/cancelled/interrupted outcomes and unresolved objections.
4. Sources and passages are real, bounded, safely fetched and clickable; missing evidence is visible.
5. The UI works in populated, empty and error states on desktop/mobile with keyboard and reduced motion.

Use ordinary project tests and focused live checks. Report results directly; do not introduce a permanent
evaluation pipeline. Preserve concurrent uncommitted work and do not push without authorization.

## References

- https://github.com/FrancescoCaracciolo/DivergenceMeter
- https://pydantic.dev/docs/ai/guides/multi-agent-applications/
- https://reactflow.dev/learn/layouting/layouting
- https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation
- https://docs.langchain.com/oss/python/langgraph/overview