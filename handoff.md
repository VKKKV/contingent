# Current development state

Product: Contingent. Repository: https://github.com/VKKKV/contingent.
Existing `tianji_lab`, CLI, environment/storage keys and local directory remain compatible.

The default workbench is durable goal-directed scenario analysis. A bounded runner makes separate
same-model calls for framing, candidate strategies, critique, optional revision and synthesis.
Task DAG and issue graph are distinct React Flow/Dagre views with source links and filters.
Projects persist user inputs, task state and validated public structured results, not raw transcripts
or hidden reasoning. Multiple roles are not independent evidence; no live retrieval or empirical
causal validation exists. See [bounded analysis](docs/bounded-analysis.md).

Legacy `vision_*` single-call generation and explicit saves remain available under the legacy
analysis tab. The supply-chain page is removed; its deterministic kernel, HTTP/CLI/MCP operations
and existing user databases remain compatible. Existing identifiers are not renamed.

The runtime clock uses original static nixie PNG from the pinned GPL source chain, showing local
system UTC as HH.MM.SS. Statistics are secondary and separate from time. GIF and audio are excluded.
The legacy actor and vision paths now share bounded HTTP transport without changing their
endpoint-specific parsers, timeouts or errors. The durable workspace uses TanStack Query core for
reads/polling with isolated per-connection caches and explicit idempotent mutations. Legacy single-call
controllers remain separate, with idempotent save retries. Legacy path diagrams now use React Flow/Dagre as well, preserving
path highlighting, keyboard selection and explicit saves. The meter now follows full-viewport
composition, 2px gaps and a reduced 150px digit cap. Locally bundled tsParticles replaces the
CSS background imitation; reduced motion removes it and hidden tabs pause it. Graph controls remain
visible, task selection retains keyboard focus, and explicit task navigation scrolls to details.
Desktop/mobile live checks and side-by-side meter inspection have run. Full cross-state visual
reproduction remains pending; see [the development plan](docs/development-plan.md).

Next feature direction is user-supplied material with inspectable citations, followed by
human review, explicit assumption branches and portable analysis packages. These are planned,
not current capabilities; see [next development](docs/next-development.md). Keep the current runner
and graph stack instead of adding another agent framework.

Start with `./start.sh`; it builds the Web and starts the cached local model and authenticated API.
`./tianji operations`, `schema NAME` and `call NAME` expose the complete live registry through CLI.
Web, CLI and MCP share validation. Normal tests and immediate live checks require no recurring
reports, screenshot archives or prompt dumps. Preserve all existing user databases.
