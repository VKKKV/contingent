# Logging Guidelines

> **Status: Current.** TianJi is a pure Rust binary. Runtime diagnostics use
> `tracing`; artifact/status data intended for operators goes to stdout as
> structured JSON or terminal UI state. Historical Python logging conventions are
> no longer standards for new code.

---

## Rust Logging Model

Current Rust conventions:

- use `tracing::{error, warn, info, debug, trace}` for diagnostic events;
- initialize formatting through `tracing_subscriber` and `RUST_LOG`;
- keep command result payloads on stdout;
- keep errors and diagnostics off stdout unless the command's explicit contract is a diagnostic command;
- do not print ad-hoc debug text from library code;
- avoid diagnostic output while the TUI owns the terminal screen.

## Output Channels

| Channel | Purpose |
|---------|---------|
| stdout | JSON artifacts, CLI command results, generated shell completions |
| stderr / tracing sink | warnings, errors, daemon/server diagnostics |
| TUI terminal screen | ratatui application state while `tianji tui` is running |
| SQLite/API state | persisted runs, daemon job state, and read API responses |

## CLI Output Rules

- `tianji run --fixture ...` emits one schema-versioned artifact to stdout.
- `history`, `history-show`, `history-compare`, daemon status, API-like command outputs, and dry-run outputs should remain machine-readable where already established.
- `doctor --json` emits a diagnostic JSON envelope without printing secret values.
- Generated completions are written to stdout so callers can redirect them.

## TUI Rules

- Do not print normal log lines while ratatui owns the terminal.
- Surface TUI loading/error state through widgets where possible.
- Use ASCII/Nerd Font fallback helpers instead of printing side-channel warnings.

## Daemon/API Rules

- Daemon worker failures should be captured in daemon job state and exposed through the stable status envelope.
- API errors use the local API response envelope with `api_version`, `data`, and `error`.
- Request/response diagnostics may use tracing, but should not change API payload shapes.

## Anti-Patterns

- Ad-hoc `println!`/`eprintln!` debug statements in library or daemon code.
- Logging secrets, webhook URLs, API keys, tokens, or raw signed-command secrets.
- Changing stdout from JSON to human text for commands consumed by tests or local API/web UI tooling.
- Emitting logs during TUI drawing that corrupt the terminal screen.
- Adding a separate runtime log file as the primary state source; persisted state belongs in SQLite and API envelopes.

## Historical Context

The retired Python oracle used `click.echo`, `print`, and framework exceptions.
Those examples may remain in archived docs for parity history, but new work should
follow the Rust rules above.
