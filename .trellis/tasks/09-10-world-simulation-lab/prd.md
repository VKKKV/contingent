# TianJi — Bidirectional World Simulation Laboratory

Status: implementation authorized on 2026-09-10. The user explicitly selected TypeScript + Python. Web-first product direction and shared agent interfaces are approved. Destructive legacy cleanup, old database migration, paid model calls and remote deployment remain separate confirmation gates.

## User-approved requirements

- Define TianJi as a bidirectional world simulation laboratory (双向世界推演实验室), with a computational Laplace's demon (计算版拉普拉斯妖) as its creative vision, not a claim of perfect prediction.
- Prioritize the browser workbench. Forward exploration and backward goal-directed planning are core capabilities, not optional distant phases.
- Every product capability must be controllable by an agent through documented, structured interfaces. Agent control must not mean bypassing policy or granting arbitrary system access.
- The assistant may select secondary product requirements; stop and consult the user when a consequential unresolved decision arises.
- Reconsider the implementation language based on the product and relevant projects; do not treat the existing Rust implementation or competitor popularity as decisive by itself.

## Proposed default scope

- Local-first single-user laboratory, browser-first; a bounded fictional civilian supply-chain scenario for initial validation.
- Scenario editor, goal/constraint editor, structured turns, forward runs, goal-directed search with same-model forward verification, branching, comparison, and replay.
- Shared application operations for Web, programmatic API, and MCP; semantic workspace commands for selected branch/tick/viewport rather than pixel automation.
- Explicit rules, resource/time constraints, role-scoped observations, independent adjudication, model/assumption provenance and limited jobs.
- Preserve the existing Rust revision and local databases without deletion or in-place schema migration during planning.

## Resolved stack decision

The user selected TypeScript + Python on 2026-09-10. Implement a React/Vite browser workbench and a Python/FastAPI/Pydantic application with a bounded worker and SQLite. Preserve Rust source and runs/*.sqlite3 unchanged; do not keep a parallel Rust backend in the new runtime. First implementation slice is defined by m1-contract.md, which narrows architecture.md to an executable bounded model.

## Current code baseline

Revision: a5a3c656e779f6444cc4408cc02a7a8dac4e5e64; clean at task creation.

Earlier same-session execution: 445 cargo tests pass; fixture eval 2 cases/34 checks pass; trace/replay works without provider. Public daemon start fails due to nested Tokio runtime. CLI predict initializes a synthetic state; forward branch probabilities and backward search are heuristic, not calibrated real-world forecasts. These observations remain evidence about the old implementation, not acceptance criteria for an identical rewrite.

Local runs/*.sqlite3 databases exist. Their contents and migration requirements are not yet audited; preserve them read-only. The old architecture and contracts remain in force for old code while this task proposes a new design.

## Acceptance criteria for planning

- [x] Compare target stacks using inspected manifests/code and concrete ecosystem examples: research/language-choice.md.
- [x] Define agent/Web operation parity, authority boundaries, job lifecycle and reproducibility: architecture.md.
- [x] Define a bounded first slice that includes both directions and browser E2E acceptance: architecture.md, M1.
- [x] Record proposed migration/compatibility boundaries and important confirmation gates: research/language-choice.md and architecture.md.
- [x] Obtain stack decision before implementation starts: TypeScript + Python selected.

## Planning deliverables

- [Architecture and acceptance contract](architecture.md): language-independent requirements, operation parity, jobs, permissions, reproducibility and milestones.
- [Language decision proposal](research/language-choice.md): recommend TypeScript/React/Vite + Python/FastAPI/Pydantic + SQLite/worker, with Rust preserved as the reference and not a parallel production backend.
- Product and stack are approved. Use m1-contract.md for the bounded executable slice; wider architecture.md defines longer-term direction, not an assertion that every feature ships in M1.

## Out of scope for this planning task

Implementation may add the new backend/frontend and dependency locks. Destructive legacy cleanup, migration of existing databases, paid model calls, remote deployment, production action integration and untrusted scenario code execution remain out of scope. No claim that a language change repairs the world model.

## Research context

The previous KB report is at /home/kita/code/knowledge/10-projects/tianji/wargaming-and-worldline-design.md. Relevant upstream examples previously inspected: God's Eye View, ShadowBroker, Crucix, WarAgent, MiroFish, World Monitor and LangGraph. This task will retain portable source URLs rather than depend on temporary research folders.
