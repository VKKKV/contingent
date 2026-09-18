# M2 slice 2 — offline observation and independent adjudication

Status: implemented and verified offline on 2026-09-18; signed commit `ec985aa` merged into local
main after maintainer authorization. Separate [local smoke evidence](research/local-model-smoke.md)
does not change the production scope below.
This contract replaces the unfinished draft's consensus/conflict
proposal. The existing kernel has one action per turn, not simultaneous multiplayer transitions.
No provider, paid call, network actor, participant credential, or calibrated probability is added.

## Scope and authority

The local director can inspect a recorded branch tick through a retailer or supplier projection,
submit one structured proposal, and retain an independently checked adjudication preview. Multiple
actors can submit separate proposals for the same recorded tick; their records are not votes and
are never automatically merged. A proposal or accepted preview never changes the recorded branch.
The director can use the existing forward-verified fork operation to explore an action separately.

All HTTP/MCP clients still possess the full director credential. Actor IDs and the distinct referee
ID are audit labels, not authenticated people or proof of organizational independence. Do not give
the director token to an untrusted participant. The projection is a data-minimization boundary,
not deployed multiplayer authorization.

## Observation and proposal contract

- `ObservationContext` binds branch ID, frozen scenario revision, and canonical specification hash.
- `ObservationEnvelope` binds actor ID, participant role, tick, typed detached projection, projection
  hash and observation hash. Only retailer/supplier roles are accepted, not director.
- Retailer fields mirror `kernel.observe`: tick, inventory, cash, delivered, shortage, spent and
  shipments. Supplier fields are tick, supplier_stock and shipments. Shipments describe the model's
  single retailer/supplier relationship; there is no invented per-actor ownership ledger.
- Nested projections and shipments are immutable. Validation rejects foreign fields, invalid types,
  invalid bounds and inconsistent hashes/role/tick. JSON round trips preserve hashes.
- The envelope does not include an authoritative full-state hash or hidden-state values. Its hash
  binds the public envelope, not omitted private values. This is not cryptographic authenticity.
- Proposals bind actor ID, role, action, observation hash and explicit policy label. `FakeActor`
  remains a deterministic test double, not a production chatbot or exposed provider endpoint.

## Independent adjudication

The adjudicator receives the authoritative frozen spec/state/context independently of the proposal,
regenerates the projection, verifies identity and binding, then revalidates through `kernel.step`.
Retailers can propose `wait`, `order_standard` or `order_express`. Suppliers can only propose `wait`:
the present model has no supplier-side order command, so a supplier must not spend retailer cash.

A record contains context, actor/role, observation identity, requested action, referee label,
pre-state hash, accepted/rejected status, reason, post-state hash and deterministic record
hash. Rejected records bind the unchanged state with equal pre/post hashes. Illegal or stale
proposals are rejected without substituting an action. Malformed requests or
identity mismatches fail validation. Accepted previews return the actual next state from the kernel;
neither accepted nor rejected adjudication mutates its source state or branch.

## Persistence and shared operations

The following operations use the existing director authentication, strict input registry, HTTP/MCP
parity and transactional mutation request IDs. They are bounded synchronous local operations (one
recorded frame, one kernel step), not background agent jobs. There is no provider budget, timeout,
cancellation or fake failure stream to simulate. Future provider jobs must define those separately.

- `observation_create({branch_id, tick, actor_id, role})`: persist a generated envelope under a server
  ID, returning `{id, observation}`. Tick must be recorded; context comes from the immutable branch,
  never a caller-supplied revision or state. Repeated request ID returns the same record.
- `observation_get({id})`: return `{id, observation}` with no director state or unrelated records.
- `adjudication_create({observation_id, proposal, adjudicator_id})`: resolve the saved envelope and
  frozen source frame, adjudicate, persist and return `{id, observation_id, record, next_state}`.
  The next state and full adjudication are director-only audit data, not participant responses.
- `adjudication_get({id})`: read back that persisted result, validating its record hash, next-state
  hash and relational IDs. List uses the same validation; corrupt records fail closed. This detects
  inconsistency, not malicious rewriting of the entire database and all hashes.
- `adjudication_list({branch_id})`: return `{items: [...]}` in creation order for this branch only.
  At most 100 observations and 100 adjudications per branch; attempts beyond a cap fail with 409
  `record_limit`, without partial records or idempotency receipts. Reads stay bounded by these caps.

Editing the live scenario does not invalidate a record of a frozen branch. Importing a branch
creates a new identity and cannot reuse observations from the original branch. Fork observations
can reference only actual recorded continuation ticks. Branch bundle v1 remains unchanged and does
not export the separately stored audit records; no portability claim is made for these records.

## Browser workflow

A director panel beside the existing workbench uses the same operations: choose role and actor,
create a projection for the selected recorded tick, inspect it, propose an action, choose a distinct
referee label, and inspect the real saved accepted/rejected preview and history. No FakeActor is
called by the product. Branch/tick changes clear stale drafts/results; asynchronous responses cannot
install an observation or result into a different selected branch/tick. Busy/error/empty states and
the director-only/non-executing warning remain explicit.

## Acceptance

- Unit tests exercise immutability, strict validation, deterministic hashes, cross-actor/role/context
  rejection, stale projection, role permissions, horizon, rejection non-mutation and forward equality.
- Service tests exercise durable readback/restart, frozen revision, imported/fork identity, caps,
  idempotency/conflict, rollback and unchanged branch/jobs/workspace.
- HTTP and official MCP SDK tests exercise real operations and exact projection allowlists; all
  capability names/schemas remain shared. These tests do not imply per-user authorization.
- Frontend tests and real Chromium exercise actual projection/adjudication calls, history/readback,
  accepted and rejected previews, changed selection and the held stale branch response regression.
- Complete backend pytest/ruff, frontend test/format/build and real browser gates pass.
- Legacy Rust, profiles, Cargo files and existing `runs/*.sqlite3` remain unchanged. No commit/push
  and no baseline/sensitivity harness, preserving the user's current review boundary.

## Follow-up requiring a separate decision

A real provider/actor scheduler needs provider and cost approval. Authenticated participant identities,
supplier-specific actions and simultaneous multi-actor conflict rules need their own model/security
contract; changing those is not an invisible extension of this deterministic single-director slice.
Remote deployment, legacy migration and real-world integrations remain explicit confirmation gates.
