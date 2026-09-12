# Bugfix: Post-Review v0.2.1 (2026-05-17)

Source: `.trellis/reviews/2026-05-17-code-review.md` (file removed in the 2026-09 documentation cleanup; Git history retains it)
Scope: 15 critical + 10 high bugs across all subsystems

---

## Section A — Storage (C4, C5, C6, H1, H2)

### A1. C5: Enable WAL mode
File: `src/storage.rs:43-44`
In `persist_run`, after `PRAGMA foreign_keys=ON`, add:
```rust
connection.execute_batch("PRAGMA journal_mode=WAL")?;
```

### A2. C4: Fix insert_raw_items / insert_normalized_events hash mismatch
File: `src/storage.rs:132-133, 161-164`
`insert_raw_items` uses `item.entry_identity_hash.clone()` directly but 
`ensure_canonical_source_items` derives hashes when they're empty. The key
lookup fails when hash fields are empty string.

Fix: Extract a helper function that replicates the derivation logic:
```rust
fn derive_hashes(raw_item: &RawItem) -> (String, String) {
    let identity = if raw_item.entry_identity_hash.is_empty() {
        derive_canonical_entry_identity_hash(raw_item)
    } else {
        raw_item.entry_identity_hash.clone()
    };
    let content = if raw_item.content_hash.is_empty() {
        derive_canonical_content_hash(raw_item)
    } else {
        raw_item.content_hash.clone()
    };
    (identity, content)
}
```
Use this helper in both `ensure_canonical_source_items` (to deduplicate) 
and `insert_raw_items`/`insert_normalized_events` (to construct lookup key).
For NormalizedEvent, create an analogous helper.

### A3. C6: Remove user-controlled sqlite_path from delta endpoint
File: `src/api.rs:340`
In `get_latest_delta`, remove `params.sqlite_path.unwrap_or(state.sqlite_path)`
and always use `state.sqlite_path`. Remove `sqlite_path` field from 
`DeltaLatestQuery` struct (line ~127).

### A4. H1: Map TianJiError to proper HTTP status codes
File: `src/api.rs:159-161` (and 4 other locations)
Create `fn map_tianji_error(e: TianJiError) -> ApiError`:
- `TianJiError::Usage` | `TianJiError::Input` → 400 Bad Request
- `TianJiError::Io(NotFound)` → 404
- `TianJiError::Storage(QueryReturnedNoRows)` → 404
- Everything else → 500 with generic "internal error" message (don't leak paths)

Replace all 5 `.map_err(|e| ApiError { status: 500, body: ... })` sites 
with the mapper.

### A5. H2: Wrap save_baseline DELETE+INSERT in transaction
File: `src/storage.rs:1646-1650`
Wrap the DELETE followed by INSERT in `conn.transaction()?` or use 
`INSERT OR REPLACE` (requires UNIQUE constraint on baselines table).

---

## Section B — Core Pipeline (C1, C2, C3, H9, H10)

### B1. C3: Fix round2 NaN/Inf panic
File: `src/utils.rs:8-10`
Change:
```rust
pub fn round2(value: f64) -> f64 {
    if !value.is_finite() { return value; }
    format!("{:.2}", value)
        .parse::<f64>()
        .unwrap_or(value)
}
```

### B2. C2: Add divide-by-zero guard to average()
File: `src/delta.rs:475-477`
```rust
fn average(values: &[f64]) -> f64 {
    if values.is_empty() { return 0.0; }
    values.iter().sum::<f64>() / values.len() as f64
}
```

### B3. C1: Fix RiskDirection semantic naming
File: `src/delta.rs:559-567`
Option A (recommended): Rename enum variants to Escalating/Deescalating
and update delta_memory.rs:299 usage accordingly.
Option B: Invert the mapping: `risk_up > risk_down` → RiskOn.

Also add doc comment explaining semantics.

### B4. H9: Add input size limits
File: `src/fetch.rs`, `src/normalize.rs`
Add `const MAX_RAW_ITEMS: usize = 500;` and truncate raw_items in 
`parse_feed` or pipeline entry point. Add `const MAX_SCORED_EVENTS: usize = 500;`
and enforce in `score_events`.

### B5. H10: Fix O(n²) dedup in extract_keywords
File: `src/normalize.rs:154-167`
Replace `Vec<String>` with `BTreeSet<String>` for `seen` to get O(log n) 
lookup. Or use `HashSet` if deterministic order isn't needed.

---

## Section C — LLM + Hongmeng (C9, C10, C11, C12, H3, H5, H6, H7)

### C1. C9: Reuse reqwest::Client
File: `src/llm/client.rs`
Add `client: reqwest::Client` field to `LlmClient` struct.
Construct in `LlmClient::new()` with:
```rust
client: reqwest::Client::builder()
    .connect_timeout(Duration::from_secs(60))
    .timeout(Duration::from_secs(120))
    .build()?
```
Replace `reqwest::Client::new()` calls in `chat_openai_compatible` (line 88)
and `chat_ollama` (line 148) with `self.client.clone()`.

### C2. H5: Already addressed by C9 (timeout config in Client builder)

### C3. C10: Guard against checkpoint_interval=0
File: `src/hongmeng/simulation.rs:192`, `src/hongmeng/config.rs`
In `Hongmeng::new` or `HongmengConfig` validation, assert/return error if
`checkpoint_interval == 0`. Or use `NonZeroU64` for the field type.

### C4. C11: Propagate LLM parse errors instead of swallowing
File: `src/hongmeng/agent.rs:253-274`
Change `parse_llm_action` to return `Result<AgentAction, LlmError>`.
On `serde_json::from_str` failure → `Err(LlmError::ChatFailed(...))`.
Update `pick_llm_action_with_fallback` to handle the new Result and 
fall through to stub action on parse failure.

### C5. C12: Serialize causal_graph (short-term fix)
File: `src/worldline/types.rs:63-64`
Short-term: remove `#[serde(skip)]` and implement manual Serialize/Deserialize
for `DiGraph<EventId, CausalRelation>` that saves as (nodes, edges) arrays.
Or: add a `reconstruct_causal_graph(&mut self)` method that rebuilds from events.

### C6. H3: Log checkpoint save errors
File: `src/hongmeng/simulation.rs:210`
Replace `let _ = checkpoint.save(conn);` with:
```rust
if let Err(e) = checkpoint.save(conn) {
    tracing::warn!("checkpoint save failed at tick {}: {e}", self.tick);
}
```
If tracing is not set up, use `eprintln!`.

### C7. H6: Implement prev_fields comparison in check_convergence
File: `src/hongmeng/convergence.rs:88`
Remove `let _ = prev_fields;` stub. Compare current worldline.fields with
prev_fields: if the difference across all fields is below epsilon AND the
current delta is also below epsilon, return FieldStabilized. If prev_fields
is empty (first tick), only check delta.

### C8. H7: Guard choices[0] access
File: `src/llm/client.rs:115-117`
Before indexing `choices[0]`, check:
```rust
let choices = json["choices"].as_array()
    .ok_or_else(|| LlmError::ChatFailed("no choices in response".into()))?;
let choice = choices.first()
    .ok_or_else(|| LlmError::ChatFailed("empty choices array".into()))?;
```
Also check `finish_reason` is "stop" — if "content_filter" or "length", 
return appropriate error.

---

## Section D — Nuwa (C13, C14, C15)

### D1. C13: Fix branch divergence calculation
File: `src/nuwa/forward.rs:179`
```rust
final_divergence: alt_worldline.divergence + offset as f64 * 0.5,
```

### D2. C14: Update working_worldline.divergence in backward search
File: `src/nuwa/backward.rs:142`
After each field update cycle (where `working_worldline.fields` changes),
call:
```rust
working_worldline.divergence = 
    worldline::baseline::compute_divergence(&base_worldline.fields, &working_worldline.fields);
```
This should happen right before line 142 where `path_probability` is computed.

### D3. C15: Populate branches vector in interactive forward
File: `src/nuwa/forward.rs:407,517`
Add branch generation logic (similar to non-interactive `run_forward` 
at lines 132-181) inside the interactive loop. At minimum:
- Inside the tick loop, after agent actions, generate alternative scenarios
- Push `BranchSummary { index, worldline_id, probability, divergence }` 
  into `branches` vec
- Ensure `BranchSummary` has the fields needed by the prune interface

---

## Section E — TUI (C7, C8, H4)

### E1. C8: Handle terminal Resize events
File: `src/tui/mod.rs:402-405`
Add resize handling:
```rust
let event = event::read()?;
match event {
    Event::Key(key) => { ... }
    Event::Resize(cols, rows) => {
        terminal.resize(Rect::new(0, 0, cols, rows))?;
        continue;
    }
    _ => continue,
}
```

### E2. C7: Async data loading for detail/compare views
File: `src/tui/state.rs:459-500`, `src/tui/mod.rs`
Add `pending_load: Option<tokio::task::JoinHandle<LoadedData>>` to TuiState.
When user opens detail/compare, spawn `tokio::task::spawn_blocking` for the
SQLite query. In the main loop, check `pending_load.is_finished()` and apply
result. Display "Loading..." while pending.

Note: This requires adding tokio dependency (already present) and 
restructuring the synchronous `handle_key` to support async operations.
Minimum viable: move the query to spawn_blocking + oneshot, poll in main loop.

### E3. H4: Use bounded channel for simulation updates
File: `src/tui/mod.rs:90`
Replace `tokio::sync::mpsc::unbounded_channel()` with 
`tokio::sync::mpsc::channel(64)`.

---

## Verification

After all fixes:
1. `cargo build` — 0 errors
2. `cargo test` — all 28 tests pass + any new tests added
3. `cargo clippy -- -D warnings` — clean
4. `cargo fmt --check` — clean

## Non-goals (explicitly out of scope)
- H8 (serde_json::Value → strong types): deferred, requires architecture change
- TUI view state refactoring: deferred
- forward.rs code deduplication: deferred  
- Connection pooling: deferred
- Structured logging: deferred
- Deprecated function cleanup: low priority
