# Laboratory guide

## Run

From the repository root:

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

## Workbench

1. Select/create a scenario, edit bounded parameters and disturbances, and save with revision checks.
2. Choose per-turn actions and run forward; inspect the recorded timeline, resources and events.
3. Enter terminal goals and a node budget; search for plans verified by the same forward model.
4. Fork a recorded tick and compare branches with identical frozen specifications.
5. Export/import a branch when wanted; imports validate every state, action, event and digest.

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
  --alias tianji-local --ctx-size 4096 --parallel 1 --gpu-layers 99 \
  --reasoning off --chat-template-kwargs '{"enable_thinking":false}'
```

Start the laboratory with `TIANJI_LOCAL_MODEL_URL=http://127.0.0.1:18789` and
`TIANJI_LOCAL_MODEL_NAME=tianji-local` in its environment. Without configuration, manual proposals
remain usable and model requests return an explicit disabled error. Never expose the model endpoint
beyond loopback. No model downloads or external providers are invoked by TianJi.

After saving an observation, explicitly request a local model proposal. Only its role projection
and public action rules are sent; hidden authoritative state and director credentials are not.
The server binds identity and observation hash, validates the returned action, and returns a proposal.
The director must still adjudicate separately. Editing the proposed action makes it a manual proposal.
No prompts, raw completions or test reports are archived. This is a single proposal call, not an
unattended actor scheduler or a quality claim about the model.

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
revision CAS and describe desired selection/tick/panel, not proof that a browser has rendered them.
The browser rejects stale async responses and preserves human drafts after conflicts.

## Development checks and boundaries

Use the pytest, Ruff, Vitest and build commands in the root README. Run real browser/API checks when
changing their behavior; results belong in the immediate response, not mandatory artifact directories.
Model failure must remain visible, never replaced with a fabricated action. Product branch replay
and explicit adjudication history are not development logs and remain available.

Remote providers, participant credentials, simultaneous turn rules, deployment and real-world
integrations need separate decisions. Local model proposals do not grant any of those capabilities.
