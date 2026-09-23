# Bounded analysis projects

This document is the canonical description of current analysis execution. The CLI and HTTP examples
below use the shared operation registry; the cross-layer schema is in
[execution-contract.md](specs/lab/execution-contract.md).

## Versions and research

`analysis_start` creates durable offline v1 projects. `analysis_start_v2` creates v2 projects, online
by default; `analysis_list_v2` lists both versions and `analysis_get` preserves the stored version.
Existing v1 requests and saved drafts remain offline and are never silently upgraded.
`research_evidence` reads v2 sources or exact passages through an authenticated cursor-paginated
operation. It is an additive read model and does not refresh or rerun research.
`research_frontier` reads the proposed/attempted query frontier through the same authenticated
cursor-paginated registry; it is a durable read model, not a continuation action.

For v2, framing proposes bounded queries, a controlled collector searches and reads public sources,
and later roles receive selected exact passages. Source snapshots, passage hashes/spans, task
visibility and validated citations are stored atomically with the run. Missing research or citations
produce a partial result even when model tasks finish. Explicit offline v2 is hypothesis-only/partial.
Critique-triggered follow-up search and user-material attachment are not implemented.
See [research integration](research-integration.md) for provider, DNS, privacy and byte limits.
The service also mirrors validated v2 sources/passages into a transactionally maintained paginated
read model; the run JSON remains the compatibility representation and source of truth for old clients.

## Operations

```bash
./tianji schema analysis_start_v2
./tianji call analysis_start_v2 --json '{"request":{"vision":"减少社区夏季高温伤害","horizon":"未来两年","constraints":"有限公共预算"}}'
./tianji call job_get --json '{"id":"RUN_ID"}'
./tianji call analysis_get --json '{"id":"RUN_ID"}'
./tianji call analysis_list_v2
./tianji call job_cancel --json '{"id":"RUN_ID"}'
```

Start returns a queued job, not a completed analysis. Read current state with `job_get` or
`analysis_get`. Creation is idempotent: reuse the same mutation request ID and arguments to recover
an uncertain response without starting another project.

## Execution model

A deterministic coordinator makes separate PydanticAI typed calls to the same loopback llama.cpp
model. There is no manager-model call and no agent-controlled shell, filesystem or retrieval tool.
Each strategy receives the user request, framing result and its own perspective, not another
strategy's first draft.

- Framing defines observable criteria, assumptions, unknowns and one to three perspectives. A
  clarification need can stop downstream work with a partial result.
- Each perspective produces its own claims and intervention.
- A critic references concrete strategy claim IDs and proposes testable objections.
- At most one strategy receives a targeted revision.
- Synthesis retains alternatives and unresolved questions; agreement never creates verified facts.

The number of perspectives follows framing within resource ceilings; it is not a fixed five-node
shape. Same-model roles are separately executed tasks, not independent evidence, empirical validation
or calibrated prediction. V1 has no retrieval; V2 has bounded retrieval, not fact checking.

## Lifecycle and limits

Default ceilings are eight model calls, eight tasks, one revision pass, 900 seconds and 16,000
reserved output tokens. Server maxima are 1,200 seconds and 20,000 reserved tokens. Per-call output
ceilings are 1,000 framing, 1,600 strategy/revision, 1,400 critic and 1,200 synthesis tokens. The
full ceiling is reserved before each call, including failures. No automatic SDK/validation retry is
enabled; resource exhaustion preserves completed structured results as partial.

The model slot is shared with legacy generation and serialized to one call at a time. A busy model is
an explicit failure. Network calls stay outside SQLite transactions. Cancellation stops later tasks;
late results cannot overwrite a cancelled project. Restart marks in-flight work interrupted and keeps
completed results; it does not replay a started call. Queued work may still run. Targeted reruns and
resumable execution are not implemented.

## Graph semantics

The task hierarchy and scheduling dependencies are independently validated as acyclic. The issue
graph may contain feedback and mutual influence. Issue nodes identify their producing task; critique
references original strategy claims; revisions retain `supersedes` lineage. The schema has no model-
controlled `verified` flag or invented citation. The issue graph is capped at 20 nodes and 40 edges.

The Web renders actual task status, duration, public brief, structured results, errors, issue
contributions and citations. It never renders hidden chain-of-thought or simulated debate.

## Compatibility

`vision_generate`, `vision_save`, `vision_get` and `vision_list` retain their prior single-call
semantics. Legacy saved drafts have no invented task history. The former supply-chain kernel and
HTTP/CLI/MCP operations remain available without a dedicated Web page. See
[the laboratory guide](laboratory.md) for operational examples.