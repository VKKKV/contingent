# Laboratory guide

## Run

From the repository root, `./start.sh` starts the cached local model and the web/API together.
Use `./start.sh --no-model` to browse saved analyses and use deterministic API operations, or
`--model /path/to/model.gguf` for another model. Ctrl+C shuts down both processes; no log archives
are created. See `./start.sh --help`.

Manual setup:

```bash
npm --prefix web ci
npm --prefix web run build
uv sync --project backend --locked
uv run --project backend --locked python -m tianji_lab serve --port 8787 --data-dir .local-data
```

Open http://127.0.0.1:8787 and use the generated token file to connect. Alternatively set
`TIANJI_TOKEN` in the service environment. Never put credentials in URLs or source files.
The browser stores the credential only for the current tab. It grants full local director access.

The API serves `web/dist`; rebuild after UI changes. For development, run
`npm --prefix web run dev` with the API on port 8787. SQLite lives in the chosen data directory.
Only one service may own it; supported hosts use POSIX file locking. Existing databases elsewhere
are not opened, converted or deleted automatically.

## Bounded analysis projects

The default workspace creates durable projects and schedules separate framing, strategy, critic,
optional revision and synthesis calls. See [bounded analysis](bounded-analysis.md) for the full
operation contract, task/issue graphs, privacy boundary, budgets, cancellation and restart behavior.
Creating a project explicitly persists the user request and validated task results; there are no
raw transcript logs. All roles share the local model and are not independent factual evidence.

## Legacy single-call analysis

The legacy analysis view takes a natural-language objective, not supply-chain parameters. Connect with the
local token, enter the goal, optionally adjust horizon/perspective/constraints, and generate.
The model returns candidate turning points and alternative paths. No result is synthesized when
inference fails, and generation does not automatically save anything. The current small-model
prompt uses five nodes and two routes with distinct interventions and shared later conditions.
This branching/converging scaffold improves output reliability; it is not discovered causal structure.

Select a path to highlight its sequence and tradeoff. Select a node for actors, concrete action,
proposed mechanism, prerequisites, risks and observable signals. Diagram stages express a proposed
dependency order, not calculated dates, likelihoods or proof of causation. Shared nodes can belong
to multiple paths. Zoom/scroll the diagram on smaller screens; node selection also works by keyboard.

Read the interpretation, assumptions and tensions before acting. The model has no live evidence
retrieval, and the application does not verify the claims against the world. Reframe constraints and
regenerate to explore alternatives, rather than treating a route as a proven optimal intervention.
The supply-chain kernel does not validate open-ended scenario paths.

Save explicitly to retain the validated structured result in SQLite; reopen it from saved projects.
Up to 100 immutable saves are supported. Saved results are user-owned product objects, not raw
provider logs. Without a model, saved results remain accessible in the Web. The supply-chain
experiment has no Web page; its existing HTTP, CLI and MCP operations remain available.

## Supply-chain compatibility API

The old page and navigation are removed; the kernel, operation registry and user databases are
unchanged. Use HTTP, CLI or MCP for these retained operations, not browser controls:

1. `scenario_list`, `scenario_create`, `scenario_update`: bounded parameters and revision checks.
2. `run_forward`, `job_get`, `branch_get`: per-turn actions and recorded results.
3. `run_backward`: bounded goal search, with completion read through `job_get`.
4. `branch_fork`, `branch_compare`: recorded ticks and equal frozen specifications.
5. `branch_export`, `branch_import`: replay-validated state, actions, events and digests.

Inspect each argument schema with `./tianji schema NAME`; CLI examples appear below. Observation,
proposal, adjudication and workspace operations also remain callable through the shared registry.
Workspace selection no longer drives a browser view.

Results retain frozen specifications even after the live scenario changes. `found` means a candidate
exists; `exhausted: false` means alternatives remain unexplored. `no_solution` requires exhaustive
finite-model search; `budget_exhausted` is undecided, not proof of impossibility.

## Model semantics

The fictional civilian supply chain has three actions: `wait`, `order_standard`, `order_express`.
An order spends cash and removes one shipment from supplier stock. Each turn purchases, advances
the clock, receives shipments due, applies declared disturbances, then serves demand.
There are no sales revenues or hidden market dynamics.

- `delivered` counts customer demand served; `shortage` is cumulative unmet demand, not backlog.
- `lost` counts goods destroyed by supplier disturbances and remains in the conservation total.
- `demand_spike` adds 1–20 units of demand at a declared tick.
- `supplier_loss` removes 1–200 stock units, clamped to what remains, without carrying excess loss.
- At most ten disturbances, one per tick/kind, all inside the scenario horizon.

Goods and cash are conserved; demand served plus shortage equals elapsed declared demand. Empty
schedules use `supply-chain.v1`, nonempty schedules use `supply-chain.v2`. The rule version derives
from the specification. There is no randomness or calibrated probability.

Goal search is bounded enumeration, not time reversal or real-world causal inference. It ranks up
to three candidates by spend, shortage and action order among explored plans. Fork/import replay
reconstructs ancestry from the complete action prefix instead of trusting a claimed starting state.

## Observations and independent adjudication

Save a role projection of a recorded branch tick. Retailers see tick, inventory, cash, delivered,
shortage, spent and shipments; suppliers see tick, supplier stock and shipments. The envelope binds
actor, role, tick, branch and frozen revision/spec. Hashes establish integrity, not authentication.

Propose an action and use a distinct referee label to adjudicate it. Retailers may wait or order;
suppliers can only wait because the model has no supplier purchase command. Invalid actions are
rejected without substitution. Accepted results are one-step previews from the authoritative kernel,
not branch mutations. Fork separately to explore an action. Separate actors do not vote or resolve
simultaneous turns.

Saved observations/adjudications are explicit product records, capped at 100 of each per branch.
They survive restart but are not part of branch export bundles. Imported branches receive new IDs.
All clients remain directors; do not distribute the director token to untrusted participants.

## Local model proposals

Local inference is opt-in. Start an existing GGUF using llama.cpp in a separate terminal:

```bash
llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 18789 \
  --alias tianji-local --ctx-size 8192 --parallel 1 --gpu-layers 99 \
  --reasoning off --chat-template-kwargs '{"enable_thinking":false}'
```

Start the laboratory with `TIANJI_LOCAL_MODEL_URL=http://127.0.0.1:18789` and
`TIANJI_LOCAL_MODEL_NAME=tianji-local` in its environment. Without configuration, manual proposals
remain usable and model requests return an explicit disabled error. Never expose the model endpoint
beyond loopback. No model downloads or external providers are invoked by Contingent.

Through HTTP, CLI or MCP, save an observation and explicitly request a local model proposal. Only
its role projection and public action rules are sent; hidden authoritative state and director
credentials are not.
The server binds identity and observation hash, validates the returned action, and returns a proposal.
The director must still adjudicate separately. A manually changed action should use the manual
policy identifier `manual.director.v1`, not retain model attribution.
No prompts, raw completions or test reports are archived. This is a single proposal call, not an
unattended actor scheduler or a quality claim about the model.

## Runtime meter

The runtime tab displays device UTC time using original static nixie PNGs, not CSS imitations
or counts presented as divergence. It requires neither authentication nor a model. Time is sampled
on every tick and tab resume, not incremented from a counter. Local images preserve full aspect
ratio; [source and GPL notices](../web/public/vendor/divergencemeter/README.md) are included.
GIFs and audio are excluded; no original news/API or external scripts are loaded.

Secondary legacy saved-analysis counts come from `./tianji call analysis_stats`. Saving another
legacy copy counts again; nodes and paths are not deduplicated. Recent legacy generation duration
is browser-memory-only and resets on reload. The API additionally exposes separate multi-agent
run/task/node totals. The meter uses full-viewport composition and original proportions; local
tsParticles supplies decorative particle links, disabled for reduced motion and paused while hidden.
The shared analysis theme and graph controls have desktop/mobile browser coverage. Full cross-state
visual reproduction remains a separate acceptance boundary.

The new project workspace uses actual separately executed tasks; task dependencies and issue
relations are separate graphs. The legacy view remains a single model call followed by graph
validation, with no invented task history. Neither workflow performs independent fact checking.

## Command-line interface

`./tianji operations` discovers every operation from the running service; `./tianji schema NAME`
shows its argument schema. `./tianji call NAME` invokes it using the same HTTP validation as the UI.
The `vision_*` names and `vision` argument are compatibility identifiers, not product terminology.

```bash
./tianji health
./tianji schema scenario_create
./tianji call scenario_create --json '{"spec":{"name":"CLI experiment"}}' --request-id experiment-1
./tianji call scenario_list
./tianji call run_forward --json '{"scenario_id":"SCENARIO_ID","actions":["wait"]}'
./tianji call job_get --json '{"id":"JOB_ID"}'
./tianji call vision_generate --json '{"vision":"Improve access to public education","horizon":"Five years"}'
./tianji call vision_list
```

IDs in uppercase are placeholders to replace with actual returned IDs. A queued job is not a
completed result; poll `job_get`, or call `job_cancel` if desired. Legacy `vision_generate` does not save.
To save its result, pass an argument object containing the returned draft under `draft` to
`vision_save`; reopen through `vision_get`. `--file` and `--stdin` accept argument JSON directly,
not an `arguments` wrapper. Do not pass a credential as a command-line token value.

Authentication precedence: `--token-file PATH`, then `TIANJI_TOKEN`, then the repository's
`.local-data/token`. The wrapper works from other directories; relative input/token paths remain
relative to the caller. For a custom data directory, pass its token file explicitly.

```bash
./tianji --url http://127.0.0.1:8787 --token-file .local-data/token operations
./tianji call scenario_create --file arguments.json --request-id experiment-1
printf '%s' '{"id":"JOB_ID"}' | ./tianji call job_get --stdin
```

Successful stdout has `ok: true` and `data`; errors have `ok: false` and `error`, with nonzero exit.
Auto-generated mutation request IDs are printed on stderr before sending. Preserve them for
uncertain results; retry the same ID with identical arguments rather than creating a second write.
Do not retry model calls expecting idempotent output: generation is nonmutating but still computes.
Timeout defaults are 190 seconds for analysis generation, 40 for actor proposals and 15 otherwise;
`--timeout` accepts 1–300 seconds. Only loopback HTTP is allowed; proxies and redirects are disabled.

All future registry operations are discoverable without adding a parallel command implementation.

## HTTP and MCP

`GET /health` is public; `/api` requires Bearer authentication. `GET /api/capabilities` provides the
operation names and strict generated schemas. `POST /api/operations/<name>` accepts
`{"arguments": {...}, "request_id": "unique-id-for-mutations"}` and returns data or an explicit error.
Mutations share transactional idempotency: identical repeated requests return the original result;
changed input under the same ID conflicts. Refetch jobs/workspace for current state.

Operations cover scenarios, forward/search/fork jobs, branches, role observations, model proposals,
adjudication and workspaces. The [execution contract](specs/lab/execution-contract.md) is authoritative.

For MCP, configure a client to launch:

```text
command: uv
args: [run, --project, /absolute/path/to/tianji/backend, --locked, python, -m, tianji_lab, mcp, --url, http://127.0.0.1:8787]
env: TIANJI_TOKEN supplied through the client's secret configuration
```

MCP discovers the same registry and calls the authenticated HTTP service. Workspace changes use
revision CAS and retain compatibility selection/tick/panel state. There is no supply-chain browser
view to render that state. The analysis Web UI separately rejects stale async results after input,
connection or selection changes.

## Development checks and boundaries

Use the pytest, Ruff, Vitest and build commands in the root README. Run real browser/API checks when
changing their behavior; results belong in the immediate response, not mandatory artifact directories.
Model failure must remain visible, never replaced with a fabricated action. Product branch replay
and explicit adjudication history are not development logs and remain available.

Remote providers, participant credentials, simultaneous turn rules, deployment and real-world
integrations need separate decisions. Local model proposals do not grant any of those capabilities.
