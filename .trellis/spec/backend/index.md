# Backend Development Guidelines

> Scope: this directory describes the preserved **legacy Rust** implementation. For new Python/TypeScript laboratory code, read [../lab/index.md](../lab/index.md) and the active M1 contract. The user-approved Web-first TS/Python direction supersedes Rust-only/CLI-first constraints for the new directories; it does not delete or migrate the old code.

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines, contracts, and specs for backend development.

**Authority**: Root `plan.md` is the authoritative architecture document. It defines
the Rust project structure (§10), dependency list (§11), and phased build order (§12).

**Migration state**: Complete. Python oracle retired in Phase 6 (v0.2.0).
All Rust milestones have passed parity gates. The project is now a pure Rust binary.

- **Guidelines**: How to write code (conventions, patterns, anti-patterns)
- **Contracts**: What subsystems do (shipped behavior boundaries, frozen vocabularies)
- **Specs**: Technical designs for specific domains (scoring model, development roadmap)

---

## Pre-Development Checklist

Before writing Rust code:

1. Read `plan.md` for architecture, project structure, and build phases
2. Read the **scoring spec** if modifying heuristic/analysis behavior
3. Read the relevant **contract** in `contracts/` if your change touches a shipped subsystem
4. Read the **thinking guides** in `spec/guides/` for cross-layer and code-reuse considerations

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Project layout — Rust target structure | Rust-only |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns — Rust | Rust-only |
| [Error Handling](./error-handling.md) | Error types and handling — Rust `TianJiError` enum | Rust-only |
| [Database Guidelines](./database-guidelines.md) | SQLite patterns — Rust rusqlite | Rust-only |
| [Logging Guidelines](./logging-guidelines.md) | Output conventions — Rust | Rust-only |

---

## Contracts Index

| Contract | Description |
|----------|-------------|
| [Daemon Contract](./contracts/daemon-contract.md) | Local daemon runtime contract |
| [Local API Contract](./contracts/local-api-contract.md) | Read-first loopback HTTP API contract |
| [TUI Contract](./contracts/tui-contract.md) | Terminal UI contract (superseded by plan.md §9 for Rust TUI) |
| [Web UI Contract](./contracts/web-ui-contract.md) | Optional browser UI contract |

---

## Specs Index

| Spec | Description |
|------|-------------|
| [Scoring Spec](./scoring-spec.md) | Deterministic `Im`/`Fa` scoring model: formulas, rationale, deferred work |
| [Development Plan](./development-plan.md) | Rust migration milestones and guardrails |
| [Phase 2.2 Worldline Model](./phase-2.2-worldline-model.md) | Worldline data model, FieldKey, Baseline, Blake3 snapshot, divergence (implemented) |
| [Phase 2.3 Actor Profiles](./phase-2.3-actor-profiles.md) | 3-tier actor profile loading from YAML, ProfileRegistry, dynamic/cross-scenario stubs (implemented) |
| [Rust Rewrite Plan](../../plan.md) | Full Rust rewrite vision: Cangjie/Fuxi/Hongmeng/Nuwa architecture, TUI spec, dependency list |

---

**Language**: All documentation should be written in **English**.
