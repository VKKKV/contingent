"""Finite-model oracles, replay integrity and boundary tests for the pure kernel."""

import json
import random
from hashlib import sha256
from itertools import product

import pytest
from pydantic import ValidationError

from tianji_lab.kernel import (
    initial_state,
    observe,
    search,
    simulate,
    state_hash,
    step,
    validate_trajectory,
)
from tianji_lab.models import Goal, Scenario, SearchResult, Shipment, State, Trajectory

ACTIONS = ("order_express", "order_standard", "wait")


def scenario(**changes):
    return Scenario(name="fictional test", **changes)


def oracle(spec, actions):
    """Independent integer-only reference: no kernel calls or State models."""
    inventory, cash, stock = spec.initial_inventory, spec.initial_cash, spec.supplier_stock
    delivered = shortage = spent = 0
    pending = []
    for tick, action in enumerate(actions, 1):
        if action != "wait":
            cost, lead = {
                "order_standard": (spec.standard_cost, spec.standard_lead),
                "order_express": (spec.express_cost, spec.express_lead),
            }[action]
            if cash < cost or stock < spec.shipment_size:
                return None
            cash -= cost
            spent += cost
            stock -= spec.shipment_size
            pending.append((tick - 1 + lead, spec.shipment_size))
        arriving = [item for item in pending if item[0] == tick]
        pending = [item for item in pending if item[0] != tick]
        inventory += sum(quantity for _, quantity in arriving)
        for _ in range(spec.demand_per_tick):
            if inventory:
                inventory -= 1
                delivered += 1
            else:
                shortage += 1
    return {
        "tick": len(actions),
        "inventory": inventory,
        "cash": cash,
        "supplier_stock": stock,
        "delivered": delivered,
        "shortage": shortage,
        "spent": spent,
        "shipments": [{"due_tick": due, "quantity": quantity} for due, quantity in sorted(pending)],
    }


def oracle_plans(spec, goal):
    found = []
    for actions in product(ACTIONS, repeat=spec.horizon):
        final = oracle(spec, actions)
        if final is None:
            continue
        actual = simulate(spec, list(actions)).final_state.model_dump()
        assert actual == final
        if (
            final["shortage"] <= goal.max_shortage
            and final["cash"] >= goal.min_cash
            and final["spent"] <= goal.max_spend
            and final["inventory"] >= goal.min_inventory
        ):
            found.append((final["spent"], final["shortage"], actions))
    return sorted(found)[:3]


def assert_invariants(spec, state):
    assert (
        state.inventory
        + state.delivered
        + state.supplier_stock
        + sum(item.quantity for item in state.shipments)
        == spec.initial_inventory + spec.supplier_stock
    )
    assert state.cash + state.spent == spec.initial_cash
    assert state.delivered + state.shortage == state.tick * spec.demand_per_tick
    assert all(item.due_tick > state.tick for item in state.shipments)


def test_forward_order_timing_lost_demand_and_conservation():
    spec = scenario(horizon=3, initial_inventory=2, demand_per_tick=4)
    origin = initial_state(spec)
    before = origin.model_dump()
    actions = ["order_standard"]
    run = simulate(spec, actions)
    assert actions == ["order_standard"]
    assert origin.model_dump() == before
    assert run.actions == ["order_standard", "wait", "wait"]
    assert run.frames[0].action == "initial"
    first, second, final = [frame.state for frame in run.frames[1:]]
    assert (first.inventory, first.delivered, first.shortage) == (0, 2, 2)
    assert first.shipments == [Shipment(due_tick=2, quantity=8)]
    assert (second.inventory, second.delivered, second.shortage) == (4, 6, 2)
    assert (final.inventory, final.delivered, final.shortage) == (0, 10, 2)
    assert run.goal_met is None
    assert run.rule_version == "supply-chain.v1"
    for frame in run.frames:
        assert_invariants(spec, frame.state)
        assert frame.state_hash == state_hash(frame.state)
    assert validate_trajectory(spec, run)


def test_express_delivery_in_same_advance_and_after_horizon_transit():
    spec = scenario(horizon=1, initial_inventory=0)
    express = simulate(spec, ["order_express"])
    assert express.final_state.delivered == 4
    assert express.final_state.inventory == 4
    standard = simulate(spec, ["order_standard"])
    assert standard.final_state.delivered == 0
    assert standard.final_state.shortage == 4
    assert standard.final_state.shipments == [Shipment(due_tick=2, quantity=8)]
    assert_invariants(spec, standard.final_state)


def test_simultaneous_arrivals_and_no_input_aliasing():
    spec = scenario(horizon=4, standard_lead=3, express_lead=2)
    first = step(spec, initial_state(spec), "order_standard")
    second = step(spec, first.state, "order_express")
    before = second.model_dump()
    third = step(spec, second.state, "wait")
    assert second.model_dump() == before
    assert len(second.state.shipments) == 2
    assert third.state.shipments == []
    assert "received 16 at tick 3" in third.events
    run = simulate(spec, [], start=second.state)
    run.frames[0].state.shipments.clear()
    assert second.model_dump() == before
    with pytest.raises(ValidationError):
        second.state.cash = 0


def test_hash_is_canonical_sha256_json_and_sensitive_to_all_state_fields():
    original = initial_state(scenario())
    data = original.model_dump(mode="json")
    expected = sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert state_hash(original) == expected
    assert state_hash(State.model_validate(dict(reversed(list(data.items()))))) == expected
    for field in ("tick", "inventory", "cash", "supplier_stock", "delivered", "shortage", "spent"):
        changed = dict(data)
        changed[field] += 1
        assert state_hash(State.model_validate(changed)) != expected
    changed = dict(data, shipments=[{"due_tick": 2, "quantity": 8}])
    assert state_hash(State.model_validate(changed)) != expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("horizon", 0),
        ("horizon", 11),
        ("horizon", True),
        ("horizon", "2"),
        ("horizon", 2.0),
        ("horizon", float("nan")),
        ("horizon", float("inf")),
        ("initial_inventory", -1),
        ("initial_inventory", 101),
        ("initial_cash", 10001),
        ("demand_per_tick", 0),
        ("supplier_stock", 201),
        ("shipment_size", 21),
        ("standard_cost", 0),
        ("express_cost", 1001),
        ("standard_lead", 6),
        ("express_lead", 0),
        ("description", "x" * 2001),
    ],
)
def test_strict_bounded_scenario_fields(field, value):
    with pytest.raises(ValidationError):
        scenario(**{field: value})


@pytest.mark.parametrize(
    "model,payload",
    [
        (Scenario, {"name": ""}),
        (Scenario, {"name": "x" * 101}),
        (Scenario, {"name": "x", "hidden_real_data": 1}),
        (Goal, {"max_shortage": 201}),
        (Goal, {"min_cash": True}),
        (Goal, {"max_spend": -1}),
        (Goal, {"min_inventory": 101}),
        (Goal, {"probability": 0.99}),
        (Shipment, {"due_tick": 0, "quantity": 1}),
        (Shipment, {"due_tick": 2, "quantity": 0}),
    ],
)
def test_other_schema_rejections(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("action", ["buy", "WAIT", "", None, 1, [], {}])
def test_unknown_actions_fail_without_mutation(action):
    spec = scenario()
    state = initial_state(spec)
    before = state.model_dump()
    with pytest.raises(ValueError):
        step(spec, state, action)
    assert state.model_dump() == before


@pytest.mark.parametrize("changes", [{"initial_cash": 0}, {"supplier_stock": 7}])
@pytest.mark.parametrize("action", ["order_standard", "order_express"])
def test_order_preconditions(changes, action):
    spec = scenario(**changes)
    state = initial_state(spec)
    before = state.model_dump()
    with pytest.raises(ValueError, match="insufficient"):
        step(spec, state, action)
    assert state.model_dump() == before
    assert step(spec, state, "wait").state.tick == 1


def test_horizon_padding_and_bad_action_sequences():
    spec = scenario(horizon=2)
    for actions in (["wait"] * 3, ["wait", "cheat"], "wait", ("wait",)):
        with pytest.raises(ValueError):
            simulate(spec, actions)
    terminal = simulate(spec, []).final_state
    with pytest.raises(ValueError, match="horizon"):
        step(spec, terminal, "wait")
    assert len(simulate(spec, [], start=terminal).frames) == 1
    with pytest.raises(ValueError):
        simulate(spec, ["wait"], start=terminal)


@pytest.mark.parametrize(
    "updates",
    [
        {"inventory": 13},
        {"cash": 159},
        {"shortage": 1},
        {"tick": 1},
        {"inventory": -1},
        {"cash": "160"},
        {"supplier_stock": 32, "inventory": 20},
        {"supplier_stock": 39, "inventory": 13},
    ],
)
def test_invalid_start_including_unvalidated_model_copy_is_rejected(updates):
    spec = scenario()
    invalid = initial_state(spec).model_copy(update=updates)
    with pytest.raises(ValueError):
        simulate(spec, [], start=invalid)
    with pytest.raises(ValueError):
        search(spec, Goal(), start=invalid)


def test_stale_or_forged_pending_shipments_are_rejected():
    spec = scenario()
    state = step(spec, initial_state(spec), "order_standard").state
    for shipment in (Shipment(due_tick=1, quantity=8), Shipment(due_tick=10, quantity=8)):
        invalid = state.model_copy(update={"shipments": [shipment]})
        with pytest.raises(ValueError, match="due tick"):
            step(spec, invalid, "wait")


def test_fork_replay_and_json_roundtrip():
    spec = scenario()
    original = simulate(spec, ["order_standard", "wait", "order_express"])
    start = original.frames[2].state
    before = original.model_dump()
    fork = simulate(spec, ["order_standard"], start=start, goal=Goal(max_shortage=200))
    assert fork.frames[0].state.tick == 2
    assert len(fork.actions) == spec.horizon - start.tick
    assert original.model_dump() == before
    assert validate_trajectory(spec, fork, start=start)
    assert Trajectory.model_validate_json(fork.model_dump_json()) == fork
    with pytest.raises(ValueError):
        validate_trajectory(spec, fork)
    result = search(spec, Goal(max_shortage=200), max_nodes=50000, start=start)
    assert result.status == "found" and result.exhausted
    assert all(validate_trajectory(spec, plan, start=start) for plan in result.plans)


@pytest.mark.parametrize("tamper", ["cash", "events", "action", "hash", "frames", "final", "rules"])
def test_replay_rejects_tampering_even_with_recomputed_hashes(tamper):
    spec = scenario()
    data = simulate(spec, ["order_standard"]).model_dump()
    if tamper == "cash":
        data["frames"][1]["state"]["cash"] += 1
        data["frames"][1]["state_hash"] = state_hash(
            State.model_validate(data["frames"][1]["state"])
        )
    elif tamper == "events":
        data["frames"][1]["events"] = ["forged adjudication"]
    elif tamper == "action":
        data["actions"][0] = "wait"
    elif tamper == "hash":
        data["state_hash"] = "0" * 64
    elif tamper == "frames":
        data["frames"].pop(1)
    elif tamper == "final":
        data["final_state"] = data["frames"][0]["state"]
        data["state_hash"] = data["frames"][0]["state_hash"]
    else:
        data["rule_version"] = "untrusted.rules"
    with pytest.raises(ValueError):
        validate_trajectory(spec, Trajectory.model_validate(data))


def test_goal_checked_only_at_horizon():
    spec = scenario(horizon=2, initial_inventory=4, supplier_stock=0)
    assert initial_state(spec).shortage == 0
    result = search(spec, Goal())
    assert result.status == "no_solution"
    assert result.exhausted and result.plans == []


@pytest.mark.parametrize("budget", [0, 50001, True, 2.0, "2", None])
def test_invalid_search_budget(budget):
    with pytest.raises(ValueError, match="max_nodes"):
        search(scenario(), Goal(), max_nodes=budget)


def test_budget_status_found_incomplete_and_exact_exhaustion_boundary():
    spec = scenario(horizon=1, initial_inventory=4)
    goal = Goal(max_shortage=200)
    bounded = search(spec, goal, max_nodes=1)
    assert (bounded.status, bounded.exhausted, bounded.expanded) == ("budget_exhausted", False, 1)
    partial = search(spec, goal, max_nodes=2)
    assert partial.status == "found" and not partial.exhausted
    assert len(partial.plans) == 1
    complete = search(spec, goal, max_nodes=4)
    assert complete.status == "found" and complete.exhausted and complete.expanded == 4
    assert [plan.final_state.spent for plan in complete.plans] == [0, 16, 32]
    assert SearchResult.model_validate_json(complete.model_dump_json()) == complete
    terminal = simulate(spec, []).final_state
    done = search(spec, goal, max_nodes=1, start=terminal)
    assert done.exhausted and done.expanded == 1 and done.plans[0].actions == []
    impossible = search(
        scenario(horizon=1, initial_cash=0, initial_inventory=0), Goal(), max_nodes=2
    )
    assert impossible.status == "no_solution" and impossible.exhausted


def test_search_matches_exhaustive_independent_oracle_and_top_three_prefixes():
    rng = random.Random(731)
    specs = [
        scenario(horizon=4, standard_cost=1, express_cost=1, standard_lead=1, express_lead=1),
        scenario(horizon=4, standard_cost=3, express_cost=1, standard_lead=1, express_lead=3),
        scenario(horizon=4, initial_cash=0, initial_inventory=0, supplier_stock=0),
    ]
    specs += [
        scenario(
            horizon=rng.randint(1, 4),
            initial_inventory=rng.randint(0, 8),
            initial_cash=rng.randint(0, 16),
            supplier_stock=rng.randint(0, 18),
            shipment_size=rng.randint(1, 6),
            demand_per_tick=rng.randint(1, 5),
            standard_cost=rng.randint(1, 8),
            express_cost=rng.randint(1, 8),
            standard_lead=rng.randint(1, 5),
            express_lead=rng.randint(1, 5),
        )
        for _ in range(35)
    ]
    for spec in specs:
        for goal in (
            Goal(),
            Goal(max_shortage=200, max_spend=10000),
            Goal(
                max_shortage=rng.randint(0, 12),
                min_inventory=rng.randint(0, 3),
                min_cash=rng.randint(0, 6),
                max_spend=rng.randint(0, 12),
            ),
        ):
            expected = oracle_plans(spec, goal)
            result = search(spec, goal, max_nodes=50000)
            actual = [
                (p.final_state.spent, p.final_state.shortage, tuple(p.actions))
                for p in result.plans
            ]
            assert actual == expected, (spec, goal, expected, actual)
            assert result.exhausted
            assert result.status == ("found" if expected else "no_solution")
            for plan in result.plans:
                assert plan.goal_met is True
                assert validate_trajectory(spec, plan)
                for frame in plan.frames:
                    assert_invariants(spec, frame.state)


def test_observations_are_explicit_role_projections_and_detached():
    spec = scenario()
    state = step(spec, initial_state(spec), "order_standard").state
    assert observe(state, "director") == state.model_dump(mode="json")
    retailer = observe(state, "retailer")
    assert "supplier_stock" not in retailer
    assert {"cash", "inventory", "shortage"} <= retailer.keys()
    supplier = observe(state, "supplier")
    assert set(supplier) == {"tick", "supplier_stock", "shipments"}
    assert not {"cash", "spent", "inventory", "delivered", "shortage"} & supplier.keys()
    supplier["shipments"].clear()
    retailer["shipments"][0]["quantity"] = 1
    assert state.shipments == [Shipment(due_tick=2, quantity=8)]
    with pytest.raises(ValueError):
        observe(state, "admin")
