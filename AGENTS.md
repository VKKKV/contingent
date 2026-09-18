# TianJi development

The only development stack is Python/FastAPI/Pydantic/SQLite in `backend/` and
React/TypeScript/Vite in `web/`. Read `docs/laboratory.md` and
`docs/specs/lab/execution-contract.md` before changing model semantics or shared operations.

- The deterministic kernel is authoritative. Model output is a proposal, not a state update.
- Web, HTTP and MCP share validation. Never substitute fake product responses.
- Use normal tests and real behavior checks; report results directly. Do not add standalone
  evaluation runners, mandatory session reports, screenshot archives or prompt/response dumps.
- Document current behavior, not accumulated test totals or session histories.
- Preserve user databases in `runs/`, `.local-data/`, and `backend/.local-data/`.
- Use focused commits; do not push without authorization. Protect concurrent user edits.

Commands:

```bash
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npm --prefix web test
npm --prefix web run format:check
npm --prefix web run build
```
