# ADR draft: target implementation language

Status: accepted by the user on 2026-09-10 (TypeScript + Python). Implementation is additive under backend/ and web/ on feat/world-simulation-lab; old source/databases remain preserved. Destructive migration is not authorized.

## Recommendation

Use TypeScript + React + Vite for the browser workbench, and Python + FastAPI + Pydantic for the application service and simulation/planning worker. Keep SQLite for the first local version. Expose a reviewed capability catalog through OpenAPI and an MCP adapter. Do not require a second Node backend at runtime just to serve the built Web assets.

Treat the current Rust system as a preserved reference and source of selected contracts/tests, not as a permanently co-running second backend. Native Rust/C++ acceleration remains an optional response to measured hotspots, not part of the first migration.

## Why this recommendation fits this product

The core has changed from a deterministic geopolitical feed CLI to a browser-operated simulation laboratory whose scenarios, rules, role policies, planners and evaluation methods will evolve. The expected advantage of Python is direct access to scientific, graph, agent-based-modeling and planning research ecosystems and rapid model iteration, not superior raw execution speed. The benefit of TypeScript is the interactive workbench, typed client operations and browser tooling. Both are design judgments, not measured productivity benchmarks.

React/Vite is a proposed implementation default because the first product is an authenticated local application, not a server-rendered publishing site. Next.js is viable, but its server rendering and second server layer do not directly solve the current workbench requirement.

Cross-language contracts are a real cost: derive TypeScript client/schema artifacts from reviewed server schemas and enforce parity in CI. Avoid handwritten competing Python/TypeScript validation definitions as separate sources of truth.

## Source-backed comparison

The inspected sample is deliberately small; it does not establish that Rust is rare or unsuitable across the industry.

- God's Eye View is Vanilla JavaScript + Cesium/Vite, with proxy/server behavior in Vite configuration. This is evidence for a browser-centric visualization stack, not for a numeric simulation kernel. Snapshot 759652207fd1279ece97f0f19af566feb9a82146: https://github.com/bilawalsidhu/gods-eye-view/blob/759652207fd1279ece97f0f19af566feb9a82146/package.json
- ShadowBroker combines a TypeScript/React/Next frontend with Python/FastAPI/Pydantic, plus libraries such as NumPy and NetworkX. Its frontend also contains a privacy-core WASM build script; therefore even this reference does not justify saying native code has no role. Snapshot cd6395f5ee7d5232fc7b553bf74f5e514deaafdb: https://github.com/BigBodyCobain/Shadowbroker/blob/cd6395f5ee7d5232fc7b553bf74f5e514deaafdb/frontend/package.json and https://github.com/BigBodyCobain/Shadowbroker/blob/cd6395f5ee7d5232fc7b553bf74f5e514deaafdb/backend/pyproject.toml
- MiroFish has a Python/Flask backend with Pydantic, CAMEL/OASIS and Zep Cloud dependencies. The lesson is Python research-library integration, not to copy Flask, Zep or a mandatory cloud dependency. Snapshot 39d849138ef254f6c737ab4c4705e5545dbe31d4: https://github.com/666ghj/MiroFish/blob/39d849138ef254f6c737ab4c4705e5545dbe31d4/backend/pyproject.toml
- Crucix uses JavaScript/Node/Express for a local intelligence application. It supports the viability of a simple JS service, but is not evidence that this stack offers the same modeling ecosystem. Snapshot 3db7068817e0c815df353fa0f19657c85142789d: https://github.com/calesthio/Crucix/blob/3db7068817e0c815df353fa0f19657c85142789d/package.json

The separate simulation-library evidence record was removed in the 2026-09 documentation cleanup as superseded history (recover from Git history). No dependency versions or upstream performance claims in these examples become automatic TianJi requirements.

## Alternatives and costs

### Keep Rust application/kernel + TypeScript frontend

Best if preserving the existing implementation, native compute, predictable memory behavior and deployment simplicity dominate. Rust can expose exactly the same Web and MCP capabilities. The existing 445 passing tests and storage/replay code are real assets; the nested-runtime bug is an implementation bug, not an argument against the language.

Trade-off: Python-only model/research libraries require bindings, subprocesses or a second service; fast-changing scenario and LLM/tool schemas are less convenient if duplicated across these boundaries. The present world-model/goal-search limitations still need redesign regardless of language.

### TypeScript full stack

Best if the priority is one language, shared types and fastest UI/tool integration with a relatively small custom simulation model. API and MCP ecosystems exist; there is no requirement to use Python just to call a model.

Trade-off: CPU-heavy search needs workers or native libraries; adopting Python-first ABM/scientific/planning libraries later may introduce another runtime anyway. This is a valid alternative if integrated research libraries are not a real requirement.

### Python + TypeScript

Best fit for the stated long-term experimental modeling and interactive laboratory direction. Trade-offs: two language/toolchains, schema-generation discipline, Python dependency packaging, explicit worker boundaries, and rewriting behavior not covered by language-independent tests. The speed of Python loops is not a substitute for bounded search; profile representative kernels before selecting acceleration.

Do not combine Python + TypeScript + Rust as three equal application layers from day one. Keep one authoritative domain service/kernel for a given scenario; an optimized backend must pass the same model-contract tests before use.

## Proposed migration boundary

After approval, create a new development branch and add the new application alongside the preserved Rust code without moving or deleting the old tree first. Use separate data directories and explicit schema versions. Preserve runs/*.sqlite3 and old bundles; import/export compatibility is a separately tested adapter, not a promise of bit-identical new simulation semantics.

Use current Rust tests to identify contracts worth preserving, but do not force the new model to reproduce known heuristic behavior. Capture semantic fixtures for valid legacy data only. Stop and ask before deleting old code, retiring maintained entrypoints or transforming user databases. Freeze the baseline by its commit before implementation and retain an independently runnable reference build.

The first release should be one local installation/dev workflow with browser assets, API and a bounded worker, not a distributed platform. Package versions, Python minor version and library choices are pinned only after compatibility checks. No full builds or performance comparison of the proposed new stack have been performed in this planning task.

## Decision recorded

The user selected Python/TypeScript. Implement the additive M1 slice on feat/world-simulation-lab, with m1-contract.md governing its exact scope. This decision does not authorize destructive legacy cleanup, paid provider usage or remote deployment.
