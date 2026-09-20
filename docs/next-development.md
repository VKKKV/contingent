# Next development: public-source scenario analysis

This document is a roadmap, not a second current-state reference. The bounded v2 search/fetch/citation
slice is implemented; details and limits live in [research-integration.md](research-integration.md).
The remaining roadmap is follow-up research, review and branching, portable packages, and interaction
improvements. Keep the existing FastAPI, SQLite, PydanticAI, React Flow/Dagre, Query core and operation
registry; do not introduce another runner or research platform without a concrete need.

## 1. Follow-up research and coverage

Persist a research frontier separate from the bounded run snapshot: question, parent question, goal
facet, query, priority, state, attempts and evidence references. Add source versions/passages with
stable IDs and authenticated pagination; retain old v1/v2 references. Select passages by relevance
across full retained documents, initially with lexical/SQLite facilities rather than a vector service.

Alternate search, source reading and gap assessment. Critique may request primary evidence, newer
information, counterevidence or missing actor/resource/mechanism/time/geography coverage. Stop with an
explicit reason—budget/storage/time exhaustion, cancellation, access/provider failure or no useful
new evidence—and expose remaining gaps. Reopening remains read-only; continuation is an explicit
new action with a new budget.

Acceptance: later-document passages can be selected; a useful additional query/source is handled;
critique causes a real additional search; reposts are not independent support; empty/all-failed/no-new-
evidence runs terminate honestly; cancellation and recovery do not duplicate evidence; old projects
retain their references.

## 2. Optional review and assumption branches

Add append-only review records attached to a claim, evidence link or inference. Store author, time,
decision, reason and exact reviewed version. Accepting an assumption for one scenario is not validating
it in the world; preserve dissent and original model output.

Branch only from a terminal completed/partial snapshot. A branch has a new budget, parent ID and
immutable change set; it never edits or secretly resumes the parent. Compare assumptions, source
versions, strategies and unresolved issues without treating text differences as measured outcomes.
Validate stale versions, cross-project references, idempotency, parent immutability and Web/CLI/MCP
parity.

## 3. Portable packages

Add explicit user-triggered JSON and readable Markdown export/import after source, review and lineage
schemas stabilize. Include selected snapshots, passages, public outputs, relations, versions and
hashes. Exclude tokens, prompts, raw completions, hidden reasoning, private absolute paths and config.
Import must be atomic, offline, non-executable and must not overwrite a project silently. Omitted source
text remains marked unavailable rather than becoming a valid citation.

## 4. Open-source reuse rules

Use source inspections as design references, not claims of installation or benchmark results. Adapt
provenance separation from Docling Core, argument relations from Argdown, source/snippet separation
from STORM, and review interaction ideas from GPT Researcher only after checking the pinned revisions,
licenses and compatibility. Keep Contingent’s renderer, identity scheme and privacy contract. Defer
OpenTelemetry until a concrete diagnostic need and a separate privacy decision exists.

Deliver one slice at a time: schema/privacy contract, transactional operations and migrations,
CLI/MCP parity, Web interaction, then a real online/local-model check. Do not add agents or vector
search as substitutes for missing evidence.