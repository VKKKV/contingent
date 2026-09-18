# TianJi (天机)

TianJi is a **bidirectional world simulation laboratory** (双向世界推演实验室). Its creative vision is a computational Laplace's demon, not perfect prediction: explore conditional futures, plan backwards from a goal, fork a worldline, and test every candidate against the same forward model.

## Active implementation: TypeScript + Python

The new local-first workbench lives in `web/` (React/TypeScript/Vite) and `backend/` (Python/FastAPI/Pydantic/SQLite). Web and external agents share a validated operation registry and an official MCP stdio adapter. The initial executable slice is a **fictional, deterministic civilian supply chain**, not a general world simulator or a calibrated forecasting system.

- Edit bounded scenario parameters and per-turn actions; run forward trajectories.
- Declare an explicit exogenous disturbance schedule (demand spikes and supplier losses) that is frozen with the scenario, conserved in a `lost` account and replayed exactly. There is no random number generator and no seed.
- Search from terminal goals and constraints; distinguish feasible plans, finite-model no solution, and incomplete search. Replay all returned plans with the forward model.
- Fork recorded ticks, compare frozen assumptions, inspect events/state hashes, export and semantically validate standalone JSON bundles.
- Operate the same scenarios, jobs, branches and desired workspace state through HTTP and MCP. The browser polls branch/tick/panel changes; a successful API call is not a browser rendering acknowledgement.
- Inspect saved retailer/supplier observations and independent kernel-checked action previews through Web, HTTP and MCP. Adjudication records are durable director audit data, not participant authentication, votes or executed branch changes.
- Single local director, token authentication, revision guards, durable bounded jobs and cancellation. No built-in LLM/chat, live feeds, multiplayer authorization or real-world actuation in this slice.

### Run the laboratory

Requires Node 22.12+ (or a supported newer Node release), `uv`, and Python 3.12+. The service currently targets Linux/macOS (POSIX file locking). From the repository root:

```bash
npm --prefix web ci
npm --prefix web run build
uv sync --project backend --locked --python 3.12
uv run --project backend --locked python -m tianji_lab serve \
  --host 127.0.0.1 --port 8787 --data-dir .local-data
```

Open http://127.0.0.1:8787. The service prints the path of a mode-0600 `token` file in the chosen data directory; paste its contents into the connection form. Tokens are never placed in URLs. Reuse the data directory to keep experiments. Only one service may own it. No legacy database migration occurs.

For development, run `npm --prefix web run dev` alongside the API. For MCP setup, model rules, acceptance commands and limitations, see [Laboratory guide](docs/laboratory.md). Product requirements, milestone contracts and verification records live under [docs/milestones/](docs/milestones/); the engineering contract is [docs/specs/lab/](docs/specs/lab/).

### Validation

```bash
uv run --project backend --locked pytest backend/tests
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run format:check
npm --prefix web run build
```

Browser acceptance is a separate real Chromium test, not mocked HTTP; see the guide. Do not infer real-world predictive validity from tests or simulated goal attainment.

## Preserved legacy Rust implementation

The remainder of this README documents the earlier geopolitical intelligence pipeline. `src/`, `Cargo.toml`, `Cargo.lock`, profiles and existing databases are retained for reference; the new laboratory does **not** run a parallel Rust backend or claim old CLI/API compatibility. Legacy milestone claims below are historical, not the status of the new stack. A later runtime check reproduced a nested Tokio runtime failure in the old daemon; its presence in the historical feature list is not a current readiness guarantee.

### Historical state (2026-06-09)

Pure Rust project. 445 cargo tests across 3 suites pass / 0 fail. Single binary, no Python dependencies. Deterministic core pipeline remains local-first; optional LLM-backed Hongmeng/Nuwa simulation, JSONL simulation trace export, replay bundle packaging, trace-backed TUI replay loading, structured agent audit viewer, daemon API, alert dispatch, eval harness drift checks, source/feed management with SQLite source health history, SQLite retention, daemon health/readiness probes, and local maintenance check/backup/export/compact are implemented. Latest local release-readiness build measured 16,245,408 bytes / 15.49 MiB under the 25 MB target.

| Milestone | Status |
|-----------|--------|
| M1A Feed + Normalization (RSS/Atom, SHA-256 hash, keywords/actors/regions) | ✅ |
| M1B Scoring + Grouping + Backtrack (Im/Fa, divergence, intervention candidates) | ✅ |
| M2 Storage + History CLI (SQLite persistence, history/history-show/history-compare) | ✅ |
| M3A Daemon + Local API (UNIX socket, axum HTTP API, job queue) | ✅ |
| M3B Web UI (embedded static files, API proxy, /queue-run) | ✅ |
| M3C Daemon schedule (bounded repeated run queue) | ✅ |
| M4 TUI (ratatui history browser MVP, Kanagawa Dark, Vim keybindings) | ✅ |
| Crucix Delta Engine (cross-run change tracking, AlertTier FLASH/PRIORITY/ROUTINE, alert decay) | ✅ |
| Hongmeng/Nuwa simulation (provider config, actor profiles, worldline sandbox, predict/backtrack/baseline/watch) | ✅ |
| Evaluation Harness (fixture corpus, golden snapshots, semantic drift reporter) | ✅ |
| Source/feed management (local registry, fixture fan-in, live fetch opt-in, SQLite source health) | ✅ |
| Operational reliability (retention, health/readiness probes, maintenance check/backup/export/compact) | ✅ |
| Phase K replay/audit (JSONL trace, replay bundle, trace-backed TUI, structured agent audit viewer) | ✅ |

---

## Operator Quickstart (local-first)

The first path is credential-free: local fixture in, deterministic JSON out. No LLM, API key, daemon, webhook, or network is required. `run` prints the JSON artifact to stdout and uses the local default SQLite path (`runs/tianji.sqlite3`) unless you pass an explicit `--sqlite-path`.

```bash
# From the repository root
cargo build

# 1. Deterministic fixture run — zero config, no network
cargo run -- run --fixture tests/fixtures/sample_feed.xml

# 2. Use an explicit local DB for repeatable history, delta, daemon/API, and TUI
mkdir -p runs
cargo run -- run --fixture tests/fixtures/sample_feed.xml --sqlite-path runs/tianji.sqlite3

# 3. Browse persisted history
cargo run -- history --sqlite-path runs/tianji.sqlite3

# 4. Validate optional config + SQLite readiness without printing secrets
cargo run -- doctor --config examples/config.example.yaml --sqlite-path runs/tianji.sqlite3
cargo run -- doctor --config examples/config.example.yaml --json

# 5. Inspect local source registry and run enabled fixture sources
cargo run -- sources --config examples/sources.example.yaml
cargo run -- sources --config examples/sources.example.yaml --run-fixtures
cargo run -- sources --config examples/sources.example.yaml --run-fixtures --sqlite-path runs/source-health.sqlite3
# Optional: live registry entries require explicit --fetch-live and an operator-owned config.

# 6. Terminal UI browser (read-only)
cargo run -- tui --sqlite-path runs/tianji.sqlite3

# 7. Local maintenance sequence before destructive retention
cargo run -- maintenance check --sqlite-path runs/tianji.sqlite3
cargo run -- maintenance backup --sqlite-path runs/tianji.sqlite3 --output runs/tianji.backup.sqlite3
cargo run -- maintenance export --sqlite-path runs/tianji.sqlite3 --output runs/tianji-history.jsonl --format jsonl
cargo run -- maintenance retain --sqlite-path runs/tianji.sqlite3 --keep-last-runs 20
cargo run -- maintenance compact --sqlite-path runs/tianji.sqlite3 --vacuum
cargo run -- maintenance check --sqlite-path runs/tianji.sqlite3

# 8. Optional daemon + local HTTP API on loopback
cargo run -- daemon start --sqlite-path runs/tianji.sqlite3 --socket-path runs/tianji.sock --host 127.0.0.1 --port 8765
```

If you installed the binary, replace `cargo run -- ...` with `tianji ...`. Examples below use `cargo run --` when they are meant to be copy-pasteable from a source checkout.

---

## One-Shot Analysis

No config files. No API keys. No LLM.

```bash
cargo run -- run --fixture tests/fixtures/sample_feed.xml
```

This runs the full pipeline on a local RSS/Atom XML file and prints a JSON artifact to stdout. The CLI default also persists to `runs/tianji.sqlite3`; pass `--sqlite-path <PATH>` when you want a specific local history database for later commands.

```
feed.xml → parse → normalize → score → group → backtrack → JSON
```

The output is a `RunArtifact` with:
- `scored_events`: every event ranked by impact, field attraction, divergence
- `scenario_summary`: dominant field, top actors, top regions, risk level, headline
- `intervention_candidates`: ranked interventions with type, target, reason, expected effect

Use the selected SQLite path for later history queries, comparisons, delta tracking, daemon/API serving, and TUI browsing.

### Input format

TianJi ingests **RSS 2.0 and Atom 1.0 XML files**. The sample fixture is a three-event geopolitical feed:

```xml
<rss version="2.0"><channel>
  <item>
    <title>Iran nuclear talks resume in Vienna after cyber dispute</title>
    <link>https://example.com/iran-talks</link>
    <description>European mediators opened a new negotiation channel...</description>
  </item>
  <!-- ... -->
</channel></rss>
```

When run on a fixture, TianJi extracts:
- **Keywords**: tokenized from title + description
- **Actors**: nations and organizations (usa, china, nato, eu, iran, russia...)
- **Regions**: geographic areas (east-asia, middle-east, europe, united-states...)
- **Field scores**: conflict, diplomacy, economy, technology — keyword-weighted
- **Event IDs**: deterministic SHA-256 hash of source + title + link

### Output

Everything is JSON. One command, one output:

```bash
$ cargo run -- run --fixture tests/fixtures/sample_feed.xml
{
  "schema_version": "tianji.run-artifact.v1",
  "mode": "fixture",
  "generated_at": "1970-01-01T00:00:00+00:00",
  "scenario_summary": {
    "dominant_field": "technology",
    "risk_level": "high",
    "headline": "...",
    "top_actors": ["usa", "china", "iran"],
    "top_regions": ["east-asia", "united-states", "middle-east"]
  },
  "scored_events": [ ... ],
  "intervention_candidates": [ ... ]
}
```

**No LLM is required for the Cangjie/Fuxi pipeline.** Feed → scoring → backtrack remains 100% deterministic and can run with no API key. Optional Hongmeng/Nuwa simulation can call configured LLM providers when provider config is present. Start from the checked-in template:

```bash
mkdir -p ~/.tianji
cp examples/config.example.yaml ~/.tianji/config.yaml
```

`examples/config.example.yaml` is credential-free and shows both local Ollama-style and OpenAI-compatible provider shapes:

```yaml
providers:
  ollama_local:
    type: ollama
    model: qwen3:14b
    base_url: http://127.0.0.1:11434
    max_concurrency: 1

  openai_compatible:
    type: openai
    model: gpt-4o
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY       # reads key from environment, never inline
    max_concurrency: 2
    fallback: ollama_local

agent_model_map:
  forward_default: ollama_local
  backward_coarse: openai_compatible
  backward_fine: ollama_local
```

For deterministic fixture runs: **no LLM, no API key, no network calls**. LLM/network access is only used by optional provider-backed simulation or external alert dispatch paths.

The default config path is `~/.tianji/config.yaml`; pass `--config <PATH>` to override it. Validate local readiness with:

```bash
cargo run -- doctor --config examples/config.example.yaml --sqlite-path runs/tianji.sqlite3
cargo run -- doctor --config examples/config.example.yaml --json
```

`doctor` reports config file presence/parse status, provider counts and shapes, `api_key_env` presence, inline key presence (without printing the value), provider fallback references, agent model-map references, and optional SQLite path readiness. Missing config is a warning; malformed YAML fails. Raw API keys and credential values are never printed.

### Optional simulation, replay, and audit export

Hongmeng/Nuwa simulation can run with configured providers when requested. Without
provider config, the local deterministic stub path still works and does not call
external model endpoints.

```bash
# Provider-backed; optional; may use network/model calls depending on config.
cargo run -- predict --field east-asia.conflict --horizon 30 --config ~/.tianji/config.yaml

# Export replay-friendly JSONL trace without changing stdout outcome JSON.
cargo run -- predict --field east-asia.conflict --horizon 30 --trace-jsonl runs/predict-trace.jsonl

# Package a portable local replay bundle: manifest.json, trace.jsonl, outcome.json.
cargo run -- predict --field east-asia.conflict --horizon 30 --replay-bundle-dir runs/replay-bundle
```

JSONL traces use schema `tianji.sim-trace.v1` records (`metadata`, `frame`,
`completed`). Replay bundles use schema `tianji.replay-bundle.v1` and contain
`manifest.json`, `trace.jsonl`, and `outcome.json`. They contain only simulation
metadata, frame traces, structured audit fields, and the final outcome; raw
config, API keys, and provider secrets are not written. `predict` stdout remains
the final `SimulationOutcome` JSON whether or not trace or bundle export flags
are set.

Replay traces and bundles can be inspected locally in the TUI without running a
provider or reading config/secrets. `--render-once` is useful for smoke tests and
automation because it prints a deterministic plain-text replay frame and exits:

```bash
cargo run -- tui --trace-jsonl runs/predict-trace.jsonl
cargo run -- tui --replay-bundle-dir runs/replay-bundle
cargo run -- tui --trace-jsonl runs/predict-trace.jsonl --render-once
```

Credential-free replay smoke gate:

```bash
bash scripts/check-replay-smoke.sh
```

That gate writes only under `/tmp`, runs `predict --replay-bundle-dir`, renders
the bundle once through `tui --render-once`, verifies the bundle contains only
`manifest.json`, `trace.jsonl`, and `outcome.json`, validates trace/bundle JSON
record kinds and outcome consistency, and checks the TUI text includes a replay
summary, selected-frame metadata, field changes, event sequence length, and
agent audit signals.

---

## Full CLI Reference

All commands are top-level clap subcommands.

```
tianji run              One-shot pipeline on a fixture file
tianji history          List persisted runs with filters
tianji history-show     Show details for a single persisted run
tianji history-compare  Compare two persisted runs side-by-side
tianji delta            Show cross-run change tracking between two runs
tianji daemon           Daemon lifecycle and job queue
tianji webui            Serve the optional local web dashboard
tianji tui              Browse persisted runs and simulation replay in a terminal UI
tianji predict          Run Hongmeng/Nuwa simulation against configured actor profiles
tianji backtrack        Search backward intervention paths for a target goal
tianji baseline         Manage worldline baselines for divergence tracking
tianji watch            Poll feeds with fast/slow scheduling helpers
tianji doctor           Validate local config readiness without printing secrets
tianji eval             Run deterministic fixture evaluation and drift checks
tianji sources          Inspect source registry manifests and run enabled fixtures
tianji maintenance      Operator maintenance commands for local storage
tianji completions      Generate shell completion scripts (bash/zsh/fish)
```

### `tianji run`

```
tianji run --fixture <PATH> [--sqlite-path <PATH>] [--show-delta]
```

Examples:
```bash
# Deterministic fixture run; prints RunArtifact JSON and uses the default local SQLite path
tianji run --fixture tests/fixtures/sample_feed.xml

# Choose an explicit SQLite path for later history queries
tianji run --fixture tests/fixtures/sample_feed.xml --sqlite-path runs/tianji.sqlite3
```

Use `--show-delta` with `--sqlite-path` when you want stdout wrapped with the
new run artifact plus delta/alert-tier context against the previous persisted
run.

### `tianji history`

List persisted runs. Supports rich filtering.

```
tianji history --sqlite-path <PATH>
    [--limit 20]
    [--mode fixture|fetch]
    [--dominant-field conflict|diplomacy|economy|technology]
    [--risk-level low|medium|high|critical]
    [--since <ISO>] [--until <ISO>]
    [--min-top-impact-score <f64>] [--max-top-impact-score <f64>]
    [--min-top-field-attraction <f64>] [--max-top-field-attraction <f64>]
    [--min-top-divergence-score <f64>] [--max-top-divergence-score <f64>]
    [--top-group-dominant-field <str>]
    [--min-event-group-count <i64>] [--max-event-group-count <i64>]
```

Example:
```bash
tianji history --sqlite-path runs/tianji.sqlite3 --limit 5 --dominant-field technology --risk-level high
```

### `tianji history-show`

Show full detail for a single run.

```
tianji history-show --sqlite-path <PATH>
    [--run-id <i64> | --latest | --previous | --next]
    [--dominant-field <str>]
    [--min-impact-score <f64>] [--max-impact-score <f64>]
    [--min-field-attraction <f64>] [--max-field-attraction <f64>]
    [--min-divergence-score <f64>] [--max-divergence-score <f64>]
    [--limit-scored-events <usize>]
    [--only-matching-interventions]
    [--group-dominant-field <str>]
    [--limit-event-groups <usize>]
```

Examples:
```bash
tianji history-show --sqlite-path runs/tianji.sqlite3 --latest
tianji history-show --sqlite-path runs/tianji.sqlite3 --run-id 42 --limit-scored-events 5
```

### `tianji history-compare`

Diff two runs side-by-side. Shows scored events with `comparable` field, intervention diffs, and count deltas.

```
tianji history-compare --sqlite-path <PATH>
    [--left-run-id <i64> --right-run-id <i64>]
    [--latest-pair | --run-id <i64> --against-latest | --run-id <i64> --against-previous]
    [same filters as history-show]
```

Examples:
```bash
tianji history-compare --sqlite-path runs/tianji.sqlite3 --latest-pair
tianji history-compare --sqlite-path runs/tianji.sqlite3 --run-id 5 --against-latest
```

### `tianji delta`

Cross-run change tracking. Shows what changed between two runs: numeric metric deltas (impact_score, divergence_score), count deltas (event counts, actor counts), new signals (new events, dominant field changes, new intervention candidates), and overall risk direction.

```
tianji delta --sqlite-path <PATH>
    [--left-run-id <i64> --right-run-id <i64> | --latest-pair]
```

Output includes:
- `alert_tier`: FLASH / PRIORITY / ROUTINE / null
- `delta.numeric_deltas`: per-metric % change with severity
- `delta.count_deltas`: per-metric absolute change with severity
- `delta.new_signals`: newly appeared events and interventions
- `delta.summary.direction`: RiskOff / RiskOn / Mixed

Example:
```bash
tianji delta --sqlite-path runs/tianji.sqlite3 --latest-pair
```

### `tianji maintenance check / backup / export / retain / compact`

Suggested operator sequence before destructive maintenance:

1. `maintenance check` — confirm SQLite diagnostics are clean.
2. `maintenance backup` — create an online-safe SQLite copy using SQLite-native `VACUUM INTO`.
3. `maintenance export` — optionally write portable JSON/JSONL run history.
4. `maintenance retain` — prune old persisted runs.
5. `maintenance compact` — checkpoint WAL and optionally `VACUUM`.
6. `maintenance check` — confirm the database remains healthy after maintenance.

```
tianji maintenance check   --sqlite-path <PATH>
tianji maintenance backup  --sqlite-path <PATH> --output <BACKUP.sqlite3> [--overwrite]
tianji maintenance export  --sqlite-path <PATH> --output <history.json|history.jsonl> [--format json|jsonl] [--include-details] [--overwrite]
tianji maintenance retain  --sqlite-path <PATH> --keep-last-runs <N>
tianji maintenance compact --sqlite-path <PATH> [--vacuum]
```

`check`, `backup`, `export`, and `compact` reject a missing `--sqlite-path`
database instead of creating one. `backup` and `export` reject an existing
output path unless `--overwrite` is set.

`maintenance check` emits `tianji.maintenance-check-report.v1` JSON with
`quick_check`, foreign-key violation count, table counts, latest run id, file
sizes, page/freelist counts, and journal mode.

`maintenance backup` emits `tianji.backup-report.v1` JSON with source/output
paths, total source/output sizes, and run count. The backup DB is queryable by
normal history commands.

`maintenance export` emits `tianji.export-report.v1` JSON with output path,
format, run count, and bytes written. JSON exports contain one object with
`metadata` and `runs`. JSONL exports are deterministic: one metadata record
followed by one run record per persisted run. `--include-details` exports full
`history-show` payloads for each run; otherwise it exports `history` summaries
in the same newest-first ordering as `list_runs`.

`maintenance compact` emits `tianji.compact-report.v1` JSON with before/after
file sizes, before/after page and freelist counts, WAL checkpoint result, and
whether `VACUUM` ran.

#### `tianji maintenance retain`

Apply the local SQLite retention policy. The command keeps the most recent N
runs by descending run id, deletes older run rows inside one transaction, relies
on existing `ON DELETE CASCADE` cleanup for run-scoped tables, and removes
canonical `source_items` no longer referenced by raw or normalized events.

`--keep-last-runs 0` is allowed and deletes all persisted runs before removing
orphan source items. Output is JSON:

```json
{
  "schema_version": "tianji.retention-report.v1",
  "sqlite_path": "runs/tianji.sqlite3",
  "keep_last_runs": 2,
  "runs_before": 3,
  "runs_after": 2,
  "deleted_runs": 1,
  "deleted_source_items": 0
}
```

### `tianji daemon`

Daemon lifecycle: start a background process with UNIX socket control plane + loopback HTTP API.

```
tianji daemon start    [--socket-path <PATH>] [--sqlite-path <PATH>] [--host 127.0.0.1] [--port 8765]
tianji daemon stop     [--socket-path <PATH>]
tianji daemon status   [--socket-path <PATH>] [--job-id <ID>]
tianji daemon run      [--socket-path <PATH>] --fixture <PATH> [--sqlite-path <PATH>]
tianji daemon schedule [--socket-path <PATH>] --fixture <PATH> [--sqlite-path <PATH>] --every-seconds <N> --count <N>
```

Examples:
```bash
# Start daemon
tianji daemon start --sqlite-path runs/tianji.sqlite3

# Queue a run
tianji daemon run --fixture tests/fixtures/sample_feed.xml --sqlite-path runs/tianji.sqlite3

# Check daemon health
tianji daemon status

# Check specific job
tianji daemon status --job-id <id-from-run-output>

# Stop
tianji daemon stop
```

The daemon exposes a read-first HTTP API at `http://127.0.0.1:8765`:

```bash
curl http://127.0.0.1:8765/api/v1/meta
curl http://127.0.0.1:8765/api/v1/health
curl http://127.0.0.1:8765/api/v1/ready
curl 'http://127.0.0.1:8765/api/v1/runs?limit=20'
curl http://127.0.0.1:8765/api/v1/runs/latest
curl 'http://127.0.0.1:8765/api/v1/compare?left_run_id=1&right_run_id=2'
curl http://127.0.0.1:8765/api/v1/delta/latest
```

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/meta` | API metadata, resource manifest, schema version |
| `GET /api/v1/health` | Liveness probe for the local API process; does not query SQLite |
| `GET /api/v1/ready` | Readiness probe for SQLite-backed API serving; checks pool checkout and a trivial query |
| `GET /api/v1/runs?limit=20` | List persisted runs |
| `GET /api/v1/runs/latest` | Latest run summary |
| `GET /api/v1/runs/{run_id}` | Single run detail |
| `GET /api/v1/compare?left_run_id=1&right_run_id=2` | Compare two runs |
| `GET /api/v1/delta/latest` | Latest delta report from hot memory |
| `POST /api/v1/agent/command` | HMAC-signed local agent command ingress |

All responses use a stable JSON envelope:

```json
{
  "api_version": "v1",
  "data": {},
  "error": null
}
```

Error responses keep the same envelope and set `data` to `null`:

```json
{
  "api_version": "v1",
  "data": null,
  "error": { "code": "run_not_found", "message": "Run not found: 7" }
}
```

The HTTP API is intended for loopback/local use. Keep it bound to `127.0.0.1` unless you have reviewed the security model for your environment.

#### Signed agent command channel

`POST /api/v1/agent/command` is an optional local ingress path for agent commands. The daemon's default API state does not enable a command secret; when unavailable, the endpoint returns an `agent_command_unavailable` error. Do not expose this endpoint beyond loopback.

Accepted command bodies are JSON envelopes like:

```json
{
  "command_id": "cmd-local-demo-001",
  "command_type": "query",
  "payload": { "question": "latest risk summary" }
}
```

Required headers:

- `x-tianji-agent-id`
- `x-tianji-agent-tier` (`restricted` allows `observe`/`query`; `full` also allows `simulate`/`intervene`)
- `x-tianji-timestamp` (Unix seconds, within the server tolerance window)
- `x-tianji-nonce` (unique per agent within the nonce cache)
- `x-tianji-signature` (hex HMAC-SHA256)

Signature message format:

```text
timestamp + "\n" + nonce + "\n" + sha256(body)
```

Dummy-only signing example (for understanding the contract, not for a live secret):

```bash
BODY='{"command_id":"cmd-local-demo-001","command_type":"query","payload":{"question":"latest risk summary"}}'
TIMESTAMP="1710000000"
NONCE="dummy-nonce-001"
SECRET="dummy-test-secret"
BODY_SHA=$(printf '%s' "$BODY" | sha256sum | cut -d' ' -f1)
SIGNATURE=$(printf '%s\n%s\n%s' "$TIMESTAMP" "$NONCE" "$BODY_SHA" \
  | openssl dgst -sha256 -hmac "$SECRET" -binary \
  | xxd -p -c 256)

curl -X POST http://127.0.0.1:8765/api/v1/agent/command \
  -H 'content-type: application/json' \
  -H 'x-tianji-agent-id: local-demo-agent' \
  -H 'x-tianji-agent-tier: restricted' \
  -H "x-tianji-timestamp: $TIMESTAMP" \
  -H "x-tianji-nonce: $NONCE" \
  -H "x-tianji-signature: $SIGNATURE" \
  --data "$BODY"
```

Use environment variables or a local secret manager for any real deployment. Never paste real tokens or signing secrets into shell history, README snippets, issue reports, or logs.

### `tianji webui`

Serve an optional web dashboard that consumes the daemon API.

```
tianji webui [--host 127.0.0.1] [--port 8766] [--api-base-url http://127.0.0.1:8765]
            [--socket-path runs/tianji.sock] [--sqlite-path <PATH>]
```

The Web UI provides a Jarvis-style HUD with run history, detail view, and a queue-run button. Requires the daemon to be running (`tianji daemon start`).

### `tianji tui`

Read-only terminal UI for browsing persisted runs and optional simulation replay. ratatui + Kanagawa Dark.

```
tianji tui --sqlite-path <PATH> [--limit 20]
tianji tui --sqlite-path <PATH> --simulate <field:horizon> [--interactive]
tianji tui [--sqlite-path <PATH>] --trace-jsonl <PATH> [--render-once]
tianji tui [--sqlite-path <PATH>] --replay-bundle-dir <DIR> [--render-once]
```

Keybindings: `j/k` or arrow keys navigate history, `g`/`G` first/last, `Ctrl-d`/`Ctrl-u` page scroll, `Enter` opens detail or compare depending on staged state, `c` stages a compare-left run, `Esc`/`h` returns from detail/compare, and `q` quits. In simulation replay, `Left`/`h` scrubs to the previous frame and `Right`/`l` scrubs to the next frame. Trace-backed replay updates the displayed selected frame data, including tick/frame metadata, replay controls, audit coverage counts, field values, field changes, event sequence length, and compact structured agent audit fields (action, target, confidence, category, assessment, drivers, rationale).

Simulation replay is still local/read-only from the terminal perspective. Replay bundle loading reads only `manifest.json`, `trace.jsonl`, and `outcome.json` from the bundle directory. Provider-backed simulation remains optional and follows the config rules above.

### `tianji predict / backtrack / baseline / watch`

Simulation and worldline helpers remain optional and separate from the
credential-free `run` path.

```
tianji predict   --field <region.domain> [--horizon 30] [--profile-dir profiles/] [--config <PATH>] [--trace-jsonl <PATH>] [--replay-bundle-dir <DIR>]
tianji backtrack --goal <TEXT> --field-constraint <region.domain:min:max> [--field-constraint <region.domain:min:max>] [--max-interventions 5] [--profile-dir profiles/] [--config <PATH>]
tianji baseline  --sqlite-path <PATH> (--set | --show | --clear)
tianji watch     --source-url <RSS_OR_ATOM_URL> [--interval 300] [--sqlite-path <PATH>] [--config <PATH>]
```

Use `predict` without `--config` for deterministic local simulation smoke tests;
pass `--config` only when intentionally using provider-backed agents. `watch`
performs live feed polling and therefore is not part of the first-run or CI
fixture path.

### Alert dispatch dry-run/redaction

Alert dispatch is optional and is not part of the first-run path. The dispatcher supports Telegram, Discord, and generic webhook channels. Use dry-run planning first: dry-run reports which deliveries would be attempted, counts message chunks, and redacts endpoints/secrets without sending network requests.

Generic webhook payload shape:

```json
{
  "tier": "priority",
  "title": "TianJi alert",
  "summary": "Risk moved higher in the latest run.",
  "body": "Operator-readable details..."
}
```

Example secret-shaped values should stay dummy/redacted:

```text
Telegram bot token: <redacted>
Discord webhook: https://example.invalid/discord/<redacted>
Generic webhook: https://example.invalid/tianji-alerts/<redacted>
Header value: dummy-test-secret
```

In dry-run mode, reports use `status: planned` and redacted endpoints such as `https://example.invalid/.../<redacted>`. Live dispatch is only for operators who intentionally configure real Telegram/Discord/webhook endpoints outside the quickstart.

### `tianji eval`

Run the checked-in local evaluation corpus and report semantic drift as JSON.
No network, daemon, or LLM provider is required.

```
tianji eval --manifest tests/fixtures/eval/corpus.yaml
```

The command exits `0` when all cases pass and exits non-zero when any manifest
expectation or golden semantic score check fails. The report uses
`schema_version: "tianji.eval-report.v1"` and includes per-case descriptions,
check counts, failed-check counts, global/per-case `max_score_delta`, and
numeric `delta`/`tolerance` values for score drift checks.

Local gate:

```bash
bash scripts/check-eval.sh
bash scripts/check-replay-smoke.sh
```

The eval script runs only:

```bash
cargo run --quiet -- eval --manifest tests/fixtures/eval/corpus.yaml
```

The replay smoke script uses a temporary `/tmp/tianji-replay-smoke.*` workdir and
runs only local deterministic commands:

```bash
cargo run --quiet -- predict --field global.conflict --horizon 2 --replay-bundle-dir "$TMP_BUNDLE"
cargo run --quiet -- tui --replay-bundle-dir "$TMP_BUNDLE" --render-once
```

It then validates the bundle file set, manifest schema `tianji.replay-bundle.v1`,
trace schema `tianji.sim-trace.v1`, metadata/frame/completed record ordering,
outcome JSON consistency, and TUI replay text signals including the replay
summary and selected-frame audit counts without network, daemon, provider config,
or secrets.

To refresh golden snapshots intentionally after an accepted deterministic
pipeline/scoring change:

```bash
cargo run --quiet -- eval --manifest tests/fixtures/eval/corpus.yaml --update-golden
```

Normal `eval` is read-only. `--update-golden` overwrites only golden files named
in `tests/fixtures/eval/corpus.yaml` and reports them in `updated_golden_paths`.

To add a fixture case:

1. Add a credential-free RSS/Atom file under `tests/fixtures/`.
2. Add a case to `tests/fixtures/eval/corpus.yaml` with stable expected counts,
   dominant field, risk level, top event id, score tolerance, and golden path.
3. Run `cargo run --quiet -- eval --manifest tests/fixtures/eval/corpus.yaml --update-golden`.
4. Inspect the new/changed golden JSON under `tests/fixtures/eval/golden/` and
   commit only intentional semantic fields.
5. Run `bash scripts/check-eval.sh` to confirm the corpus passes without refresh.

When eval fails, inspect `cases[].checks[]`: non-numeric drift shows expected vs
actual semantic values; score drift additionally shows absolute `delta` and the
allowed `tolerance`. Update fixtures/goldens only when the changed behavior is
intentional; otherwise fix the deterministic pipeline or manifest expectation.

### `tianji sources`

Inspect a local source registry manifest, run enabled fixture sources, or
explicitly fetch enabled RSS/Atom sources. Source management is safe by default:
plain listing validates and reports registry health without network I/O.
Disabled sources are always reported but are never run or fetched.

```
tianji sources --config examples/sources.example.yaml [--run-fixtures] [--fetch-live] [--sqlite-path <PATH>]
```

Default output is JSON with `schema_version: "tianji.sources-report.v1"`, source
counts, aggregate health counters (`ready`, `skipped`, `errors`), tier counts,
and per-source status metadata:

```bash
cargo run --quiet -- sources --config examples/sources.example.yaml
```

Run enabled fixture sources only:

```bash
cargo run --quiet -- sources --config examples/sources.example.yaml --run-fixtures
```

Fetch enabled live RSS/Atom sources only when explicitly requested:

```bash
tianji sources --config ~/.config/tianji/sources.yaml --fetch-live
```

`--run-fixtures` never fetches RSS/Atom URLs. `--fetch-live` never runs disabled
sources and is the only source-registry mode that may perform network I/O. Both
run modes report concise per-source status plus artifact counts
(`raw_item_count`, `normalized_event_count`, `scored_event_count`, and
`intervention_candidate_count`), `dominant_field`, and `risk_level` without
embedding full run artifacts. The checked-in `examples/sources.example.yaml` uses
only local fixture paths and a disabled `https://example.invalid/...` dummy URL;
do not put private feed URLs, credentials, cookies, or tokens in shared
manifests.

Add `--sqlite-path <PATH>` to persist source health history when a run mode is
selected. TianJi records one health row per reported source, including disabled
sources skipped by policy, with `source_id`, `kind`, `status`, `checked_at`, item
counts, `dominant_field`, `risk_level`, and safe error text. Plain listing with
`--sqlite-path` reads latest persisted health and enriches per-source
`last_success`, `last_error`, and `last_error_message`; listing without
`--sqlite-path` remains validation-only with no database writes.

TianJi does not spawn a source scheduler daemon in this slice. Use an external
scheduler (cron/systemd/Kubernetes) to invoke live polling explicitly, for
example:

```bash
tianji sources --config ~/.config/tianji/sources.yaml --fetch-live --sqlite-path /var/lib/tianji/source-health.sqlite3
```

CI-friendly local source smoke commands:

```bash
cargo run --quiet -- sources --config examples/sources.example.yaml
cargo run --quiet -- sources --config examples/sources.example.yaml --run-fixtures
```

### `tianji completions`

Generate shell completion scripts.

```
tianji completions <bash|zsh|fish>
```

Examples:
```bash
# Bash
tianji completions bash > ~/.local/share/bash-completion/completions/tianji

# Zsh
tianji completions zsh > ~/.zfunc/_tianji

# Fish
tianji completions fish > ~/.config/fish/completions/tianji.fish
```

For release/readiness checks, generate completions to `/tmp` and inspect them;
do not install into your interactive shell unless you intend to.

---

## Daemon + Web UI Quick Setup

```bash
# 1. Persist some runs first
cargo run -- run --fixture tests/fixtures/sample_feed.xml --sqlite-path runs/tianji.sqlite3

# 2. Start daemon
cargo run -- daemon start --sqlite-path runs/tianji.sqlite3
# → Daemon runs in background. Logs at runs/tianji.sock.log.
# → API available at http://127.0.0.1:8765

# 3. Open Web UI
cargo run -- webui --sqlite-path runs/tianji.sqlite3
# → Dashboard at http://127.0.0.1:8766

# 4. Queue a run via daemon
cargo run -- daemon run --fixture tests/fixtures/sample_feed.xml --sqlite-path runs/tianji.sqlite3

# 5. Check delta
curl http://127.0.0.1:8765/api/v1/delta/latest

# 6. Stop
cargo run -- daemon stop
```

---

## What the Pipeline Does

```
RSS/Atom XML
  │  roxmltree parse + SHA-256 canonical hash
  ▼
Vec<RawItem>
  │  regex: keywords, actors, regions, field_scores
  │  actor patterns: nato, eu, un, usa, china, russia, iran
  │  region patterns: ukraine, russia, middle-east, east-asia, united-states, europe
  │  field keywords: conflict (attack, missile, troops...), diplomacy (talks, summit...),
  │    technology (ai, chip, cyber...), economy (tariff, trade, oil...)
  ▼
Vec<NormalizedEvent>
  │  Im = actor_weight + region_weight + keyword_density
  │       + dominant_field_bonus + field_diversity + text_signal_intensity
  │  Fa = dominant_field_strength + dominance_margin + coherence
  │       - near_tie_penalty - diffuse_third_field_penalty
  │  divergence_score = f(Im, Fa)
  ▼
Vec<ScoredEvent>
  │  shared keyword/actor/region + 24h time window
  │  causal ordering + evidence chain
  ▼
Vec<EventGroupSummary>
  │  dominant_field → intervention_type mapping
  │  strong groups (3+ members, 5+ shared signals) → escalation override
  │  weak groups (2+ members, 1+ link) → containment/stabilization
  ▼
Vec<InterventionCandidate>
  │  if --sqlite-path: persist to SQLite + compute delta vs previous run
  ▼
RunArtifact JSON (stdout) + optional SQLite persistence + optional DeltaReport
```

---

## Repository Layout

```
tianji/
├── Cargo.toml                  # Rust crate manifest
├── src/
│   ├── main.rs                 # CLI entry (17 top-level subcommands)
│   ├── lib.rs                  # Pipeline library + integration tests
│   ├── models.rs               # RawItem → NormalizedEvent → ScoredEvent → RunArtifact
│   ├── fetch.rs                # RSS/Atom parsing + SHA-256 canonical hash
│   ├── normalize.rs            # Keyword/actor/region extraction (LazyLock regexes)
│   ├── scoring.rs              # Im/Fa scoring + divergence + rationale
│   ├── grouping.rs             # Event grouping + causal ordering
│   ├── backtrack.rs            # Intervention candidate generation (HeadlineRole enum)
│   ├── storage.rs              # SQLite persistence + history/source-health/maintenance CRUD
│   ├── daemon.rs               # UNIX socket + job queue + serve + mark_delta_signals_alerted
│   ├── api.rs                  # axum /api/v1 HTTP API + response envelope
│   ├── webui.rs                # Embedded static files + API proxy + /queue-run
│   ├── tui/                    # ratatui history/simulation browser (Kanagawa Dark, Vim keys)
│   ├── delta.rs                # Crucix Delta Engine: compute_delta, MetricSnapshot, severity
│   ├── delta_memory.rs         # HotMemory, AlertDecayModel, AlertTier, atomic I/O
│   └── utils.rs                # round2, days_since_epoch, collect_string_array
├── tests/
│   └── fixtures/               # sample_feed.xml + contract fixtures
├── plan.md                     # Authoritative architecture document
└── README.md
```

---

## Design Principles

1. **Local First** — deterministic fixture and SQLite workflows run without cloud dependencies; provider-backed simulation, live feed fetch, and alert dispatch require explicit opt-in.
2. **Deterministic First** — BTreeMap (not HashMap), LazyLock regex, no wall-clock in pipeline. Same input always produces same output.
3. **CLI First** — every feature ships as a CLI subcommand before any UI or service layer.
4. **Single Binary** — `cargo build` produces one binary. Web UI assets are `include_str!` embedded.
5. **No LLM required for core runs** — the deterministic pipeline is rule-based; LLM-backed multi-agent simulation is optional and configured separately.
