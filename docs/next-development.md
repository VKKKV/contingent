# Next development: traceable scenarios, not more agents

Status: proposed next work, not implemented functionality. Contingent already has a bounded
same-model coordinator, durable SQLite jobs, typed results, linked task/issue graphs and shared
HTTP/CLI/MCP operations. [Current behavior](bounded-analysis.md) and
[existing design boundaries](development-plan.md) remain authoritative.

The next product increment should answer: **what material supports this assumption, who accepted
it for this scenario, and what changes if it is replaced?** More agents alone cannot answer that.
Keep FastAPI, SQLite, PydanticAI, React Flow/Dagre and Query core. Do not introduce a second runner,
vector database, collector service or research platform before a concrete need justifies it.

## 1. First slice: user-supplied material and inspectable citations

Build a small, end-to-end evidence workspace before automated browsing or PDF ingestion.
Accept pasted UTF-8 text/Markdown with a user-entered title, optional source URL and source date.
A URL is metadata only: opening a project must not fetch it. Saving material is an explicit user
action with a privacy notice; it changes the current input-persistence boundary, not the prohibition
on saving model transcripts or hidden reasoning.

Suggested domain objects:

- `SourceVersion`: stable ID, title, optional canonical URL, supplied date, ingestion timestamp,
  immutable original text and full SHA-256 of its exact UTF-8 bytes. Content identity and publication
  identity are different: mirrors do not become independent sources, and the same URL can change.
- `Passage`: stable ID, source-version ID, start/end offsets and quoted text. Define offsets in Unicode
  code points with an end-exclusive range; test non-BMP text across Python/JavaScript. Require the
  quoted text to equal that range in the retained original text. Normalization must never silently
  change what the hash or offsets refer to.
- `ClaimEvidenceLink`: stable claim and passage references, a proposed support/challenge/context
  relation and its author origin. A valid reference is not proof that a passage supports the claim.

Use separate tables and explicit schema/version dispatch, not new required fields injected into
`tianji.analysis.v1`. Keep legacy saved objects readable without pretending they have citations.
The first read/write registry slice can use proposed operations `source_create`, `source_get`,
`source_list` and a versioned analysis-start input. Final operation names follow schema review.
Source creation must be idempotent; a new analysis records the immutable material version IDs
selected by the user. The model can select only provided passage IDs, never invent source URLs.
Pass only explicitly selected, bounded passages into each task rather than the entire collection.

Acceptance:

- One supplied passage can be saved, explicitly selected for a new run, cited by a structured claim,
  and opened from that claim in the Web; HTTP/CLI/MCP expose the same validated operations.
- Reject missing, cross-project or unknown references, invalid spans, mismatched quotes, duplicate
  identities and oversized text. Agree explicit per-source, per-project and per-call byte/token
  ceilings before implementation; resource exhaustion is visible and cannot drop sources silently.
- Test malicious HTML, script-like Markdown, instruction-like passages and bidi/non-BMP text.
  Render source text safely; treat it as untrusted material, not tool/system instructions. No source
  content reaches shell commands, logs, unsolicited network calls or unbounded prompt context.
- Existing v1 databases and views still load, source writes roll back atomically on failure, and
  cancellation preserves the selected input versions without manufacturing evidence.
- Label user-provided material separately from model hypotheses. Do not add a model-controlled
  `verified` flag or present repeated quotations as independent corroboration.

Out of scope: autonomous retrieval, OCR, vector search, factual verification, deletion/retention
automation and arbitrary file paths supplied by a remote client. Source deletion/retention needs a
separate explicit policy before it can invalidate saved analyses.

## 2. Human review and explicit assumption branches

After the first source slice is usable, add append-only review records attached to a specific
claim, evidence link or inference. Store author origin, timestamp, decision, reason and the exact
object/version reviewed. Distinguish accepting an assumption **for this scenario** from validating
it in the world. Preserve dissent, contradictory materials and the original model contribution.
A reviewer cannot rewrite the underlying model result through a review action.

Adopt a small relation vocabulary before adding more node types: support, challenge and critique of
an inference are different. Label these as asserted relations, not automatically proved logical
contradictions. Render all relations with the existing graph stack; retain list/detail navigation
for keyboard users and small screens.

Then support explicit branching from a terminal project snapshot:

- Select an assumption, provide a replacement and rationale, and create a new run with a new budget,
  parent-run ID and immutable change set. First version permits completed/partial terminal parents;
  it does not edit an active run or secretly resume an interrupted call.
- Compare changed assumptions, selected source versions, candidate strategies and unresolved issues.
  Do not interpret text differences as measured outcome changes or confidence improvements.
- Persist branch creation and idempotency response together. Parent snapshots stay immutable,
  source versions remain pinned, and cancellation/restart semantics are tested on the child run.
- Framing clarification may use the same explicit follow-up/branch mechanism; waiting for user
  feedback must not hold the model slot, transaction or an open request indefinitely.

Acceptance includes conflicting reviews remaining visible, stale-version review rejection,
idempotent concurrent branch creation, cross-project reference rejection, parent immutability,
readback after restart and parity across Web/CLI/MCP. Bounded review exhaustion remains
`partial`/unresolved, never forced acceptance. No LangGraph migration is needed for this slice.

## 3. Portable analysis packages

Once sources, reviews and lineage have stable schemas, implement explicit export/import of a
versioned JSON package and readable Markdown. Export is user-triggered, not an automatic report
pipeline. A later optional Argdown projection is a view, not the authoritative storage format.

The package contains selected run snapshots, source versions/passages, public structured task
outputs, evidence/review relations and the lineage needed to interpret them. Include a manifest
with versions and content hashes; exclude tokens, prompt histories, raw completions, hidden
reasoning, absolute private paths and internal configuration. Source text can itself be private:
show export scope and require explicit inclusion; an intentionally omitted source must remain
marked unavailable, not represented as an intact citation.

Acceptance: offline round-trip preserves public semantics and references; unknown versions,
invalid hashes, oversized bundles and bad references fail atomically. Import must never execute a
model, fetch URLs, extract arbitrary filesystem paths or overwrite an existing project silently.
Handle ID collisions through a defined transactional remapping of the entire reference graph,
or reject them explicitly. An imported running snapshot is historical/interrupted, not runnable
work. No tar/zip extraction is needed for the first JSON-only format.

## 4. Open-source decisions and evidence

Source review performed against the fixed revisions below. These are source-level observations,
not claims that the upstream projects were installed, benchmarked or integrated here. Licenses
were read at those revisions; copying code requires retaining its applicable notices. Commit pins
are research anchors, not recommended package versions. No new dependency is approved by this plan.

### Docling Core: adapt provenance, defer full ingestion

Repository: https://github.com/docling-project/docling-core
Revision: `4582a183c55b95ccfb1aea9e3febfe19cc0bd595`
License: [MIT](https://github.com/docling-project/docling-core/blob/4582a183c55b95ccfb1aea9e3febfe19cc0bd595/LICENSE).

[ProvenanceItem](https://github.com/docling-project/docling-core/blob/4582a183c55b95ccfb1aea9e3febfe19cc0bd595/docling_core/types/doc/common/reference.py#L183-L193)
models a page, bounding box and character span; origin metadata is separate. Borrow this separation
for SourceVersion/Passage, initially without layout coordinates. Core itself has additional
processing dependencies; a future optional PDF/OCR adapter needs its own resource, isolation and
model-asset licensing review. Do not equate a bounded numeric origin hash with a full cryptographic
content digest. Engineering cost: small domain adapter now; larger document ingestion later.

### Argdown: adapt argument semantics, keep our renderer

Repository: https://github.com/argdown/argdown
Revision: `27f412a68f7f4c23ea3afc13793c151ad22d534e`
License: [argdown-core MIT](https://github.com/argdown/argdown/blob/27f412a68f7f4c23ea3afc13793c151ad22d534e/packages/argdown-core/License).

[RelationType](https://github.com/argdown/argdown/blob/27f412a68f7f4c23ea3afc13793c151ad22d534e/packages/argdown-core/src/model/model.ts#L44-L67)
distinguishes support/attack from undercutting an inference and statement-level relations. Its
[JSON exporter](https://github.com/argdown/argdown/blob/27f412a68f7f4c23ea3afc13793c151ad22d534e/packages/argdown-core/src/plugins/JSONExportPlugin.ts)
separates statements, arguments and relations. Adapt the concepts, not the parser/Graphviz stack:
Contingent already has a renderer, layout and stable identity scheme. Do not treat equal titles as
identical claims. Cost: schema/UI changes and compatibility tests; no new rendering dependency.

### STORM: adapt source/snippet separation, defer research engine

Repository: https://github.com/stanford-oval/storm
Revision: `fb951af7744dab086e34962e9bc6fe878e145f83`
License: [MIT](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/LICENSE).

[Information](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/knowledge_storm/interface.py#L41-L67)
separates URLs, titles, snippets and metadata. Borrow the source registry/citation lookup pattern,
not URL-only identity. The [engine](https://github.com/stanford-oval/storm/blob/fb951af7744dab086e34962e9bc6fe878e145f83/knowledge_storm/storm_wiki/engine.py)
and its research dependencies would duplicate orchestration; its model-history persistence does
not match our privacy contract. Cost: low for the data pattern, high for the whole platform.

### GPT Researcher: adapt review interaction, do not copy forced acceptance

Repository: https://github.com/assafelovic/gpt-researcher
Revision: `6f998577d547b1e54ec662dac63583aa11e3b84b`
License metadata is inconsistent: root [LICENSE](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/LICENSE)
is Apache-2.0, while [pyproject.toml](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/pyproject.toml)
still declares MIT. Clarify before code reuse; we only borrow the interaction idea here.

The [human reviewer](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/multi_agents/agents/human.py)
is a reference for plan feedback, not proof of durable review recovery. The
[editor](https://github.com/assafelovic/gpt-researcher/blob/6f998577d547b1e54ec662dac63583aa11e3b84b/multi_agents/agents/editor.py#L151-L164)
returns acceptance when revisions exceed its ceiling; explicitly do not adopt that behavior.
Cost: modest interaction work, substantial durable schema/lifecycle work handled in our own registry.

### OpenTelemetry Python: defer until there is an approved diagnostic need

Repository: https://github.com/open-telemetry/opentelemetry-python
Revision: `5321c606f216c8262da949e85d46a18621484ea9`
License: [Apache-2.0](https://github.com/open-telemetry/opentelemetry-python/blob/5321c606f216c8262da949e85d46a18621484ea9/LICENSE).

Its [trace export interfaces](https://github.com/open-telemetry/opentelemetry-python/blob/5321c606f216c8262da949e85d46a18621484ea9/opentelemetry-sdk/src/opentelemetry/sdk/trace/export/__init__.py)
are preferable to a custom trace protocol if richer diagnostics become necessary. For now use
existing task state/timing. Default telemetry stays disabled, with no mandatory Collector or trace
archive. Any later opt-in needs a separate privacy decision, attribute whitelist and tests proving
no prompts, passages, completions or credentials leak to logs/exporters. SDK/exporter dependencies
must be version-compatible; this research revision is not a deployment recommendation.

## 5. Delivery order and stopping rules

Ship the first source/citation slice before implementing the entire roadmap. Order within each
slice: schema and privacy contract, transactional operations and migration tests, CLI/MCP parity,
Web interaction, then one real local-model check with clearly user-supplied material. Keep ordinary
tests and immediate checks; do not create mandatory evaluation dashboards or evidence archives.

Finish the remaining current UI state checks as maintenance, without blocking useful source work
on pixel-identical replication of a different product. The 150px tube cap and Contingent branding
are intentional product choices, not regressions to upstream's layout.

Do not add automatic retrieval until the source model and citation validation work without it.
If later introduced, retrieval needs explicit consent, outbound/SSRF controls, byte/time limits,
source-version capture, prompt-injection boundaries and separate identification of retrieved versus
user-supplied material. Do not add vector search for a collection that bounded explicit selection
can handle. Do not add more agents as a substitute for missing evidence or human review.

Four different claims must remain distinct: a reference is structurally valid; a passage supports
an assertion; a person accepts an assumption for a scenario; a causal effect is empirically
validated. None automatically implies the next.
