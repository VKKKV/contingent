# Development conventions

Python 3.12+ and strict TypeScript are the application stack. Read the
[execution contract](execution-contract.md) before cross-layer changes.

- Use bounded Pydantic schemas and canonical JSON; scenario input is data, never executable code.
- Keep the deterministic kernel free of I/O. Validate model proposals independently.
- Share the operation registry across Web, HTTP and MCP; do not create alternate write paths.
- Scope SQLite transactions to local state, not network calls. Preserve revision CAS, idempotent
  mutations, immutable recorded branches and explicit job errors.
- Invalidate stale browser requests when inputs, selection or connection changes. Supply-chain
  workspace state remains an API contract, not a browser view.
- Use ordinary pytest/Vitest, Ruff, build and real API/browser checks as needed. Report results
  directly; do not create permanent run reports, transcript dumps or screenshot archives.

Run commands from the root [README](../../README.md). Do not push, migrate or delete user databases
implicitly.