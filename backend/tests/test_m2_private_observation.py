import hashlib
import json

import pytest
from pydantic import ValidationError

from tianji_lab import kernel
from tianji_lab.models import Scenario, Shipment, State
from tianji_lab.offline_adjudication import (
    ActionProposal,
    AdjudicationRecord,
    FakeActor,
    ObservationContext,
    ObservationEnvelope,
    RetailerProjection,
    SupplierProjection,
    adjudicate,
    observe_envelope,
)


def digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def context_for(spec, **updates):
    return ObservationContext(
        **{
            "branch_id": "branch-1",
            "scenario_revision": 1,
            "spec_hash": digest(spec.model_dump(mode="json")),
            **updates,
        }
    )


@pytest.fixture
def case():
    spec = Scenario(name="offline slice", initial_inventory=3)
    state = kernel.initial_state(spec)
    context = context_for(spec)
    envelope = observe_envelope(state, "retailer-1", "retailer", context=context)
    proposal = FakeActor("retailer-1", "retailer").propose(envelope)
    return spec, state, context, envelope, proposal


def judge(case, **updates):
    spec, state, context, observation, proposal = case
    return adjudicate(
        **{
            "scenario": spec,
            "state": state,
            "observation": observation,
            "proposal": proposal,
            "context": context,
            "adjudicator_id": "referee-1",
            "record_id": "record-1",
            **updates,
        }
    )


def rehash_observation(payload):
    payload["projection_hash"] = digest(payload["projection"])
    payload["observation_hash"] = digest(
        {key: value for key, value in payload.items() if key != "observation_hash"}
    )
    return ObservationEnvelope.model_validate(payload)


def assert_rejected(case, **updates):
    record, result = judge(case, **updates)
    state = updates.get("state", case[1])
    assert record.status == "rejected"
    assert record.pre_state_hash == record.post_state_hash == kernel.state_hash(state)
    assert result == state
    assert result is not state
    assert result.shipments is not state.shipments
    assert record.record_hash == digest(record.model_dump(mode="json", exclude={"record_hash"}))
    return record, result


def test_role_observations_are_bounded_detached_deeply_immutable_and_hashed(case):
    spec, initial, context, _, _ = case
    state = kernel.step(spec, initial, "order_standard").state
    retailer = observe_envelope(state, "retailer-1", "retailer", context=context)
    supplier = observe_envelope(state, "supplier-1", "supplier", context=context)
    assert isinstance(retailer.projection, RetailerProjection)
    assert isinstance(supplier.projection, SupplierProjection)
    assert set(retailer.projection.model_dump()) == {
        "tick",
        "inventory",
        "cash",
        "delivered",
        "shortage",
        "spent",
        "shipments",
    }
    assert set(supplier.projection.model_dump()) == {"tick", "supplier_stock", "shipments"}
    assert retailer.projection.inventory == state.inventory
    assert supplier.projection.supplier_stock == state.supplier_stock
    for envelope in (retailer, supplier):
        assert isinstance(envelope.projection.shipments, tuple)
        assert envelope.projection.shipments[0] is not state.shipments[0]
        with pytest.raises(ValidationError):
            envelope.tick = 2
        with pytest.raises(ValidationError):
            envelope.context.branch_id = "elsewhere"
        with pytest.raises(ValidationError):
            envelope.projection.tick = 2
        with pytest.raises(ValidationError):
            envelope.projection.shipments[0].quantity = 1
        with pytest.raises(AttributeError):
            envelope.projection.shipments.append(Shipment(due_tick=3, quantity=2))
        payload = envelope.model_dump(mode="json")
        assert isinstance(payload["projection"]["shipments"], list)
        assert envelope.projection_hash == digest(payload["projection"])
        assert envelope.observation_hash == digest(
            {key: value for key, value in payload.items() if key != "observation_hash"}
        )
        assert ObservationEnvelope.model_validate(payload) == envelope
        assert ObservationEnvelope.model_validate_json(envelope.model_dump_json()) == envelope
        payload["projection"]["shipments"][0]["quantity"] = 1
        assert envelope.projection.shipments[0].quantity == spec.shipment_size
    state.shipments.clear()
    assert len(retailer.projection.shipments) == len(supplier.projection.shipments) == 1


def test_supplier_loss_is_not_exposed_to_either_participant():
    spec = Scenario(
        name="private supplier loss",
        disturbances=[{"tick": 1, "kind": "supplier_loss", "amount": 3}],
    )
    state = kernel.step(spec, kernel.initial_state(spec), "wait").state
    assert state.lost == 3
    for role in ("retailer", "supplier"):
        assert "lost" not in kernel.observe(state, role)
        envelope = observe_envelope(state, f"{role}-1", role, context=context_for(spec))
        assert "lost" not in envelope.projection.model_dump()
    assert kernel.observe(state, "director")["lost"] == 3


def test_observations_have_no_private_state_digest(case):
    _, state, context, retailer, _ = case
    # Same public context/projection => same identity, regardless of hidden state.
    # Immutable branch/tick provenance is the director's responsibility, not a
    # participant-visible commitment to enumerable private inventory/cash.
    hidden_change = state.model_copy(update={"supplier_stock": 39})
    assert (
        observe_envelope(hidden_change, retailer.actor_id, "retailer", context=context) == retailer
    )
    supplier = observe_envelope(state, "supplier-1", "supplier", context=context)
    hidden_change = state.model_copy(update={"cash": 159})
    assert observe_envelope(hidden_change, "supplier-1", "supplier", context=context) == supplier
    for observation in (retailer, supplier):
        assert set(observation.model_dump()) == {
            "actor_id",
            "role",
            "context",
            "tick",
            "projection",
            "projection_hash",
            "observation_hash",
        }
        assert kernel.state_hash(state) not in observation.model_dump_json()


@pytest.mark.parametrize(
    "updates",
    [
        {"branch_id": "branch-2"},
        {"scenario_revision": 2},
        {"spec_hash": "f" * 64},
    ],
)
def test_identity_binds_context_even_when_projection_is_identical(case, updates):
    _, state, context, envelope, _ = case
    changed_context = ObservationContext.model_validate({**context.model_dump(), **updates})
    changed = observe_envelope(state, envelope.actor_id, envelope.role, context=changed_context)
    assert changed.projection_hash == envelope.projection_hash
    assert changed.observation_hash != envelope.observation_hash
    assert_rejected(case, observation=changed)


def test_identity_binds_actor_and_proposal_uses_envelope_hash(case):
    _, state, context, envelope, proposal = case
    other = observe_envelope(state, "retailer-2", "retailer", context=context)
    assert envelope.projection_hash == other.projection_hash
    assert envelope.observation_hash != other.observation_hash
    assert proposal.observation_hash == envelope.observation_hash
    assert proposal.observation_hash != envelope.projection_hash
    assert_rejected(
        case, proposal=proposal.model_copy(update={"observation_hash": envelope.projection_hash})
    )


def test_same_fake_actor_observation_and_adjudication_are_deterministic(case):
    *_, envelope, proposal = case
    assert proposal == FakeActor("retailer-1", "retailer").propose(envelope)
    assert proposal.policy_id == "fake.retailer.fixed-action.v1"
    assert judge(case) == judge(case)


@pytest.mark.parametrize(
    "role,action", [("retailer", a) for a in kernel.ACTIONS] + [("supplier", "wait")]
)
def test_only_kernel_step_executes_accepted_proposal(case, monkeypatch, role, action):
    spec, state, context, _, _ = case
    actor_id = f"{role}-1"
    envelope = observe_envelope(state, actor_id, role, context=context)
    before = state.model_dump()
    proposal = FakeActor(actor_id, role, action).propose(envelope)
    assert state.model_dump() == before
    direct = kernel.step(spec, state, action).state
    calls = []
    real_step = kernel.step

    def traced_step(*args):
        calls.append(args)
        return real_step(*args)

    monkeypatch.setattr(kernel, "step", traced_step)
    record, result = judge(case, observation=envelope, proposal=proposal)
    assert len(calls) == 1
    assert calls[0] == (spec, state, action)
    assert result == direct
    assert result is not state
    assert result.shipments is not state.shipments
    assert state.model_dump() == before
    assert record.status == "accepted"
    assert record.pre_state_hash == kernel.state_hash(state)
    assert record.post_state_hash == kernel.state_hash(direct)
    assert record.observation_hash == envelope.observation_hash
    assert record.context == context
    assert record.role == role
    assert record.policy_id == proposal.policy_id
    assert record.record_hash == digest(record.model_dump(mode="json", exclude={"record_hash"}))
    assert AdjudicationRecord.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("action", ["order_standard", "order_express"])
def test_supplier_cannot_spend_retailer_cash_even_with_legal_kernel_order(
    case, monkeypatch, action
):
    spec, state, context, _, _ = case
    assert kernel.step(spec, state, action).state.spent > 0
    envelope = observe_envelope(state, "supplier-1", "supplier", context=context)
    proposal = FakeActor("supplier-1", "supplier", action).propose(envelope)

    def forbidden(*args):
        pytest.fail("unauthorized proposal reached kernel.step")

    monkeypatch.setattr(kernel, "step", forbidden)
    record, _ = assert_rejected(case, observation=envelope, proposal=proposal)
    assert "supplier may only wait" in record.reason
    assert record.action == action


@pytest.mark.parametrize("params", [{"initial_cash": 0}, {"supplier_stock": 0}])
@pytest.mark.parametrize("action", ["order_standard", "order_express"])
def test_illegal_proposal_rejected_without_substitution(params, action):
    spec = Scenario(name="cannot order", **params)
    state = kernel.initial_state(spec)
    context = context_for(spec)
    envelope = observe_envelope(state, "retailer-1", "retailer", context=context)
    proposal = FakeActor("retailer-1", "retailer", action).propose(envelope)
    case = spec, state, context, envelope, proposal
    record, _ = assert_rejected(case)
    assert "kernel rejected" in record.reason
    assert record.action == action


def test_horizon_rejected_by_kernel(case):
    spec, state, context, _, _ = case
    for _ in range(spec.horizon):
        state = kernel.step(spec, state, "wait").state
    envelope = observe_envelope(state, "retailer-1", "retailer", context=context)
    proposal = FakeActor("retailer-1", "retailer").propose(envelope)
    record, _ = assert_rejected(case, state=state, observation=envelope, proposal=proposal)
    assert "horizon" in record.reason


def test_stale_observation_rejected_with_detached_shipments(case):
    spec, state, _, _, _ = case
    changed = kernel.step(spec, state, "order_standard").state
    record, result = assert_rejected(case, state=changed)
    assert "stale" in record.reason
    assert result.shipments[0] is not changed.shipments[0]
    result.shipments.clear()
    assert len(changed.shipments) == 1


@pytest.mark.parametrize("rehash", [False, True])
def test_projection_tampering_rejected_even_with_recomputed_hashes(case, rehash):
    *_, envelope, proposal = case
    payload = envelope.model_dump(mode="json")
    payload["projection"]["cash"] -= 1
    changed = rehash_observation(payload) if rehash else ObservationEnvelope.model_validate(payload)
    forged_proposal = proposal.model_copy(update={"observation_hash": changed.observation_hash})
    assert_rejected(case, observation=changed, proposal=forged_proposal)
    if not rehash:
        with pytest.raises(ValueError, match="projection hash mismatch"):
            FakeActor("retailer-1", "retailer").propose(changed)


@pytest.mark.parametrize("field", ["projection_hash", "observation_hash"])
def test_hash_tampering_rejected(case, field):
    envelope = case[3].model_copy(update={field: "f" * 64})
    assert_rejected(case, observation=envelope)
    with pytest.raises(ValueError, match="hash mismatch"):
        FakeActor("retailer-1", "retailer").propose(envelope)


@pytest.mark.parametrize(
    "field,value", [("actor_id", "retailer-2"), ("tick", 1), ("context", None)]
)
def test_fake_actor_rechecks_all_envelope_identity_fields(case, field, value):
    envelope = case[3]
    if field == "context":
        value = envelope.context.model_copy(update={"scenario_revision": 2})
    changed = envelope.model_copy(update={field: value})
    with pytest.raises(ValueError):
        FakeActor("retailer-1", "retailer").propose(changed)


@pytest.mark.parametrize("updates", [{"actor_id": "other"}, {"role": "supplier"}])
def test_cross_actor_and_role_proposals_rejected(case, updates):
    with pytest.raises(ValueError, match="actor/role differ"):
        judge(case, proposal=case[4].model_copy(update=updates))


def test_self_adjudication_and_wrong_fake_actor_rejected(case):
    with pytest.raises(ValueError, match="independent"):
        judge(case, adjudicator_id="retailer-1")
    with pytest.raises(ValueError, match="does not belong"):
        FakeActor("supplier-1", "supplier").propose(case[3])


def test_authoritative_context_spec_binding_checked(case):
    bad_context = case[2].model_copy(update={"spec_hash": "f" * 64})
    with pytest.raises(ValueError, match="spec_hash"):
        judge(case, context=bad_context)
    with pytest.raises(ValueError, match="spec_hash"):
        judge(case, scenario=case[0].model_copy(update={"initial_cash": 100}))


def test_context_required_at_both_entrypoints(case):
    spec, state, _, envelope, proposal = case
    with pytest.raises(TypeError, match="context"):
        observe_envelope(state, "retailer-1", "retailer")
    with pytest.raises(TypeError, match="context"):
        adjudicate(spec, state, envelope, proposal, adjudicator_id="referee", record_id="r1")


@pytest.mark.parametrize(
    "field,value",
    [
        ("branch_id", ""),
        ("branch_id", "x" * 101),
        ("branch_id", 1),
        ("scenario_revision", 0),
        ("scenario_revision", 2147483648),
        ("scenario_revision", True),
        ("scenario_revision", "1"),
        ("spec_hash", "f" * 63),
        ("spec_hash", "A" * 64),
    ],
)
def test_context_rejects_invalid_bounds_and_types(case, field, value):
    with pytest.raises(ValidationError):
        ObservationContext.model_validate({**case[2].model_dump(), field: value})
    forged = case[2].model_copy(update={field: value})
    with pytest.raises(ValidationError):
        observe_envelope(case[1], "retailer-1", "retailer", context=forged)
    with pytest.raises(ValidationError):
        judge(case, context=forged)


@pytest.mark.parametrize("role", ["director", "unknown", None, True])
def test_participant_boundary_excludes_director(case, role):
    with pytest.raises(ValidationError):
        observe_envelope(case[1], "actor", role, context=case[2])
    with pytest.raises(ValidationError):
        FakeActor("actor", role)


@pytest.mark.parametrize("field", ["record_id", "adjudicator_id"])
@pytest.mark.parametrize("value", ["", "x" * 101, 1, True])
def test_receipt_identifiers_validated_before_execution(case, monkeypatch, field, value):
    def forbidden(*args):
        pytest.fail("invalid identifier reached kernel.step")

    monkeypatch.setattr(kernel, "step", forbidden)
    with pytest.raises(ValidationError):
        judge(case, **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_id", ""),
        ("policy_id", "x" * 101),
        ("action", "steal"),
        ("role", "director"),
        ("observation_hash", "not-a-digest"),
    ],
)
def test_forged_proposal_instances_revalidated(case, field, value):
    payload = {**case[4].model_dump(), field: value}
    for proposal in (
        ActionProposal.model_construct(**payload),
        case[4].model_copy(update={field: value}),
    ):
        with pytest.raises(ValidationError):
            judge(case, proposal=proposal)


def test_forged_nested_observation_state_and_scenario_revalidated(case):
    spec, state, context, envelope, _ = case
    invalid_shipment = Shipment.model_construct(due_tick=2, quantity=True)
    forged_projection = envelope.projection.model_copy(update={"shipments": (invalid_shipment,)})
    forged_observation = envelope.model_copy(update={"projection": forged_projection})
    with pytest.raises(ValidationError):
        judge(case, observation=forged_observation)
    with pytest.raises(ValidationError):
        FakeActor("retailer-1", "retailer").propose(forged_observation)
    invalid_state = State.model_construct(**{**state.model_dump(), "shipments": [invalid_shipment]})
    with pytest.raises(ValidationError):
        judge(case, state=invalid_state)
    with pytest.raises(ValidationError):
        observe_envelope(invalid_state, "actor", "retailer", context=context)
    with pytest.raises(ValidationError):
        judge(case, scenario=spec.model_copy(update={"horizon": True}))
    with pytest.raises(ValidationError):
        judge(case, observation=ObservationEnvelope.model_construct())


@pytest.mark.parametrize(
    "updates",
    [
        {"tick": True},
        {"cash": "1"},
        {"cash": 10001},
        {"inventory": 301},
        {"delivered": 201},
        {"shortage": 401},
        {"spent": -1},
        {"lost": 401},
        {"supplier_stock": 20},
        {"shipments": [{"due_tick": 2, "quantity": 8}] * 11},
        {"shipments": [{"due_tick": 16, "quantity": 8}]},
        {"shipments": [{"due_tick": 2, "quantity": False}]},
    ],
)
def test_projection_contract_rejects_private_extra_fields_and_out_of_bounds(case, updates):
    with pytest.raises(ValidationError):
        RetailerProjection.model_validate({**case[3].projection.model_dump(), **updates})


def test_projection_rejects_arbitrary_iterables_without_consuming_them(case):
    def untrusted_stream():
        pytest.fail("projection consumed an arbitrary iterable")
        yield

    for shipments in (untrusted_stream(), set(), {}, ""):
        with pytest.raises(ValidationError):
            RetailerProjection.model_validate(
                {**case[3].projection.model_dump(), "shipments": shipments}
            )


def test_projection_role_and_tick_consistency(case):
    payload = case[3].model_dump(mode="json")
    with pytest.raises(ValidationError, match="role"):
        ObservationEnvelope.model_validate({**payload, "role": "supplier"})
    with pytest.raises(ValidationError, match="tick"):
        ObservationEnvelope.model_validate({**payload, "tick": 1})
    with pytest.raises(ValidationError):
        SupplierProjection(tick=0, supplier_stock=201, shipments=())
    with pytest.raises(ValidationError):
        SupplierProjection(tick=0, supplier_stock=2, shipments=(), cash=10)


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "supplier"),
        ("reason", "different"),
        ("record_id", "record-2"),
        ("policy_id", "other-policy"),
    ],
)
def test_record_hash_detects_mutation_and_is_content_addressed(case, field, value):
    record, _ = judge(case)
    with pytest.raises(ValidationError, match="hash mismatch"):
        AdjudicationRecord.model_validate(record.model_copy(update={field: value}))
    if field == "record_id":
        changed, _ = judge(case, record_id=value)
    elif field == "policy_id":
        changed, _ = judge(case, proposal=case[4].model_copy(update={field: value}))
    else:
        return
    assert changed.record_hash != record.record_hash


def test_kernel_invariants_still_authoritative(case):
    spec, state, context, _, _ = case
    invalid = state.model_copy(update={"cash": state.cash - 1})
    envelope = observe_envelope(invalid, "retailer-1", "retailer", context=context)
    proposal = FakeActor("retailer-1", "retailer").propose(envelope)
    record, _ = assert_rejected(case, state=invalid, observation=envelope, proposal=proposal)
    assert "cash conservation violated" in record.reason
    assert spec.initial_cash == state.cash
