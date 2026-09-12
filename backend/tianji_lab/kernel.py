"""Deterministic rules-v1 simulation and finite, model-conditional goal search.

`delivered` counts goods served to retail customers, not inbound shipments.
Shortage is cumulative lost demand, never a recoverable backlog. Costs are per
shipment. Search explores action sequences, not probabilities or bargaining.
"""

import json
from hashlib import sha256

from .models import Action, Frame, Goal, Role, Scenario, SearchResult, Shipment, State, Trajectory

ACTIONS: tuple[Action, ...] = ("order_express", "order_standard", "wait")


def initial_state(scenario: Scenario) -> State:
    scenario = Scenario.model_validate(scenario)
    return State(
        tick=0,
        inventory=scenario.initial_inventory,
        cash=scenario.initial_cash,
        supplier_stock=scenario.supplier_stock,
        delivered=0,
        shortage=0,
        spent=0,
        shipments=[],
    )


def state_hash(state: State) -> str:
    state = State.model_validate(state)
    payload = json.dumps(
        state.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _check_state(scenario: Scenario, state: State) -> State:
    state = State.model_validate(state)
    if state.tick > scenario.horizon:
        raise ValueError("state tick exceeds scenario horizon")
    if state.cash + state.spent != scenario.initial_cash:
        raise ValueError("cash conservation violated")
    goods = (
        state.inventory
        + state.delivered
        + state.supplier_stock
        + sum(shipment.quantity for shipment in state.shipments)
    )
    if goods != scenario.initial_inventory + scenario.supplier_stock:
        raise ValueError("goods conservation violated")
    if state.supplier_stock > scenario.supplier_stock:
        raise ValueError("supplier stock exceeds initial stock")
    if state.delivered + state.shortage != state.tick * scenario.demand_per_tick:
        raise ValueError("cumulative demand accounting violated")
    purchased = scenario.supplier_stock - state.supplier_stock
    if purchased % scenario.shipment_size:
        raise ValueError("purchased stock must consist of whole shipments")
    order_count = purchased // scenario.shipment_size
    if order_count > state.tick or len(state.shipments) > order_count:
        raise ValueError("more shipments than possible orders")
    if not any(
        express * scenario.express_cost + (order_count - express) * scenario.standard_cost
        == state.spent
        for express in range(order_count + 1)
    ):
        raise ValueError("spend does not match purchased shipments")
    for shipment in state.shipments:
        if shipment.quantity != scenario.shipment_size:
            raise ValueError("pending shipment quantity differs from scenario")
        if (
            not state.tick
            < shipment.due_tick
            <= (state.tick - 1 + max(scenario.standard_lead, scenario.express_lead))
        ):
            raise ValueError("invalid pending shipment due tick")
    if state.tick == 0 and state != initial_state(scenario):
        raise ValueError("tick zero must match scenario initial state")
    return state


def _legal(scenario: Scenario, state: State, action: Action) -> bool:
    if action == "wait":
        return True
    cost = scenario.standard_cost if action == "order_standard" else scenario.express_cost
    return state.cash >= cost and state.supplier_stock >= scenario.shipment_size


def _parse_action(action: str) -> Action:
    if isinstance(action, str):
        if action == "wait":
            return "wait"
        if action == "order_standard":
            return "order_standard"
        if action == "order_express":
            return "order_express"
    raise ValueError(f"unknown action: {action!r}")


def step(scenario: Scenario, state: State, action: str) -> Frame:
    """Purchase, advance the clock, receive due goods, then serve fixed demand."""
    parsed_action = _parse_action(action)
    scenario = Scenario.model_validate(scenario)
    state = _check_state(scenario, state)
    if state.tick >= scenario.horizon:
        raise ValueError("cannot act at or beyond the horizon")
    if not _legal(scenario, state, parsed_action):
        raise ValueError("insufficient cash or supplier stock for order")

    inventory, cash, stock, spent = (state.inventory, state.cash, state.supplier_stock, state.spent)
    shipments = [shipment.model_copy(deep=True) for shipment in state.shipments]
    events: list[str] = []
    if action != "wait":
        standard = action == "order_standard"
        cost = scenario.standard_cost if standard else scenario.express_cost
        lead = scenario.standard_lead if standard else scenario.express_lead
        due_tick = state.tick + lead
        cash -= cost
        spent += cost
        stock -= scenario.shipment_size
        shipments.append(Shipment(due_tick=due_tick, quantity=scenario.shipment_size))
        events.append(f"{action}: purchased {scenario.shipment_size}; cost {cost}; due {due_tick}")
    else:
        events.append("wait: no order")

    tick = state.tick + 1
    arrived = sum(shipment.quantity for shipment in shipments if shipment.due_tick <= tick)
    inventory += arrived
    shipments = sorted(
        (shipment for shipment in shipments if shipment.due_tick > tick),
        key=lambda shipment: (shipment.due_tick, shipment.quantity),
    )
    if arrived:
        events.append(f"received {arrived} at tick {tick}")
    served = min(inventory, scenario.demand_per_tick)
    shortage = scenario.demand_per_tick - served
    events.append(f"demand {scenario.demand_per_tick}: delivered {served}; shortage {shortage}")
    next_state = _check_state(
        scenario,
        State(
            tick=tick,
            inventory=inventory - served,
            cash=cash,
            supplier_stock=stock,
            delivered=state.delivered + served,
            shortage=state.shortage + shortage,
            spent=spent,
            shipments=shipments,
        ),
    )
    return Frame(
        state=next_state, action=parsed_action, events=events, state_hash=state_hash(next_state)
    )


def _goal_met(state: State, goal: Goal) -> bool:
    return (
        state.shortage <= goal.max_shortage
        and state.cash >= goal.min_cash
        and state.spent <= goal.max_spend
        and state.inventory >= goal.min_inventory
    )


def simulate(
    scenario: Scenario,
    actions: list[str],
    goal: Goal | None = None,
    start: State | None = None,
) -> Trajectory:
    scenario = Scenario.model_validate(scenario)
    if goal is not None:
        goal = Goal.model_validate(goal)
    state = initial_state(scenario) if start is None else _check_state(scenario, start)
    if not isinstance(actions, list):
        raise ValueError("actions must be a list")
    if len(actions) > scenario.horizon - state.tick:
        raise ValueError("too many actions for remaining horizon")
    padded: list[Action] = [_parse_action(action) for action in actions]
    while len(padded) < scenario.horizon - state.tick:
        padded.append("wait")
    frames = [Frame(state=state, action="initial", events=[], state_hash=state_hash(state))]
    for action in padded:
        frame = step(scenario, state, action)
        frames.append(frame)
        state = frame.state
    return Trajectory(
        frames=frames,
        actions=padded,
        final_state=state,
        state_hash=state_hash(state),
        goal_met=None if goal is None else _goal_met(state, goal),
    )


def validate_trajectory(
    scenario: Scenario, trajectory: Trajectory, start: State | None = None
) -> bool:
    """Replay all frames, including events, rather than trusting supplied hashes.

    A continuation must supply its independently trusted fork state as `start`.
    `goal_met` cannot be authenticated here: Goal is not part of this contract;
    search separately checks the actual terminal goal against forward replay.
    """
    trajectory = Trajectory.model_validate(trajectory)
    replay = simulate(scenario, list(trajectory.actions), start=start)
    if trajectory.model_dump(exclude={"goal_met"}) != replay.model_dump(exclude={"goal_met"}):
        raise ValueError("trajectory differs from deterministic forward replay")
    return True


def _state_key(state: State) -> tuple:
    # Every transition-relevant field participates; no inventory-only merging.
    return (
        state.tick,
        state.inventory,
        state.cash,
        state.supplier_stock,
        state.delivered,
        state.shortage,
        state.spent,
        tuple(sorted((shipment.due_tick, shipment.quantity) for shipment in state.shipments)),
    )


def search(
    scenario: Scenario,
    goal: Goal,
    max_nodes: int = 5000,
    start: State | None = None,
) -> SearchResult:
    """Lexicographic DFS with a hard bound on expanded prefix states.

    Retain the first three prefixes per full sufficient state: one would retain
    feasibility but could discard globally top-three action sequences. DFS visits
    equal-length prefixes lexicographically, so later equivalent prefixes cannot
    improve the ranked top three. An incomplete search ranks only plans found;
    `exhausted` alone certifies finite-model completeness. Terminal visits count
    against the node budget, including a start already at the horizon.
    """
    if type(max_nodes) is not int or not 1 <= max_nodes <= 50000:
        raise ValueError("max_nodes must be an integer between 1 and 50000")
    scenario = Scenario.model_validate(scenario)
    goal = Goal.model_validate(goal)
    origin = initial_state(scenario) if start is None else _check_state(scenario, start)
    frontier: list[tuple[State, tuple[Action, ...]]] = [(origin, ())]
    visited: dict[tuple, int] = {}
    candidates: list[tuple[int, int, tuple[Action, ...]]] = []
    expanded = 0
    while frontier:
        state, actions = frontier[-1]
        key = _state_key(state)
        if visited.get(key, 0) >= 3:
            frontier.pop()
            continue
        if expanded >= max_nodes:
            break
        frontier.pop()
        visited[key] = visited.get(key, 0) + 1
        expanded += 1
        if state.tick == scenario.horizon:
            if _goal_met(state, goal):
                candidates.append((state.spent, state.shortage, actions))
                candidates.sort()
                del candidates[3:]
            continue
        for action in reversed(ACTIONS):
            if _legal(scenario, state, action):
                successor = step(scenario, state, action).state
                frontier.append((successor, (*actions, action)))

    plans: list[Trajectory] = []
    for _, _, actions in candidates:
        plan = simulate(scenario, list(actions), goal=goal, start=origin)
        validate_trajectory(scenario, plan, start=origin)
        if plan.goal_met is not True:
            raise ValueError("search candidate failed forward goal verification")
        plans.append(plan)
    exhausted = not frontier
    status = "found" if plans else ("no_solution" if exhausted else "budget_exhausted")
    return SearchResult(plans=plans, expanded=expanded, exhausted=exhausted, status=status)


def observe(state: State, role: Role) -> dict:
    """Return a detached role projection; the director view is privileged."""
    state = State.model_validate(state)
    if role == "director":
        return state.model_dump(mode="json")
    if role == "retailer":
        return state.model_dump(mode="json", exclude={"supplier_stock"})
    if role == "supplier":
        # Allowlist excludes retail inventory, demand fulfillment, cash and spend.
        return state.model_dump(mode="json", include={"tick", "supplier_stock", "shipments"})
    raise ValueError(f"unknown observation role: {role!r}")
