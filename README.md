# TianJi (天机)

A local-first bidirectional world simulation laboratory: explore forward outcomes, search for
plans that meet a goal, and compare recorded worldlines. The current model is a bounded fictional
civilian supply chain, not a calibrated forecast or a general world simulator.

## Run

Requires Python 3.12+, uv, Node 22.12+ and a POSIX host.

```bash
npm --prefix web ci
npm --prefix web run build
uv sync --project backend --locked
uv run --project backend --locked python -m tianji_lab serve --port 8787 --data-dir .local-data
```

Open http://127.0.0.1:8787. The service prints the path of its generated token file; use that token
to connect. Keep the data directory to preserve scenarios and branches. One process owns it at a time.

## Features

- Edit scenario parameters, explicit disturbances, actions and terminal goals.
- Run deterministic forward simulations and bounded, forward-verified goal search.
- Fork recorded ticks, compare frozen specifications, inspect the timeline, export/import replay.
- Create role-scoped observations and independently adjudicate action proposals without changing
  the source branch. The director can explicitly use the proposed action in a new fork.
- Use the same operations through the React workbench, HTTP and official MCP stdio adapter.

Python/FastAPI/Pydantic/SQLite implement the model and service in `backend/`; React/TypeScript/Vite
implement `web/`. Old implementations remain recoverable through Git, not parallel development trees.

## Development

```bash
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run format:check
npm --prefix web run build
```

Run relevant tests and inspect actual behavior. Do not create recurring verification reports,
screenshot archives, prompt/response dumps or per-session evidence directories. Ordinary unit and
integration tests remain part of the source. Saved scenarios, replay branches and explicit adjudication
history are product data, not development logs.

See [the guide](docs/laboratory.md), [execution contract](docs/specs/lab/execution-contract.md),
and [current development state](handoff.md).
