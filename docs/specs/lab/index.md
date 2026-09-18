# Development conventions

Python 3.12+ and strict TypeScript are the only application stack. Read the
[execution contract](execution-contract.md) before cross-layer changes.

- Use strict bounded Pydantic schemas and canonical JSON. No executable scenario input.
- Keep the deterministic kernel free of I/O. Model proposals go through independent validation.
- Share the operation registry between Web, HTTP and MCP; never add hidden alternate write paths.
- Scope SQLite transactions to local state operations, not network calls. Preserve revision CAS,
  mutation idempotency, immutable recorded branches and explicit job errors.
- Clear obsolete browser requests when identity, branch, tick or connection changes.
- Use normal pytest/Vitest regressions and real API/browser checks as needed. Report results
  directly, without permanent run reports, transcript dumps or screenshot archives.
- Keep current docs concise. Product records are distinct from development logging.

Run commands in the root README. Do not push, migrate or delete user databases implicitly.
