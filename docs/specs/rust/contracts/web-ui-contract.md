# TianJi Web UI Contract

## Purpose

This document defines the shipped contract for TianJi's optional browser UI.

The web UI exists as a convenience read surface for local operators who want browser access to persisted runs, compare views, and intervention browsing without changing the underlying storage or API contract.

## Boundaries

1. **Optional and off by default**
   - TianJi works without any web server.
   - Operators start the UI explicitly when they want it.

2. **Separate from the daemon**
   - The UI is served by `tianji webui`.
   - By default it binds to `127.0.0.1:8766`.
   - It consumes the daemon-hosted API instead of replacing it.

3. **Local-only**
   - The UI is a loopback convenience surface, not a hosted product.
   - No auth, accounts, or cloud deployment assumptions belong here.

4. **Not the write authority**
   - CLI writes remain authoritative.
   - The UI should reuse existing local surfaces rather than widen `/api/v1/*` into a browser-owned backend.

## Default Runtime Values

- UI host: `127.0.0.1`
- UI port: `8766`
- daemon/API base URL in examples: `http://127.0.0.1:8765`

## Operator Startup

Start the daemon first so the API is available:

```bash
tianji daemon start --sqlite-path runs/tianji.sqlite3 --socket-path runs/tianji.sock --host 127.0.0.1 --port 8765
```

Then start the optional web UI:

```bash
tianji webui --api-base-url http://127.0.0.1:8765 --host 127.0.0.1 --port 8766
```

Then open:

```text
http://127.0.0.1:8766/
```

## Expected Surface

The shipped UI is intentionally thin and should stay aligned with the frozen local API vocabulary. It currently covers local browsing for:

- run history
- run detail
- explicit run compare
- intervention browsing

It may proxy local queue actions through the local daemon control surface when needed, but it should not redefine the daemon, API, or CLI contracts.

## Relationship to Other Surfaces

- `README.md` gives the operator-facing startup summary.
- `local-api-contract.md` defines the payloads the UI consumes.
- `daemon-contract.md` defines the local process that hosts the API.
- `tui-contract.md` defines the alternative read-only terminal browser.

## Non-Goals

This contract does not include:

- replacing the CLI as the write authority
- widening `/api/v1/*` with browser-specific write routes
- public hosting or remote access
- frontend build tooling requirements
- a separate browser-only domain model
