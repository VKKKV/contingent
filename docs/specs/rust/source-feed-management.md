# Phase I — Source/feed Management

## Purpose

Phase I turns TianJi's single-input feed path into an explicit source registry
without making the product depend on live network access. The operator should be
able to define source metadata in YAML, enable/disable sources, group them by tier,
and inspect registry health/status locally.

The registry is an operator control plane for feed inputs. It is not a scoring
change and not an LLM/simulation feature.

## Principles

1. Local-first default
   - Checked-in examples must use local fixture paths or dummy URLs.
   - Tests must not require network, daemon, LLM provider, or credentials.

2. Explicit source identity
   - Each source has a stable `id` used in reports/status and future persistence.
   - Display names and URLs/paths are metadata, not identity.

3. Safe config
   - No tokens, API keys, passwords, cookies, or private feed URLs in examples/tests.
   - If credentialed feeds are ever added, credentials must be referenced through env vars, never printed.

4. Bounded completion
   - I1 starts with manifest loading, validation, listing, and fixture-run fan-in.
   - Phase I completion adds JSON health summaries and explicit live-fetch opt-in.
   - Default listing must never perform network I/O.

## Registry schema

Canonical sample path:

```text
examples/sources.example.yaml
```

Suggested YAML shape:

```yaml
sources:
  - id: sample_technology
    name: Sample technology fixture
    enabled: true
    tier: primary
    kind: fixture
    path: tests/fixtures/sample_feed.xml
    tags: [technology, demo]

  - id: economy_fixture
    name: Economy fixture
    enabled: true
    tier: secondary
    kind: fixture
    path: tests/fixtures/economy_feed.xml
    tags: [economy, demo]

  - id: disabled_dummy_remote
    name: Disabled dummy remote feed
    enabled: false
    tier: watchlist
    kind: rss
    url: https://example.invalid/feed.xml
    tags: [dummy]
```

Required fields:

- `id`: non-empty stable slug; unique within the file.
- `name`: non-empty operator label.
- `enabled`: boolean.
- `tier`: non-empty operator tier such as `primary`, `secondary`, `watchlist`.
- `kind`: one of `fixture`, `rss`, `atom`.
- `path`: required for `fixture`.
- `url`: required for `rss`/`atom`.
- `tags`: optional list of labels.

Validation rules:

- Duplicate IDs fail validation.
- Missing `path` for fixture fails validation.
- Missing `url` for rss/atom fails validation.
- Unknown kind fails validation.
- Disabled sources are loaded and reported but not selected for fan-in runs.

## CLI

List and validate registry without network I/O:

```bash
tianji sources --config examples/sources.example.yaml
```

Run enabled fixture sources only:

```bash
tianji sources --config examples/sources.example.yaml --run-fixtures
```

Explicitly fetch enabled `rss`/`atom` sources:

```bash
tianji sources --config ~/.config/tianji/sources.yaml --fetch-live
```

Safety rules:

- default listing is validation/report only;
- `--run-fixtures` never fetches network sources;
- `--fetch-live` is the only CLI mode that may perform network I/O;
- disabled sources are always reported but never run/fetched;
- examples and tests must remain credential-free.

Expected JSON report includes:

```json
{
  "schema_version": "tianji.sources-report.v1",
  "config": "examples/sources.example.yaml",
  "total": 3,
  "enabled": 2,
  "disabled": 1,
  "ready": 2,
  "skipped": 1,
  "errors": 0,
  "tiers": {"primary": 1, "secondary": 1, "watchlist": 1},
  "sources": [],
  "runs": []
}
```

Run entries should include:

- `source_id`
- `kind`
- `status`: `ok`, `skipped`, or `error`
- item/event/candidate counts on success
- dominant field and risk level on success
- safe error string on failure

## Acceptance for I1

1. Add typed Rust registry support, preferably `src/source_registry.rs`.
2. Add `examples/sources.example.yaml` with only fixture/dummy-example sources.
3. Add `tianji sources --config <PATH>` JSON summary.
4. Add `--run-fixtures` deterministic local fan-in for enabled fixture sources.
5. Add tests for valid load, duplicate ID rejection, missing fixture path rejection, disabled source exclusion, and CLI parsing.
6. Update README/plan with Phase I start state.

## Acceptance for I2-I4 completion

1. Source JSON reports include health/aggregate status fields (`ready`, `skipped`, `errors` or equivalent).
2. `tianji sources --config <PATH>` performs no network I/O.
3. `tianji sources --config <PATH> --run-fixtures` runs enabled fixture sources only.
4. `tianji sources --config <PATH> --fetch-live` explicitly fetches enabled rss/atom sources.
5. Disabled sources are reported but never run/fetched in any mode.
6. Live-fetch tests use deterministic local/mock HTTP or injected fetch text; no external internet dependency.
7. README documents registry listing, fixture fan-in, live-fetch opt-in, and local smoke commands.
8. `plan.md` marks Phase I complete after verification.

## Verification

```bash
cargo fmt
cargo test --quiet source
cargo test --quiet
cargo clippy -- -D warnings
git diff --check
cargo run --quiet -- sources --config examples/sources.example.yaml
cargo run --quiet -- sources --config examples/sources.example.yaml --run-fixtures
```
