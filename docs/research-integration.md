# Online research implementation decisions

Status: the first bounded v2 search/fetch/citation slice is implemented and has passed live integration
checks. It is not unrestricted autonomous research or fact checking. Results remain partial when
sources are blocked, citations fail validation or budgets are exhausted.

## Current behavior

The Web form defaults to online research; only the objective is required. It discloses external
queries and local source persistence. Explicit offline v2 performs no research and is labeled
hypothesis-only/partial. Existing v1 projects remain offline. Reopening a project reads its snapshot;
it does not fetch or invoke a model again.

```bash
./tianji schema analysis_start_v2
./tianji call analysis_start_v2 --json '{"request":{"vision":"Compare Python learning routes for an experienced programming team"}}'
./tianji call analysis_list_v2
./tianji call analysis_get --json '{"id":"RUN_ID"}'
```

Defaults are at most two queries, three attempted pages and 90 research seconds; server ceilings are
three queries, five pages and 180 seconds. Fetch budgets are separate from search-provider usage.
Later roles receive at most 4,000 passage characters. Each source retains at most 6,000 characters
and three exact 800-character windows. Queries rotate across result queues with global URL deduplication.
Failed attempts consume budget. There is no provider switch, hidden retry or critique-triggered
follow-up search.

Citations bind a completed task's actual text field to a passage that task saw. Existence and
visibility are validated; semantic entailment is not. One real local-model run has exercised research,
strategies, critique, revision, synthesis and persisted citations; this is an exercised slice, not a
success rate or arbitrary-topic guarantee.

## Provider and extractor choices

- DDGS `9.16.0` (MIT), explicit Brave backend, pinned at
  [deedy5/ddgs](https://github.com/deedy5/ddgs/tree/70a5635510fb8d5b15d5ba6ceced6a67e212149b).
  It is isolated in a killable, resource-bounded subprocess. Search response bytes are not precisely
  accounted for; do not combine unknown provider usage with page-download byte accounting.
- Trafilatura `2.2.0` (Apache-2.0), pinned at
  [adbar/trafilatura](https://github.com/adbar/trafilatura/tree/c1bc9531a2a978326112ca9987e1382745116136).
  It extracts already-fetched HTML offline; it is not used as a downloader. No PDF/OCR support is
  implied.
- HTTPX handles async IO, TLS, streaming and cancellation. The application owns URL policy, DNS
  validation and connection pinning.

No search credentials or remote LLM provider are required. SearXNG is a future adapter, not a
mandatory service. No CAPTCHA, access-control or paywall bypass exists.

## Public fetch safety

Search results are untrusted URLs. Fetches use controlled HTTP without provider credentials, arbitrary
ports, implicit proxies or automatic redirects. Public addresses are validated and pinned at connect
time; every redirect is revalidated. Loopback, private, link-local, reserved and fake-IP ranges are
blocked. Robots.txt is read first; denied paths and unsupported crawl-delay/request-rate requirements
are skipped. Login forms, common challenge markers and script-only fallback pages are rejected
conservatively. Only HTML and plain text are extracted.

The system resolver is the default. In fake-IP environments, explicitly set
`TIANJI_RESEARCH_DNS=cloudflare` to use the fixed Cloudflare DNS-over-HTTPS resolver with validated
TLS Host/SNI and public-address checks. This reveals queried hostnames to that resolver and does not
change the user's system proxy. Without this opt-in, non-public answers fail closed.

## Persistence and boundaries

Source text, exact UTF-8 hashes, Unicode code-point passage spans, research status and citation links
remain embedded in the versioned analysis snapshot and are committed atomically with the job checkpoint.
The service additionally mirrors validated sources, passages and the per-run query frontier into
authenticated cursor-paginated SQLite read models. A terminal v2 run can explicitly start a separate
continuation job with new bounded queries. Continuations preserve the parent ID, immutable input and
stop state; validated source versions use stable text-independent document identities and exact
passages use stable evidence IDs. These are additive read models, not an unlimited source archive or
automatic critique loop; the original run snapshot remains the compatibility source of truth. Query
persistence and outbound disclosure remain visible; private material must not be copied into queries.
Retrieved pages are data, not instructions, and cannot alter tool permissions or request private
information.

Not included in this slice: automatic post-critic follow-up research, cross-run frontier merging,
resumable global queues, attached-file parsing, OCR,
authenticated browsing, recurring monitoring, arbitrary source refresh, human review, assumption
branches or real-world action. Optional user material is a later supplement, not a prerequisite for
autonomous research.