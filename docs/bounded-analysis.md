# Bounded analysis projects

The new analysis workflow creates a durable project, unlike the legacy ephemeral
`vision_generate` operation. Click **创建并运行分析** in the analysis workspace, or call
`analysis_start` through the shared HTTP, CLI or MCP registry. This intentionally saves the
user request, task state and validated structured outputs. It does not save assembled prompts,
SDK message history, raw completions, hidden reasoning or per-event traces.

## Operations

```bash
./tianji schema analysis_start
./tianji call analysis_start --json '{"request":{"vision":"减少社区夏季高温伤害","horizon":"未来两年","constraints":"有限公共预算"}}'
./tianji call job_get --json '{"id":"RUN_ID"}'
./tianji call analysis_get --json '{"id":"RUN_ID"}'
./tianji call analysis_list
./tianji call job_cancel --json '{"id":"RUN_ID"}'
```

The start response is a queued job, not a completed analysis. `analysis_get` exposes the current
versioned project snapshot while it runs; `analysis_list` permits reopening projects after a
refresh. Idempotent creation uses the existing mutation request ID contract. Retrying with the
same ID and arguments returns the original creation response and does not start another project.
Read current state with `job_get` or `analysis_get` afterward.

## Browser request lifecycle

The durable analysis workspace uses `@tanstack/query-core` QueryClient/QueryObserver for
catalog/list/project reads, deduplication, cancellation and active-run polling. Each session has
an isolated cache; disconnect or token change clears it, and credentials are never query keys.
Read errors pause polling until explicit recovery. Terminal runs and unmounted views stop polling.
Focus/reconnect do not refetch, and reads or mutations do not retry automatically.

Creation remains an explicit mutation with a preserved UUID and input intent after an ambiguous
network outcome, including across remounts. Definite rejection unlocks editing. Server cancellation
remains `job_cancel` followed by a fresh canonical read; aborting a browser read alone never cancels
a server job. The legacy single-call controller remains separate. Explicit saves retain their
request ID and draft after ambiguous failures; once the created ID is known, retries only read back
that object. Invalid pending creation records cannot lock the editor.

## What actually runs

A deterministic coordinator uses separate PydanticAI typed agents against the same loopback
llama.cpp model. There is no manager-model call or agent-controlled filesystem, shell or network
retrieval tool. Each strategy's initial context contains the user request, framing result and its
own perspective, never another strategy's first draft.

- Framing defines observable criteria, assumptions, unknowns and one to three relevant perspectives.
  An explicit clarification need stops downstream generation with a partial result.
- Each perspective receives a separate strategy call and produces its own claims and intervention.
- A separate critic references concrete generated claim IDs and proposes testable objections.
- At most one strategy receives a targeted revision. Original claims and objections remain visible.
- Synthesis preserves alternatives and unresolved questions; agreement cannot create verified facts.

The number of perspectives follows the framing output within a resource ceiling. It is not a
fixed five-node diagram. All roles initially use the same model and can share its biases. These
are separately executed tasks, not independent sources of evidence, empirical validation or
calibrated predictions. There is no factual researcher or live source retrieval.

## Transport compatibility

The legacy actor and single-call vision paths share a bounded HTTP exchange in
`local_transport.py`. Their original payloads, deadlines, response limits, error codes,
parsers and slot ownership remain endpoint-specific. Raw response bytes and decompressed output
are both bounded before buffering. Identity, gzip and zlib/raw-deflate responses are supported;
unsupported encodings are rejected. The new PydanticAI adapter retains separate usage and JSON
validation. No legacy inference becomes a durable analysis job or implicit save.

## Limits and lifecycle

Default run ceilings are eight calls, eight tasks, one revision pass, 900 elapsed seconds and
16,000 reserved output tokens. The input budget can lower these limits; the server permits at most
1,200 seconds and 20,000 reserved output tokens. Per-call output ceilings are 1,000 for framing,
1,600 for strategy/revision, 1,400 for critic and 1,200 for synthesis. The full ceiling is reserved
before issuing each call, including calls that fail; missing usage is not treated as free work.
No automatic SDK or validation retry is enabled. The provider request has its own 180-second
whole-call deadline and bounded input/response bytes. Resource exhaustion retains completed
structured outputs as partial rather than fabricating a synthesis.

The model call slot is shared with legacy generation and supply-chain actor proposals. One model
call runs at a time. The single job supervisor also serializes analysis and deterministic jobs;
a long analysis can delay a queued rules job. A busy model is an explicit failure, not an implicit
unbounded wait or retry. Local provider requests do not execute inside SQLite transactions.

Cancel updates the durable job/project and stops subsequent tasks; the active asynchronous client
request is cancelled and late results cannot overwrite the cancelled project. Provider-side
cancellation remains best effort. Restart marks in-flight work interrupted and preserves completed
structured results; it does not resume or replay an already-started call. Unstarted queued work
can still run. Targeted user-requested reruns and resumable execution are not implemented.

## Two graphs, not a fabricated agent conversation

`tianji.analysis.v1` separates tasks, issue nodes/edges and candidate strategies. Task hierarchy
(`parent_id`) and scheduling dependencies are independently validated as acyclic. Issue graphs
may contain feedback and mutual influence; they are not constrained to the legacy four stages.

Issue nodes identify their producing completed task. Strategy claims are server-namespaced,
critique targets are restricted to original strategy claims, excluding the framing question,
objections themselves and later revisions. Candidate strategies reference only their own
producing task's claims. A revision keeps explicit `supersedes` lineage. Issue nodes remain
`model_hypothesis` or `model_objection`; the schema has no model-controlled “verified” flag or
invented source-citation field. The issue graph has at most 20 nodes and 40 edges.

The Web uses React Flow/Dagre to link actual task status and issue contributions. Status, duration,
public brief, structured result and errors are inspectable; private chain-of-thought is not.

## Compatibility

`vision_generate`, `vision_save`, `vision_get` and `vision_list` retain their prior semantics.
Legacy saved drafts remain single-call results with no task history; the UI must not invent agents
for them. Legacy generation still uses its original five-node structural scaffold and explicit
save operation. New projects do not silently turn that old Generate action into auto-save.

The legacy path diagram also uses React Flow/Dagre: shared nodes are rendered once, edges retain
all path memberships, and switching paths changes highlights without moving the layout. Stage
labels stay on nodes; horizontal ranks follow path dependencies rather than fixed stage columns.
The goal remains a non-selectable direction, not a completed task or guaranteed outcome. Pan,
zoom and fit are library-owned; keyboard node selection and the full detail panel remain available.

`analysis_stats` retains the legacy saved-analysis/node/path fields and their
`single_model_single_call` architecture marker. Separate multi-agent project counts are additive;
they do not retroactively relabel old records. The fictional supply-chain kernel and all existing
HTTP/CLI/MCP operations remain available without a dedicated Web page.
