# Backend Contracts

> Executable contracts defining shipped behavior boundaries for TianJi subsystems.

---

## Overview

Contracts define **what** each subsystem does, its boundaries, and its relationship to other surfaces. Unlike guidelines (which define **how** to write code), contracts define shipped behavior and frozen vocabularies.

---

## Contracts Index

| Contract | Description | Status |
|----------|-------------|--------|
| [Daemon Contract](./daemon-contract.md) | Local daemon runtime: socket control plane, job lifecycle, operator commands | Shipped |
| [Local API Contract](./local-api-contract.md) | Read-first loopback HTTP API: routes, envelopes, frozen vocabulary | Shipped |
| [TUI Contract](./tui-contract.md) | Read-only Rich terminal UI: navigation, lenses, projection semantics | Shipped |
| [Web UI Contract](./web-ui-contract.md) | Optional browser UI: startup, boundaries, relationship to other surfaces | Shipped |

---

## Contract Relationships

```
DAEMON_CONTRACT ─── hosts ───→ LOCAL_API_CONTRACT
                                    ↑
WEB_UI_CONTRACT ─── consumes ───────┤
                                    │
TUI_CONTRACT ─── independent ───────┘  (uses storage directly, not API)
```

---

## How to Use

1. **Before modifying a subsystem**: Read its contract to understand the shipped boundaries
2. **When adding new behavior**: Update the contract first, then implement
3. **Contract fixtures**: Frozen vocabulary fixtures live in `tests/fixtures/contracts/`

---

**Language**: English
