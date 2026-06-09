# Quality Guidelines

> Code standards, testing requirements, and forbidden patterns for this project.

---

## Overview

TianJi is a **pure Rust project**. The Rust implementation under `src/` is the
product. All milestones (M1A–M4, Crucix Delta, M3.5 housekeeping, Phase 6 cleanup)
are complete. The Python oracle was retired in Phase 6 (v0.2.0) after all parity
gates passed.

---

## Rust Technology Stack

| Concern | Choice | Constraint |
|---------|--------|------------|
| **Language** | Rust 2021 edition | `Cargo.toml`-based |
| **CLI framework** | `clap` (derive) | Phase 1 (replacing manual arg parse) |
| **XML parsing** | `roxmltree` | Feed parsing (Cangjie) |
### Rust Dependencies (Current)

Only dependencies needed for implemented milestones:

```toml
regex = "1.12"
roxmltree = "0.21"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
serde_yaml = "0.9"
sha2 = "0.11"
hmac = "0.13"
rusqlite = { version = "0.39", features = ["bundled"] }
clap = { version = "4.6", features = ["derive"] }
clap_complete = "4"
tokio = { version = "1", features = ["full"] }
axum = "0.8"
uuid = { version = "1", features = ["v4"] }
reqwest = { version = "0.13", default-features = false, features = ["rustls", "blocking"] }
libc = "0.2"
ratatui = "0.30"
crossterm = "0.28"
chrono = { version = "0.4", features = ["serde"] }
anyhow = "1"
thiserror = "2"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
blake3 = "1"
petgraph = { version = "0.7", features = ["serde-1"] }
```

### Rust Dependencies (Planned, per `plan.md` §11)

Add only when the milestone requires them:

- Milestone 2: `rusqlite` (SQLite persistence), `clap` (CLI subcommands) — **shipped**
- Milestone 3: `tokio` (async runtime), `axum` (HTTP API), `reqwest` (reverse proxy), `uuid` (job IDs), `libc` (setsid) — **shipped**
- Milestone 4: `ratatui`, `crossterm` (TUI) — **shipped**
- Phase 6: `clap_complete` (shell completions) — **shipped**
- Phase 2+: `blake3`, `petgraph`, `chrono` (worldline, field DAG) — **shipped**
- LLM providers use the shipped `reqwest`-based client/registry; no `async-openai` or `ollama-rs` dependency is present.

---

## Rust Testing Requirements

### Framework

**`cargo test` is the canonical test framework.** Verification commands:

```bash
cargo test
cargo fmt --check
cargo clippy -- -D warnings
```

### Test Structure

| Convention | Pattern |
|------------|---------|
| **Unit tests** | `#[cfg(test)] mod tests` inside each module |
| **Integration tests** | Tests in `src/lib.rs` exercising full pipeline |
| **Fixture path** | `tests/fixtures/sample_feed.xml` |
| **Contract fixture** | `tests/fixtures/contracts/run_artifact_v1.json` |

### Test Coverage Expectations

- Pipeline integration: every stage exercised end-to-end
- Scoring: deterministic numeric assertions on known inputs (exact-value + factor isolation)
- Grouping: event group structure and causal ordering
- Backtracking: intervention candidate generation
- Contract: top-level and nested artifact keys match expected schema
- Hash parity: canonical hashes are deterministic SHA-256

### Python Oracle Verification

The Python oracle was retired in Phase 6 (v0.2.0) after all parity gates passed.
Python code is no longer present in the repository.

---

## Rust Code Standards

### Structs for Data

All structured data uses typed Rust structs:

```rust
// src/models.rs — all model types
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct NormalizedEvent {
    pub event_id: String,
    pub source: String,
    pub title: String,
    ...
}

#[derive(Debug, Serialize)]
pub struct RunArtifact {
    pub schema_version: String,
    pub mode: String,
    ...
}
```

### JSON Serialization

Use `serde_json::to_string_pretty()` for artifact output:

```rust
pub fn artifact_json(artifact: &RunArtifact) -> Result<String, TianJiError> {
    Ok(serde_json::to_string_pretty(artifact)?)
}
```

### Error Handling

Use the `TianJiError` enum with `Result<T, TianJiError>` returns:

```rust
#[derive(Debug)]
pub enum TianJiError {
    Usage(String),
    Input(String),
    Io(std::io::Error),
    Json(serde_json::Error),
}
```

See `error-handling.md` for full details.

### Naming

| Element | Convention | Example |
|---------|------------|---------|
| Modules | `snake_case.rs` | `scoring.rs`, `backtrack.rs` |
| Structs | `PascalCase` | `RunArtifact`, `ScoredEvent` |
| Functions | `snake_case` | `run_fixture_path`, `normalize_item` |
| Constants | `UPPER_SNAKE` | `ATOM_NS`, `FIELD_KEYWORDS` |
| Private helpers | `snake_case` (module-local) | `clean_text`, `sha256_hex` |

### Spec Document Naming

Specification documents under `.trellis/spec/` use **lowercase kebab-case** filenames.

### Determinism and Hot-Path Helpers

- State-affecting collections must use deterministic ordering (`BTreeMap`, sorted `Vec`, or explicit sorting) rather than relying on `HashMap` iteration order. This applies to pipeline grouping, backtracking candidate selection, daemon job registries, and any future worldline state.
- Regexes used inside per-item, per-event, per-keyword, or timestamp parse paths must be compiled once with `std::sync::LazyLock<regex::Regex>` or an equivalent module-local cache. Do not call `Regex::new(...)` inside loops or frequently called helpers unless the pattern is truly dynamic.

```rust
use regex::Regex;
use std::sync::LazyLock;

static TOKEN_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[a-z0-9][a-z0-9-]{2,}").unwrap());

fn extract_tokens(text: &str) -> Vec<&str> {
    TOKEN_RE.find_iter(text).map(|m| m.as_str()).collect()
}
```

#### Wrong

```rust
fn extract_tokens(text: &str) -> Vec<&str> {
    let token_re = Regex::new(r"[a-z0-9][a-z0-9-]{2,}").unwrap();
    token_re.find_iter(text).map(|m| m.as_str()).collect()
}
```

#### Correct

```rust
static TOKEN_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[a-z0-9][a-z0-9-]{2,}").unwrap());

fn extract_tokens(text: &str) -> Vec<&str> {
    TOKEN_RE.find_iter(text).map(|m| m.as_str()).collect()
}
```

---

## File Size Guidelines

- If a Rust module exceeds ~500 lines, consider splitting into submodules
- If a module exceeds ~800 lines, it should definitely be split
- Test modules within `src/` can be larger due to many test cases

---

## Forbidden Patterns

| Pattern | Why |
|---------|-----|
| **Adding dependencies before the milestone that needs them** | Each milestone adds only what it uses |
| **Async runtimes before Phase 2+** | No `tokio` until daemon/simulation needs it |
| **Web frameworks before Milestone 5** | No `axum` until daemon/API milestone |
| **TUI crates before Milestone 4** | No `ratatui` until TUI milestone |
| **LLM crates before Phase 3+** | No `async-openai`/`ollama-rs` until simulation |
| **Tests depending on public network** | All tests use local fixtures |
| **Asserting against incidental formatting** | Assert on artifact semantics, not whitespace |
| **Bypassing CLI input rules** | No run without `--fixture` plus at least one resolved source |

---

## Anti-Patterns to Avoid

- **Don't design for daemon/IPC/web UI before one-shot flow is correct** — CLI first
- **Don't replace deterministic logic with opaque model-driven behavior** — deterministic first
- **Don't add cloud-required dependencies** — local-only MVP

## Common Mistakes

### Converting `TianJiError` to `String` mid-chain (error variant loss)

**Symptom**: Structured error information (`Usage`/`Input`/`Io`/`Json`/`Storage` variants)
is lost when an error is converted to a plain `String` via `format!("TianJiError: {e}")`
or `.to_string()` before being propagated.

**Cause**: Rust's `?` operator automatically converts errors via `From` impls, preserving
the full type chain. Manually converting to `String` breaks this chain — downstream code
cannot match on the variant or extract structured info.

**Fix**: Always propagate `TianJiError` directly via `?`. If a boundary (like job storage)
requires a string, convert only at the final storage point — not in the intermediate layers.

#### Wrong

```rust
fn run_pipeline_for_job(request: &RunJobRequest) -> Result<(), String> {
    run_fixture_path(fixture_path, sqlite_path)
        .map_err(|e| format!("TianJiError: {e}"))?;  // variant lost
    Ok(())
}
```

#### Correct

```rust
fn run_pipeline_for_job(request: &RunJobRequest) -> Result<(), TianJiError> {
    run_fixture_path(fixture_path, sqlite_path)?;  // variant preserved
    Ok(())
}
```

### Discarding daemon child stdout/stderr (`Stdio::null()`)

**Symptom**: Daemon child process crashes or panics, but no output is captured — making
post-mortem debugging impossible.

**Cause**: Using `Stdio::null()` for child stdout/stderr silently discards all output.

**Fix**: Redirect child stdout/stderr to a log file (e.g., `<socket-path>.log`) using
`Stdio::from(File)`. This captures diagnostic output while still detaching from the
parent's terminal.

#### Wrong

```rust
.stdout(std::process::Stdio::null())
.stderr(std::process::Stdio::null())
```

#### Correct

```rust
let log_path = format!("{socket_path}.log");
let log_file = std::fs::File::create(&log_path)?;
let log_file_err = log_file.try_clone()?;
.stdout(Stdio::from(log_file))
.stderr(Stdio::from(log_file_err))
```

### Duplicating utility functions across modules

**Symptom**: Helper functions like `round2`, `days_since_epoch` are copy-pasted into
multiple modules with minor inconsistencies (`.unwrap()` vs `.expect()`).

**Cause**: Avoiding a shared utility module because the functions "feel too small to
extract." Over time this creates maintenance burden — any bug fix or behavior change
must be applied in multiple places.

**Fix**: Extract shared helpers to `src/utils.rs` as `pub fn`. Import from `crate::utils`.
Standardize on `.expect()` for consistency.

### Over-broad shared parsers after utility extraction

**Symptom**: A shared parser accepts inputs that one caller previously rejected, such as
accepting timestamp strings with trailing junk or non-UTC offsets after centralizing time
parsing.

**Cause**: Utility extraction reuses a permissive helper for multiple call sites that had
different boundary contracts. Prefix parsers are useful for loose feed parsing, but storage
or delta-memory paths may require full-string validation.

**Fix**: Preserve caller-specific strictness with separate public helpers when needed.
For timestamp utilities, provide strict entry points for persisted state or alert decay,
and cover both accepted and rejected formats in unit tests.

#### Wrong

```rust
pub fn parse_delta_timestamp_seconds(value: &str) -> Option<i64> {
    parse_iso_timestamp_seconds(value).or_else(|| value.parse().ok())
}
```

#### Correct

```rust
pub fn parse_delta_timestamp_seconds(value: &str) -> Option<i64> {
    parse_strict_utc_rfc3339_seconds(value).or_else(|| value.parse().ok())
}
```

### Hardcoding `include_str!` paths to external directories

**Symptom**: Rust build breaks if an external directory is absent or reorganized.

**Cause**: `include_str!` pointing outside the Rust crate's owned directories.

**Fix**: Keep static assets in Rust-owned directories (e.g., `src/webui/`).

#### Wrong

```rust
const INDEX_HTML: &str = include_str!("../tianji/webui/index.html");
```

#### Correct

```rust
const INDEX_HTML: &str = include_str!("webui/index.html");
```

### Using stringly-typed enums instead of real Rust enums

**Symptom**: Code compares strings like `== " headline role=chain endpoint;"` instead of
using enum variants. Fragile — typos or vocabulary changes silently fall through to wrong defaults.

**Cause**: Quick prototyping with stringly-typed values that never got refactored to proper enums.

**Fix**: Replace string comparisons with a proper `enum` + `Display` impl. The `Display` impl
preserves the original text for artifact output parity, while the enum enforces correctness
at compile time.

#### Wrong

```rust
if headline_role_text == " headline role=chain endpoint;" { ... }
```

#### Correct

```rust
match headline_role {
    HeadlineRole::ChainEndpoint => { ... }
}
// Display impl preserves the text for artifact output:
impl Display for HeadlineRole {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match self {
            HeadlineRole::ChainEndpoint => write!(f, " headline role=chain endpoint;"),
            ...
        }
    }
}
```

### Dropping `std::process::Child` without reaping (zombie process leak)

**Symptom**: After spawning a daemon child process with `Command::spawn()`, the parent
CLI exits and the child becomes a zombie (visible in `ps` as `Z` state) until the
parent process exits.

**Cause**: In Rust, dropping a `Child` handle does **not** call `wait()` on the OS
process. The OS keeps the zombie entry until someone reaps it. Error paths often
correctly call `child.wait()`, but the success path (where the child should keep
running) is easily missed.

**Fix**: For daemon-style child processes that must outlive the parent, call
`std::mem::forget(child)` after confirming the child started successfully. This
intentionally leaks the handle — the OS reaps the child when it eventually exits.
Do **not** call `child.wait()` on the success path (it blocks until the daemon exits,
defeating the purpose of spawning a background process).

#### Wrong

```rust
let mut child = cmd.spawn()?;
let pid = child.id();
// ... readiness checks pass ...
// child dropped here → zombie process
Ok(success_payload)
```

#### Correct

```rust
let mut child = cmd.spawn()?;
let pid = child.id();
// ... readiness checks pass ...
// Deliberately leak the handle: the daemon child must outlive
// this parent CLI process. std::mem::forget prevents the Drop
// impl from running, and the OS will reap the child when it exits.
std::mem::forget(child);
Ok(success_payload)
```

---

## Pre-Commit Checklist

Before committing any Rust change:

- [ ] `cargo test` passes
- [ ] `cargo fmt --check` passes
- [ ] `cargo clippy -- -D warnings` passes
- [ ] New code follows existing patterns (look at neighboring modules)
- [ ] No new dependencies in `Cargo.toml` without milestone justification
- [ ] Tests don't depend on public network

---

**Language**: English
