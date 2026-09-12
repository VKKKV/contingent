# Phase H — Evaluation Harness

## Purpose

Make TianJi's deterministic analysis quality measurable before expanding scoring,
simulation, or feed-source behavior. Phase H adds a local-first evaluation harness
that runs checked-in fixtures, compares semantic output against checked-in
expectations/golden snapshots, and reports drift in a CI-friendly format.

The harness is not a live LLM test and not a network smoke test. It must run with
only repository files and the Rust binary/library.

## Architecture

### Corpus manifest

Canonical path:

```text
tests/fixtures/eval/corpus.yaml
```

The manifest describes evaluation cases, not raw implementation internals. Each
case should include:

- `id`: stable lowercase slug used in reports and snapshot filenames.
- `description`: short human-readable scenario description.
- `fixture`: path to a checked-in RSS/Atom fixture.
- `expected.schema_version`: expected artifact schema.
- `expected.mode`: expected run mode.
- `expected.raw_item_count` and `expected.normalized_event_count`.
- `expected.scored_event_count` and `expected.intervention_count`.
- `expected.dominant_field` and `expected.risk_level`.
- `expected.top_event_id` where a stable top event is important.
- `tolerance.score_abs`: allowed absolute drift for numeric score checks.
- `golden`: checked-in golden snapshot path.

Keep the first slice intentionally small: start with existing local fixtures such
as `tests/fixtures/sample_feed.xml` and `tests/fixtures/grouped.xml`.

### Golden snapshots

Canonical directory:

```text
tests/fixtures/eval/golden/
```

Golden snapshots should preserve stable semantic artifact fields. They may store
the full artifact if generated timestamps are deterministic, but comparison code
should still focus on semantic fields:

- schema version
- mode
- counts
- scenario dominant field and risk level
- top scored event identity/dominant field/risk scores
- intervention count and stable priority ordering

Avoid comparing incidental formatting or local paths beyond fixture source names.

### Drift report

The user-facing command is:

```bash
tianji eval --manifest tests/fixtures/eval/corpus.yaml
```

Expected behavior:

- runs every manifest case through the deterministic fixture pipeline;
- loads each golden snapshot if present;
- reports one JSON object to stdout;
- exits `0` when every case is accepted;
- exits non-zero when any required expectation fails or disallowed drift occurs.

Snapshot refresh is explicit:

```bash
tianji eval --manifest tests/fixtures/eval/corpus.yaml --update-golden
```

Normal `eval` is read-only. `--update-golden` may overwrite only golden files
listed in the manifest and should report the updated paths.

Report shape is stable and compact:

```json
{
  "schema_version": "tianji.eval-report.v1",
  "manifest": "tests/fixtures/eval/corpus.yaml",
  "case_count": 2,
  "passed": 2,
  "failed": 0,
  "max_score_delta": 0.0,
  "updated_golden_paths": [],
  "cases": [
    {
      "id": "sample_feed_technology_high",
      "description": "Representative sample feed remains technology/high.",
      "status": "pass",
      "fixture": "tests/fixtures/sample_feed.xml",
      "check_count": 13,
      "failed_check_count": 0,
      "checks": [
        {"name": "dominant_field", "status": "pass", "expected": "technology", "actual": "technology", "delta": null, "tolerance": null}
      ],
      "max_score_delta": 0.0
    }
  ]
}
```

## Acceptance for H1 first slice

H1 may ship as a minimal end-to-end slice. Required:

1. Add eval manifest and at least one golden snapshot under `tests/fixtures/eval/`.
2. Add typed Rust support for reading the manifest.
3. Add `tianji eval --manifest <PATH>`.
4. Compare deterministic fixture run output against manifest expectations.
5. Compare at least one golden semantic field beyond top-level counts.
6. Return non-zero on drift/failure.
7. Add tests for pass and intentional failure behavior.
8. Keep all inputs local-first and credential-free.

Out of scope for H1:

- live network feeds;
- live LLM/provider calls;
- daemon/API integration;
- probabilistic simulation quality metrics;
- broad fixture corpus expansion beyond the first representative cases.

## Acceptance for H2-H4 completion

1. Eval corpus contains at least two checked-in local fixture cases.
2. Every case has a checked-in golden snapshot.
3. `tianji eval --manifest tests/fixtures/eval/corpus.yaml` exits `0` for the checked-in corpus.
4. `tianji eval --manifest tests/fixtures/eval/corpus.yaml --update-golden` refreshes only listed golden snapshots and is tested.
5. Report includes case descriptions, check counts, failed check counts, global max score delta, and per-numeric-check delta/tolerance.
6. A local verification script or documented gate exists and requires no network, daemon, LLM, or credentials.
7. README and `plan.md` document Phase H as complete after verification.

## Verification

Run:

```bash
cargo fmt
cargo test --quiet eval
cargo test --quiet
cargo clippy -- -D warnings
git diff --check
cargo run --quiet -- eval --manifest tests/fixtures/eval/corpus.yaml
```

The eval command must exit `0` and print valid JSON for the checked-in corpus.

## Phase H follow-ups

- H2: expand golden snapshot coverage and snapshot refresh workflow.
- H3: add richer score drift reporter with numeric deltas across fixture families.
- H4: document fixture authoring and wire a lightweight eval command into release/CI checks.
