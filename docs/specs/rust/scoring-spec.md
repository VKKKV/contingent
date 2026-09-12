# TianJi Im / Fa Scoring Slice

## Purpose

This note defines the first first-party TianJi interpretation of `Im` and `Fa` for the deterministic one-shot pipeline.

It is intentionally narrower than the long-term Phase 2 goal. The purpose of this slice is to make TianJi's scoring language explicit without changing the pipeline shape, artifact schema, or ranking behavior in a broad way.

## Definitions

- **`Im` (Impact)**
  - TianJi's deterministic estimate of how strongly an event can move the current branch.
  - In the current slice, it is a bounded additive score built from:
     - actor weight
     - region weight
     - a bounded actor/region title-salience bonus for headline mentions
     - keyword density
     - a small dominant-field evidence bonus
     - a bounded dominant-field-specific impact-scaling bonus
     - a small thresholded field-diversity bonus for fields with meaningful scored support
     - a bounded text-signal-intensity bonus for dominant-field cue concentration across normalized text surfaces

- **`Fa` (Field Attraction)**
  - TianJi's deterministic estimate of how strongly an event belongs to its dominant attractor field.
  - In the current slice, it starts from the strongest normalized field score and then adds:
     - a small dominance-margin bonus over the second-best field
     - a small coherence bonus based on how much of the total scored field mass belongs to the dominant field
     - a small bounded near-tie ambiguity penalty when the top two fields are almost tied
     - a small bounded diffuse mixed-field penalty when a strong third field remains after the top-two margin is already clear
    - when no field has any positive scored mass, TianJi treats the event as `uncategorized` and returns `Fa = 0.0`
    - when multiple positive fields tie for the top score, TianJi picks one deterministically by canonical field-name order rather than dict insertion order

- **`divergence_score`**
  - TianJi's current ranking score derived from explicit `Im` and `Fa` intermediates.
  - The current formula remains a transparent bounded blend:
    - `divergence_score = 0.65 * Im + 1.35 * Fa`

## Rationale Transparency Contract

This scoring-spec update documents the shipped rationale output more explicitly. It does not revise the scoring formula.

Current rationale remains additive, explicit, transparent, inspectable, and bounded:

- `build_rationale()` in `src/scoring.rs` always starts with top-level `Im=<value>` and `Fa=<value>` entries
- the rationale then exposes the additive `Im` components with the exact shipped labels:
  - `im_base`
  - `im_actor_weight`
  - `im_region_weight`
  - `im_keyword_density`
  - `im_dominant_field_bonus`
  - `im_nonzero_field_bonus`
- the rationale also exposes additive `Im` components conditionally when those shipped terms are active:
  - `im_title_salience`, only when the bounded title-salience bonus is greater than zero
  - `im_field_impact_scaling`, only when the bounded dominant-field impact-scaling bonus is greater than zero
  - `im_text_signal_intensity`, whenever the selected dominant field has first-party field keyword vocabulary, including zero-valued cases for that shipped text-signal term
- when field-score mass exists, the rationale exposes the additive and subtractive `Fa` components with the exact shipped labels:
  - `fa_dominant_field_strength`
  - `fa_dominance_margin_bonus`
  - `fa_coherence_bonus`
  - `fa_near_tie_penalty`
  - `fa_diffuse_third_field_penalty`

This contract keeps score inspection aligned with shipped behavior. The rationale labels name the current additive `Im` and `Fa` terms directly so operators and tests can inspect how each bounded component contributed, without claiming any broader scoring-model revision.

## Why This Slice Is Small

This first scoring-focused Phase 2 change does **not**:

- alter the feed parsing or normalization stages
- add clustering or multi-event causal logic
- alter SQLite persistence shape
- add model-driven or cloud-based scoring

It only makes the existing deterministic scoring language explicit and testable in first-party TianJi terms.

## Current Actor / Region Title-Salience Expansion

The current Phase 2 scoring slice now also includes:

- **a bounded title-salience bonus inside `Im` for actor and region mentions already present in the normalized event**

Intent:

- reward events whose already-extracted actors or regions are important enough to
  appear directly in the headline rather than only in the body text
- deepen `Im` without changing the meaning of `Fa`
- preserve the current split where `Im` represents branch-moving force and `Fa`
  represents dominant-field alignment

Allowed inputs for this slice:

- normalized `title`
- normalized `actors`
- normalized `regions`
- existing actor and region pattern vocabulary already used during normalization

Disallowed inputs for this slice:

- any new stored title-only actor or region fields in the artifact or SQLite
- cross-event corroboration
- prior runs or baseline history

Constraints implemented in this slice:

- the bonus is additive inside `Im`
- the bonus only rewards actors and regions already matched by TianJi's existing
  normalization vocabulary; it does not introduce a second entity extractor
- title salience remains smaller than the base actor/region contribution so the
  headline can sharpen an existing signal without overpowering the event's
  broader normalized evidence
- `Fa` and the top-level artifact shape remain unchanged

Current implementation shape:

- TianJi re-checks the normalized `title` against the existing actor and region
  pattern maps from normalization
- actor title-salience adds a small bounded bonus per actor whose canonical label
  is both present in `event.actors` and matched in the title
- region title-salience adds a small bounded bonus per region whose canonical
  label is both present in `event.regions` and matched in the title
- the combined title-salience bonus is capped so headline mentions sharpen `Im`
  but do not outweigh the full actor + region base contribution

Recommended verification for this slice:

- paired synthetic-event tests where `field_scores`, keywords, body text, and
  extracted actor/region sets stay fixed
- moving a matched actor or region mention into the title should raise
  `impact_score`
- the same paired tests should leave `field_attraction` unchanged

## Current Dominant-Field Impact-Scaling Expansion

The current Phase 2 scoring slice now also includes:

- **a bounded dominant-field-specific impact-scaling bonus inside `Im`**

Intent:

- let TianJi distinguish equally structured events whose branch-moving force
  should differ slightly by dominant field even before any historical baseline
  exists
- keep the scoring model local and inspectable by deriving the adjustment from
  the same first-party field vocabulary TianJi already uses for normalization
- preserve the current split where `Im` remains branch-moving force and `Fa`
  remains field-alignment strength

Allowed inputs for this slice:

- the selected `dominant_field`
- the dominant field's current strength from `field_scores`
- first-party field keyword weights already defined in `src/normalize.rs`

Disallowed inputs for this slice:

- any external taxonomy or reference-repo runtime logic
- persistence history, novelty, or spike detection
- changes to the `divergence_score` blend itself

Constraints implemented in this slice:

- the adjustment stays additive inside `Im`
- the adjustment is field-specific but derived from first-party TianJi field
  vocabulary rather than hidden manual overrides at runtime
- the bonus remains smaller than the dominant-field base contribution so it
  refines impact rather than rewriting the ranking model
- `Fa` stays field-alignment-only for this slice

Current implementation shape:

- TianJi computes a small field-impact factor from the dominant field's keyword
  vocabulary profile in `src/normalize.rs`
- stronger dominant-field vocabularies contribute a modestly larger bounded bonus
  when the event's dominant-field strength is otherwise the same
- uncategorized events do not receive this bonus

Recommended verification for this slice:

- paired synthetic-event tests where actor, region, keyword-density, and
  dominant-field strength stay fixed while the dominant field changes
- a stronger-impact dominant field should score a modestly higher `impact_score`
  than a weaker-impact field with the same structural inputs
- `field_attraction` should continue to reflect only field-score shape, not this
  `Im`-side refinement

Later Phase 2 grouping work now adds lightweight evidence-chain metadata inside
`scenario_summary.event_groups` so grouped backtracking can cite corroborating
events. That additive nested-group metadata is separate from the scoring slice
defined here and does not change how `Im`, `Fa`, or top-level artifact versioning
work.

Current grouping work now also supports transitive causal clustering inside
`scenario_summary.event_groups`, adding admission-path `causal_ordered_event_ids`,
`causal_span_hours`, per-link relationship metadata, and `causal_summary`
without changing SQLite table shape.

## Shipped `Fa` Contract

The shipped `Fa` model is intentionally narrow and fully local to one normalized event.

Current rule set in `src/scoring.rs`:

- start from the dominant field strength
- add a bounded dominance-margin bonus over the second-best field
- add a bounded coherence bonus from dominant-field share of total positive field mass
- subtract a bounded near-tie penalty when the rounded top-two margin is below `1.0`
- subtract a bounded diffuse-third-field penalty only when the rounded top-two margin is already at least `1.0` and the third-best field is above `2.5`
- if total positive field mass is zero, return `Fa = 0.0` and keep the event `uncategorized`
- if multiple positive fields tie for the top score, keep the event categorized but resolve the dominant-field label deterministically by canonical field-name order

This is the whole shipped `Fa` rule set for the current branch. It is a bounded field-shape heuristic, not a broader contradiction, corroboration, grouping, persistence, or history model.

## Deferred Work

Still deferred after this slice:

- richer `Fa` from corroboration, contradiction, or other mixed-field reasoning beyond current top-two and third-field concentration checks
- richer `Im` from novelty, spike, or baseline-deviation signals
- any grouped or cross-event ambiguity logic
- any persistence-driven or history-driven scoring logic
- broader persisted analysis beyond top scored-event run-history queries

## Current Text-Signal-Intensity Expansion

The current Phase 2 scoring slice now includes:

- **add one bounded text-signal-intensity factor to `Im`**

Intent:

- improve TianJi's ability to distinguish weak textual evidence from strong
  branch-relevant textual evidence inside a single normalized event
- deepen `Im` without changing the meaning of `Fa`
- preserve the current split where `Im` represents branch-moving force and `Fa`
  represents dominant-field alignment

Allowed inputs for this slice:

- normalized `keywords`
- normalized `title`
- normalized `summary`
- existing `field_scores`

Disallowed inputs for this slice:

- prior runs or SQLite history
- grouped-event or cross-event corroboration
- model-driven inference
- any hidden heuristic that cannot be described as one bounded additive term

Constraints implemented in this slice:

- the new factor is a single additive `Im` subcomponent
- it rewards **field-evidence intensity**, not mere text length
- it is bounded so actor and region weighting remain more important than raw text repetition
- `Fa` and the `divergence_score` blend remain unchanged in this branch

Current implementation shape:

- the bonus is derived from boundary-aware dominant-field cue concentration across three normalized
  text surfaces:
  - extracted `keywords`
  - normalized `title`
  - normalized `summary`
- it is intentionally smaller than the combined actor+region contribution
- it is separate from the existing keyword-density bonus because it rewards
  dominant-field-specific cue concentration rather than raw token count
- title and summary cue checks are boundary-aware so short cues like `ai` do not
  receive incidental credit inside unrelated larger words

Recommended verification for this slice:

- paired synthetic-event tests where actor, region, and dominant-field structure
  remain fixed
- stronger dominant-field textual evidence should raise `impact_score`
- the same paired tests should leave `field_attraction` unchanged or nearly so
- one exact-value scoring test should remain pinned so the additive formula stays
  inspectable

Out of scope for this slice:

- novelty or baseline-deviation scoring
- contradiction-aware or corroboration-aware `Fa`
- persistence-schema changes
- grouped-analysis changes
- CLI/history surface expansion unrelated to score validation

## Current Near-Tie Fa Refinement

The current Phase 2 scoring slice now also includes:

- **a bounded near-tie ambiguity penalty inside `Fa`**

Intent:

- reduce `field_attraction` modestly when the dominant field barely leads the
  runner-up field
- keep `Fa` aligned with “belongs to one dominant attractor field” rather than
  rewarding almost-tied top-two distributions too generously
- preserve the existing split where `Fa` remains field-alignment-only and `Im`
  remains branch-moving force

Constraints implemented in this slice:

- dominant field strength remains the base of `Fa`
- the existing margin bonus and coherence bonus remain in place
- the new adjustment is a small bounded subtraction driven only by the margin
  between the top two fields
- in the current implementation, that bounded subtraction applies when the
  rounded top-two margin is below `1.0`
- broad contradiction/corroboration logic is still deferred

Current implementation shape:

- when the top-two field margin is comfortably clear, `Fa` behaves like the
  prior shipped formula
- when that margin becomes a near tie, `Fa` subtracts a small bounded ambiguity
  penalty
- the penalty is intentionally smaller than the dominant-field base and remains a
  surgical ambiguity adjustment rather than a formula rewrite

Recommended verification for this slice:

- paired synthetic-event tests where `Im` inputs stay fixed and only the top-two
  field spread changes
- a near-tie case such as `6.5 vs 6.4` should score lower `Fa` than a more
  clearly dominant case such as `6.5 vs 5.8`
- a clearly dominant case such as `6.5 vs 2.0` should remain stable

## Current Diffuse Mixed-Field Fa Refinement

The current Phase 2 scoring slice now also includes:

- **a bounded diffuse mixed-field penalty inside `Fa` when the top-two margin is already clear**

Intent:

- reduce `field_attraction` modestly for broadly split three-field cases that are
  not near ties but still retain unusually strong third-field support
- keep cleaner two-field structures from scoring too close to materially more
  diffuse mixed-field distributions with the same `Im`
- preserve the current split where `Fa` remains field-alignment-only and `Im`
  remains branch-moving force

Constraints implemented in this slice:

- the near-tie penalty remains the primary top-two ambiguity adjustment
- the new diffuse penalty only applies when the rounded top-two margin is already
  at least `1.0`
- in the current implementation, unusually strong third-field support means the
  rounded third-best field is above `2.5`
- the new diffuse penalty is driven by unusually strong third-field support, not
  by any persistence, history, or grouped context
- the penalty stays bounded and smaller than the dominant-field base

Current implementation shape:

- cleaner two-field cases with a clear dominant margin still behave like the
  prior shipped formula
- when a strong third field remains after the top-two margin is already clear,
  `Fa` subtracts a small bounded diffuse-support penalty
- this remains a surgical ambiguity adjustment rather than a broad contradiction
  model
- when all field scores are zero, TianJi does not infer a dominant field from
  dict order; it treats the event as `uncategorized` with `Fa = 0.0`
- when multiple positive fields share the exact top score, TianJi keeps the event
  categorized but resolves the dominant-field label deterministically by
  canonical field-name order so `Im` text-signal matching and rationale output do
  not depend on field-score dict insertion order

Recommended verification for this slice:

- paired synthetic-event tests where `Im` inputs stay fixed and the top-two
  margin remains clear
- a diffuse three-field case such as `6.5 / 4.9 / 4.8` should score lower `Fa`
  than a cleaner two-field case such as `6.5 / 4.9 / 0.2`

## Current Implementation Boundary

- `src/scoring.rs` owns the explicit `Im` and `Fa` computations for now.
- `impact_score` in the artifact corresponds to current TianJi `Im`.
- `field_attraction` in the artifact corresponds to current TianJi `Fa`.

## Next-Refinement Decision Gate

No additional `Fa` refinement should land next just because mixed-field cases exist in the abstract. The next refinement is allowed only if one still-unhandled mixed-field weakness is proven first with one canonical synthetic event pair that keeps `Im` inputs fixed and shows a meaningful `Fa` failure not already explained by the shipped near-tie rule or the shipped diffuse-third-field rule.

Task 5 completed that proof check for this branch and did not find a meaningful uncovered mixed-field weakness. Until a later branch proves otherwise, this spec treats the current `Fa` model as the shipped baseline and records that no new `Fa` rule landed here.

## Branch Guardrail

This branch is formula-focused. It must not change persistence, CLI behavior, artifact schema, grouped analysis, or any `Im` rule.

This preserves backward compatibility while making the Phase 2 vocabulary real inside first-party code.
