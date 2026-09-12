# M2 slice 1 executable contract — exogenous disturbances

Authority: this file narrows `prd.md` to exact schemas and behavior. Where it contradicts an older
document, this file wins for `backend/`, `web/` and `scripts/check-lab-browser.py` until the next
approved slice. Everything M1 established that is not mentioned here stays as-is.

## 1. Model changes (`backend/tianji_lab/models.py`)

```python
DisturbanceKind = Literal["demand_spike", "supplier_loss"]

class Disturbance(Model):          # extra=forbid, strict, frozen
    tick: int = Field(ge=1, le=10)
    kind: DisturbanceKind
    amount: int = Field(ge=1, le=200)
```

`Scenario` gains:

```python
disturbances: list[Disturbance] = Field(default_factory=list, max_length=10)
```

`Scenario` gains a `model_validator(mode="after")` requiring:

- every `disturbance.tick <= horizon` (a disturbance after the horizon is dead input and is rejected,
  not silently ignored);
- no duplicate `(tick, kind)` pair, so an operator mistake cannot silently accumulate;
- `demand_spike.amount <= 20` and `supplier_loss.amount <= 200`.

`State` gains `lost: int = Field(default=0, ge=0, le=400)`, the explicit loss account. It is part of
canonical state hashing like every other field.

`Scenario.description` default text is updated to mention the optional exogenous schedule; it must no
longer claim "rules-v1 ordering" as the only content of the model.

Rule version:

```python
RULE_VERSION_V1 = "supply-chain.v1"          # M1 semantics, no schedule
RULE_VERSION_V2 = "supply-chain.v2"          # semantics extended with the schedule
RuleVersion = Literal["supply-chain.v1", "supply-chain.v2"]
def rule_version_for(spec: Scenario) -> RuleVersion:  # in kernel.py
    return RULE_VERSION_V2 if spec.disturbances else RULE_VERSION_V1
```

The label is **derived from the specification**, never claimed by a caller: an empty schedule is
exactly M1 semantics, a non-empty schedule is v2 semantics. `Trajectory.rule_version` and
`SearchResult.rule_version` are the derived value and are passed explicitly at construction.
`service.Provenance.rule_version` accepts both labels and is set from the frozen spec.

## 2. Transition semantics (`backend/tianji_lab/kernel.py`)

`step(scenario, state, action)` keeps the M1 order and inserts exogenous events at one exact point:

1. the actor's action executes (order purchases a shipment, consumes cash, consumes supplier stock,
   or waits);
2. the round advances to `tick = state.tick + 1`; shipments due at `tick` arrive and are added to
   inventory;
3. **exogenous disturbances declared at `tick` apply**;
4. demand for `tick` is served; unmet demand accumulates into `shortage`.

A disturbance declared at tick `1` therefore applies in the first turn. Disturbance application, in
declaration order, for the applied tick:

- `demand_spike(amount)`: effective demand for that tick is `scenario.demand_per_tick + amount`.
  Nothing is clamped: declared demand is always fully demanded.
- `supplier_loss(amount)`: `actual = min(amount, supplier_stock)`; `supplier_stock -= actual` and
  `lost += actual`. A declared loss larger than the remaining stock destroys only the remaining
  stock, and the shortfall is **not** carried to later ticks. The event text states both numbers.

Because the actor's own order executes before the shock lands, buying ahead of a declared disruption
moves goods out of supplier custody into an in-transit shipment and thereby protects them. That is
intended planning pressure, not a loophole: the schedule is operator-visible and frozen, so the
goal search can and must plan around it. A loss never carries forward and never destroys goods that
have already arrived.

Event strings, appended in this order and readable by the browser and the MCP client:

```text
<action event>                                # from step 1
received <n> at tick <t>                      # only when arrivals happened
disturbance demand_spike at tick <t>: demand 4 -> 7
disturbance supplier_loss at tick <t>: declared 10, lost 4, stock 40 -> 36
demand <effective> [base <base> + spikes <extra>]: delivered <n>; shortage <n>
```

The demand event keeps the plain `demand <n>: delivered <n>; shortage <n>` form whenever the tick has
no spike, so existing operator habits and M1 event expectations still hold.

Executable invariants in `_check_state` (all must hold exactly, integers only):

- goods: `inventory + delivered + supplier_stock + shipments + lost == initial_inventory + supplier_stock`;
- cash: `cash + spent == initial_cash` (unchanged);
- `lost <= scenario.supplier_stock`;
- demand: `delivered + shortage == cumulative_demand(scenario, tick)` where
  `cumulative_demand(scenario, tick) = tick * demand_per_tick + sum(amount for demand_spike with d.tick <= tick)`;
- a specification with an empty schedule must satisfy `lost == 0` — a v1-labelled trajectory cannot
  invent losses;
- all M1 per-shipment, purchase and spend checks stay unchanged.

`_state_key` includes `lost`, so search deduplication never merges states that differ in losses.
`search`, `simulate`, `validate_trajectory`, `observe` and `_goal_met` need no other change: goal
plans are still re-verified by replaying the same forward model, now including the schedule.
`observe` keeps the M1 projections (director sees everything; retailer excludes `supplier_stock`;
supplier allowlist is `tick`, `supplier_stock`, `shipments`).

## 3. Service, HTTP and MCP

- No new operations. `scenario_create`/`scenario_update` validate the schedule through `Scenario`, so
  `/api/capabilities` and MCP `tools/list` publish it automatically.
- Scenario revisions keep freezing the schedule per branch/job; `branch_compare` still requires equal
  frozen specs, so two branches built from different schedules cannot be compared as if identical.
- `branch_export`/`branch_import` keep `schema_version = "tianji.lab.bundle.v1"`. The digest stays the
  canonical JSON of the supplied `branch` object, so a bundle exported before this slice (no
  `disturbances`, no `lost` keys) still verifies and imports; it replays under v1 semantics.
- Import/verification rejects a bundle whose declared `rule_version` disagrees with the frozen
  specification (for example a v1 label over a non-empty schedule). This is enforced by the existing
  `_verify_branch` replay-equality check plus an explicit `rule_version_for(spec)` comparison; do not
  add a tolerant fallback that rewrites the label.
- Job payloads carry the spec, so a disturbance-aware search runs in the spawned compute process
  exactly like an M1 search. Wall-clock and node budgets are unchanged.

## 4. Browser workbench (`web/`)

`web/src/api.ts`: `Scenario` gains `disturbances: Disturbance[]`, `State` gains `lost`, `Trajectory`
and `SearchResult` keep `rule_version` as `string`.

Scenario editor (`web/src/App.tsx`) gains a bounded "外生扰动" editor bound to the real capability
schema, with these test ids:

- `disturbance-add` — append one disturbance;
- `disturbance-tick-<i>`, `disturbance-kind-<i>`, `disturbance-amount-<i>` — row inputs, tick bounded
  by the current horizon, kind limited to `demand_spike | supplier_loss`;
- `disturbance-remove-<i>` — remove the row;
- `disturbance-count` — the number of configured disturbances as text.

Labels: `demand_spike` = 需求激增, `supplier_loss` = 供应损失. An empty list must be shown as an
explicit empty state ("无外生扰动"), never as hidden state. An invalid row (tick beyond the horizon or
amount out of range) must be surfaced as an actionable error before submission; the server remains
the authority and its validation error is displayed if it still rejects.

Timeline: the trace chart marks ticks that carry a disturbance (vertical marker plus a legend entry
"外生扰动"), driven by the real `spec.disturbances`, not by guessed state. `lost` is displayed with
the other state fields when a branch has any. Event log rendering needs no change: disturbance events
arrive as real event strings.

No fabricated schedule, no mock data, no client-side replay of the model.

## 5. Tests this slice must add

`backend/tests/test_kernel.py`:

- a demand spike at tick `t` raises that tick's delivered+shortage by exactly `amount` and leaves
  cumulative demand accounting exact at every tick;
- `supplier_loss` moves goods into `lost`, clamps at the remaining stock, and never carries the
  shortfall forward;
- disturbance application happens between arrivals and demand service: the same turn's purchase
  precedes the loss (so buying ahead protects the goods), arrivals at `t` land before the loss, the
  loss event precedes the demand event of the same frame, and the loss never carries forward;
- conservation and cash invariants hold across schedules with both kinds, including a schedule that
  loses the whole supplier stock;
- duplicate `(tick, kind)`, `tick > horizon`, and out-of-range amounts are rejected at validation;
- a schedule-aware goal plan is found and forward-verified; a plan that is only feasible if the
  schedule is ignored is never returned;
- replay determinism: identical spec + actions produce identical frames and hashes;
- `rule_version_for` derivation and `validate_trajectory` rejection when hashes/frames are tampered.

`backend/tests/test_import_metadata.py` (or the import test module): a pre-disturbance
(schedule-free) bundle round-trips, and a bundle whose spec has a schedule but whose declared rule
version is v1 is rejected.

`backend/tests/test_service.py`: `scenario_update` with a schedule bumps the revision and a frozen
branch keeps its old schedule; a forward job on a scheduled scenario reports the real disturbance
events; a backward job on a scheduled scenario returns v2 plans.

`scripts/check-lab-browser.py`: add real-browser checks that the editor creates a schedule, that
saving and running forward shows the disturbance events and a nonzero `lost` when a loss is
configured, that an out-of-horizon tick is rejected in the UI, and that the schedule survives export
plus re-import.

## 6. Documentation that must move with the code

- `docs/laboratory.md`: model semantics section (order of exogenous events, the two kinds, clamping,
  the `lost` account, the derived rule version), the "no random disturbances / no seed" paragraph
  must be replaced by "disturbances are an explicit schedule; randomness is still absent", and the
  limitations list.
- `README.md`: the active-slice bullet list.
- `.trellis/spec/lab/execution-contract.md`: the rule-version derivation and the import compatibility
  rule.

## 7. Non-goals for this slice

No RNG/seed/draw log, no probability output, no multi-actor decision ownership or observation
barrier, no adjudication records, no model/LLM calls, no new operations, no changes to the legacy
Rust tree, `runs/*.sqlite3`, job queue bounds, wall-clock limit, or authorization model.
