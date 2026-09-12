# Error Handling

> Error types, handling strategies, and communication patterns for this project.

---

## Rust Error Model (Current)

The Rust implementation uses `Result<T, TianJiError>` with a custom error enum:

```rust
#[derive(Debug)]
pub enum TianJiError {
    Usage(String),   // CLI usage errors
    Input(String),   // Feed/input parse errors
    DataIntegrity(String),  // Internal invariant / consistency failures
    Storage(rusqlite::Error),  // SQLite errors (Milestone 2+)
    Io(std::io::Error),
    Json(serde_json::Error),
}
```

- Library functions return `Result<T, TianJiError>`
- `main()` maps errors to stderr + exit code 1
- No `unwrap()` in library code — propagate errors through `Result`
- `DataIntegrity` is for internal invariant failures where persisted or derived
  data is inconsistent; do not encode these as `Storage(rusqlite::Error)` unless
  the underlying failure actually came from SQLite
- `Storage` variant wraps `rusqlite::Error`; "not found" cases are matched via `rusqlite::Error::QueryReturnedNoRows` and converted to `Option<T>::None` at the call site
- Daemon worker catches broad `Exception` at the boundary (like Python oracle), stores formatted error string in `JobRecord.error`

### DataIntegrity vs Storage

Use `TianJiError::DataIntegrity(message)` when code detects a violated internal
contract, such as a missing canonical source item ID after the write path already
built the canonical ID map. These are not user-input errors and not SQLite API
errors; they should surface as internal failures at API/daemon boundaries.

#### Wrong

```rust
return Err(TianJiError::Storage(rusqlite::Error::InvalidParameterName(
    "missing canonical source item id".to_string(),
)));
```

#### Correct

```rust
return Err(TianJiError::DataIntegrity(
    "missing canonical source item id".to_string(),
));
```

---

> **Status: Historical / compatibility reference.** The current Rust model is above.
> The sections below preserve the retired Python oracle's error patterns for
> historical parity context only. They are **not** coding standards for new Rust code.

---

## Overview

TianJi uses **exceptions as the primary error mechanism** — no `Optional`/`Result`-style return values. Each architectural layer has its own error boundaries and re-raising strategy.

---

## Error Types

### Custom Exceptions

| Class | Base | Location | Purpose |
|-------|------|----------|---------|
| `TianJiInputError` | `ValueError` | `tianji/fetch.py:17-18` | Feed read/fetch failures: missing files, HTTP errors, parse errors |
| `ApiRouteError` | `Exception` | `tianji/api.py:171-174` | HTTP API routing errors with structured `ApiError` payload |

```python
# tianji/fetch.py:17-18
class TianJiInputError(ValueError):
    """Raised when source data cannot be read or parsed."""
```

```python
# tianji/api.py:171-174
@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    status: int

class ApiRouteError(Exception):
    def __init__(self, api_error: ApiError) -> None:
        super().__init__(api_error.message)
        self.api_error = api_error
```

### Library Exceptions Used Directly

| Exception | Where Used |
|-----------|------------|
| `click.UsageError` | CLI validation failures (`cli_history.py:*, cli_daemon.py:*, cli_validation.py:*`) |
| `click.BadParameter` | Parameter format errors (`cli_validation.py:26,31`) |
| `click.ClickException` | Generic click-layer error (caught in `cli.py:781`) |
| `RuntimeError` | Storage type guard failures (`storage_views.py`: 12 locations) |
| `ValueError` | Input validation in `cli_sources.py`, `daemon.py` factory methods |
| `SystemExit` | Graceful exit from `main()` (`cli.py:783,785`, `__main__.py:5`) |

---

## Error Handling Patterns

### Pattern 1: Specific Catch → Re-raise as Domain Error

Catch library-specific exceptions near the source and re-raise as a project-specific error:

```python
# tianji/fetch.py:24-28
try:
    return fixture_path.read_text(encoding="utf-8")
except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError) as error:
    raise TianJiInputError(f"Failed to read fixture file: {fixture_path}") from error
```

### Pattern 2: `click.UsageError` for User-Facing Validation

Report invalid user input via click's built-in error type:

```python
# tianji/cli_history.py:44-45
if limit < 0:
    raise click.UsageError("--limit must be zero or greater.")
```

```python
# tianji/cli_validation.py:25-27
if score_range:
    try:
        low, high = map(float, score_range.split(","))
    except ValueError:
        raise click.BadParameter("score-range must be 'LOW,HIGH', e.g. '0.5,2.0'")
```

### Pattern 3: `RuntimeError` for Defensive Type Guards

Type assertions on storage row data — not user errors, but defensive programming:

```python
# tianji/storage_views.py:122
run_id = row["id"]
if not isinstance(run_id, int | str):
    raise RuntimeError("Unexpected run id type in top scored event summary row")
```

### Pattern 4: `except Exception` at Daemon Boundaries

The daemon worker loop catches broad `Exception` to prevent crashes, storing the error string:

```python
# tianji/daemon.py:202-204
except Exception as exc:
    error_message = f"{exc.__class__.__name__}: {exc}"
    self.state.set_job_failed(record.job_id, error=error_message)
```

### Pattern 5: Structured JSON Error Envelopes

API and daemon responses wrap errors in JSON:

```python
# tianji/cli_daemon.py:229-234 — daemon IPC response
response = {
    "ok": False,
    "error": {"message": f"{exc.__class__.__name__}: {exc}"},
}
```

```python
# tianji/api.py:185-193 — HTTP API response
def _error_envelope(error: ApiError) -> dict[str, object]:
    return {
        "api_version": API_VERSION,
        "data": None,
        "error": {"code": error.code, "message": error.message},
    }
```

---

## Error Communication Strategy by Layer

| Layer | Error Mechanism | Consumer |
|-------|-----------------|----------|
| **Libraries** (fetch, normalize, scoring, backtrack) | Raise exceptions (`ValueError`, `TianJiInputError`, `RuntimeError`) | Pipeline, CLI, daemon |
| **CLI** | Catch `TianJiInputError` → re-raise as `click.UsageError`; catch `click.ClickException` → `sys.stderr` → `SystemExit` | Terminal user |
| **Daemon** | Catch `Exception` → store error string in `JobRecord.error`; API handler catches `Exception` → JSON error envelope | API client, web UI |
| **Storage** | `RuntimeError` for type mismatches; `ValueError` for invalid inputs | Caller (pipeline, CLI, daemon) |

---

## Error Display Pattern

The CLI entry point catches and formats errors for display:

```python
# tianji/cli.py:781-785
except click.ClickException as error:
    error.show(file=sys.stderr)
    raise SystemExit(1)
except SystemExit:
    raise
```

---

## Anti-Patterns

- **No silent error swallowing** — every `except` block either re-raises, logs, or stores the error
- **No bare `except:` clauses** — always catch specific exception types
- **No return-value error indicators** — use exceptions, not `(result, error)` tuples
- **No error types that leak implementation details** — use `TianJiInputError` instead of exposing `xml.etree.ElementTree.ParseError` to callers

---

## Common Mistakes

- Adding new exceptions without a clear consumer — every new exception type should be caught somewhere specific
- Catching too broadly in library code — let exceptions propagate to the layer that knows how to handle them
- Using `RuntimeError` when `ValueError` or a custom exception would be more descriptive

---

**Language**: English
