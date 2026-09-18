"""Single validated operation registry shared by HTTP and the MCP adapter."""

import hashlib
import json
import multiprocessing
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import kernel
from .models import (
    RULE_VERSION_V1,
    Action,
    Goal,
    RuleVersion,
    Scenario,
    State,
    Trajectory,
)
from .offline_adjudication import (
    ActionProposal,
    AdjudicationRecord,
    ObservationContext,
    ObservationEnvelope,
    ParticipantRole,
    adjudicate,
    observe_envelope,
)
from .store import Store, canonical

Identifier = Annotated[str, Field(min_length=1, max_length=100)]
Name = Annotated[str, Field(min_length=1, max_length=100)]
Tick = Annotated[int, Field(ge=0, le=10)]
Revision = Annotated[int, Field(ge=1, le=2_147_483_647)]
Actions = Annotated[list[Action], Field(max_length=10)]


class OperationError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Input):
    pass


class ById(Input):
    id: Identifier


class ScenarioCreate(Input):
    spec: Scenario


class ScenarioUpdate(ScenarioCreate):
    id: Identifier
    revision: Revision


class ByScenario(Input):
    scenario_id: Identifier


class Forward(ByScenario):
    actions: Actions
    name: Name = "Forward exploration"


class Backward(ByScenario):
    goal: Goal
    max_nodes: Annotated[int, Field(ge=1, le=50_000)] = 5000
    name: Name = "Goal plan"


class Fork(ById):
    tick: Tick
    actions: Actions
    name: Name = "Fork continuation"


class ByBranch(Input):
    branch_id: Identifier


class ObservationCreate(ByBranch):
    tick: Tick
    actor_id: Identifier
    role: ParticipantRole


class AdjudicationCreate(Input):
    observation_id: Identifier
    proposal: ActionProposal
    adjudicator_id: Identifier


class SavedAdjudication(Input):
    id: Identifier
    observation_id: Identifier
    record: AdjudicationRecord
    next_state: State


class Compare(Input):
    left_id: Identifier
    right_id: Identifier


class Import(Input):
    bundle: dict


class Attach(Input):
    id: Identifier | None = None


class WorkspaceUpdate(ById):
    revision: Revision
    branch_id: Identifier | None = None
    scenario_id: Identifier | None = None
    compare_branch_id: Identifier | None = None
    tick: Tick | None = None
    panel: Literal["timeline", "compare", "goal"] | None = None


class Provenance(Input):
    rule_version: RuleVersion = RULE_VERSION_V1
    policy: Literal["rules-v1"] = "rules-v1"
    scenario: Literal["fictional"] = "fictional"
    interpretation: Literal["model-conditional"] = "model-conditional"
    prefix_actions: Actions = Field(default_factory=list)
    goal: Goal | None = None
    imported_parent_id: Identifier | None = None


class Branch(Input):
    id: Identifier
    name: Name
    scenario_id: Identifier
    scenario_revision: Revision
    spec: Scenario
    parent_id: Identifier | None
    fork_tick: Tick | None
    trajectory: Trajectory
    mode: Literal["forward", "backward", "fork", "import"]
    created_at: Annotated[str, Field(max_length=100)]
    provenance: Provenance = Field(default_factory=Provenance)


# Each schema is the authoritative input schema, including MCP tools/list.
OPERATIONS = {
    "scenario_list": (Empty, False, "List fictional scenario specifications."),
    "scenario_create": (ScenarioCreate, True, "Create a fictional scenario."),
    "scenario_update": (
        ScenarioUpdate,
        True,
        "Update a scenario using revision CAS; branches stay frozen.",
    ),
    "branch_list": (ByScenario, False, "List recorded branches for a scenario."),
    "branch_get": (ById, False, "Read a branch and its frozen assumptions."),
    "observation_create": (
        ObservationCreate,
        True,
        "Director: save a role-scoped observation of a frozen branch tick; not participant auth.",
    ),
    "observation_get": (ById, False, "Director: read one saved role-scoped observation."),
    "adjudication_create": (
        AdjudicationCreate,
        True,
        "Director: save an independent kernel-checked proposal preview; never changes a branch.",
    ),
    "adjudication_get": (ById, False, "Director: read an adjudication and next-state preview."),
    "adjudication_list": (
        ByBranch,
        False,
        "Director: list bounded adjudication history for a branch.",
    ),
    "run_forward": (Forward, True, "Queue a bounded rules-v1 forward simulation."),
    "run_backward": (
        Backward,
        True,
        "Queue bounded model-conditional goal search; not a probability.",
    ),
    "branch_fork": (Fork, True, "Queue a verified continuation at an actual recorded tick."),
    "branch_compare": (Compare, False, "Compare branches with identical frozen specifications."),
    "branch_export": (ById, False, "Export a versioned, replayable JSON bundle."),
    "branch_import": (
        Import,
        True,
        "Validate digest, provenance and forward replay before import.",
    ),
    "job_get": (ById, False, "Read durable job status and result."),
    "job_cancel": (
        ById,
        True,
        "Cancel queued/running work; prevent result commit, stop worker compute.",
    ),
    "workspace_attach": (
        Attach,
        True,
        "Attach/create shared desired workspace state, not a browser acknowledgement.",
    ),
    "workspace_get": (
        ById,
        False,
        "Read desired workspace state; does not prove browser rendering.",
    ),
    "workspace_update": (
        WorkspaceUpdate,
        True,
        "CAS update desired branch/tick/panel; not browser-acknowledged rendering.",
    ),
}


def now():
    return datetime.now(UTC).isoformat()


def uid():
    return str(uuid.uuid4())


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def compute(payload, connection):
    """Spawned process: no database, network, credentials or filesystem operations."""
    try:
        spec = Scenario.model_validate(payload["spec"])
        start = State.model_validate(payload["start"]) if payload.get("start") else None
        if payload["kind"] == "run_backward":
            result = kernel.search(spec, Goal.model_validate(payload["goal"]), payload["max_nodes"])
            connection.send({"search": result.model_dump(mode="json")})
        else:
            result = kernel.simulate(spec, payload["actions"], start=start)
            if not kernel.validate_trajectory(spec, result, start=start):
                raise ValueError("Forward replay failed")
            connection.send({"trajectory": result.model_dump(mode="json")})
    except Exception as exc:
        connection.send(
            {"error": str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__}
        )
    finally:
        connection.close()


class Service:
    def __init__(self, data_dir, *, start_worker=True):
        self.store = Store(data_dir)
        self.stopping = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        with self.store.transaction() as db:
            if not db.execute("SELECT 1 FROM scenario LIMIT 1").fetchone():
                spec = Scenario(name="Fictional supply chain / 虚构供应链")
                db.execute(
                    "INSERT INTO scenario VALUES(?,?,?)", (uid(), 1, canonical(spec.model_dump()))
                )
            db.execute(
                "UPDATE jobs SET status='interrupted',error='Worker restarted during computation' "
                "WHERE status='running'"
            )
        if start_worker:
            self.start()

    @staticmethod
    def capabilities():
        return [
            {
                "name": name,
                "description": description,
                "input_schema": model.model_json_schema(),
                "mutating": mutating,
            }
            for name, (model, mutating, description) in OPERATIONS.items()
        ]

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._worker, name="lab-worker", daemon=True)
            self.thread.start()

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError("Worker did not stop; data directory ownership retained")
        self.store.close()

    def execute(self, name, arguments, request_id=None):
        if name not in OPERATIONS:
            raise OperationError("not_found", "Unknown operation", 404)
        model, mutating, _ = OPERATIONS[name]
        try:
            value = model.model_validate(arguments)
            args_json = canonical(value.model_dump(exclude_unset=True, mode="json"))
            if mutating and (not isinstance(request_id, str) or not 1 <= len(request_id) <= 128):
                raise OperationError(
                    "request_id_required", "Mutation requires request_id (1..128 characters)"
                )
            with self.store.transaction() as db:
                if mutating:
                    old = db.execute(
                        "SELECT * FROM idempotency WHERE operation=? AND request_id=?",
                        (name, request_id),
                    ).fetchone()
                    if old:
                        if old["arguments_json"] != args_json:
                            raise OperationError(
                                "idempotency_conflict",
                                "request_id reused with different arguments",
                                409,
                            )
                        return json.loads(old["result_json"])
                result = self._dispatch(db, name, value)
                if mutating:
                    db.execute(
                        "INSERT INTO idempotency VALUES(?,?,?,?)",
                        (name, request_id, args_json, canonical(result)),
                    )
            self.wake.set()
            return result
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise OperationError("validation", str(exc)[:1000]) from exc

    @staticmethod
    def _row(db, table, id):
        # table is internal-only, never an operation argument.
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
        if row is None:
            raise OperationError("not_found", f"{table} not found", 404)
        return row

    def _scenario(self, db, id):
        row = self._row(db, "scenario", id)
        return {"id": row["id"], "revision": row["revision"], "spec": json.loads(row["spec_json"])}

    def _branch(self, db, id):
        return json.loads(self._row(db, "branch", id)["branch_json"])

    def _job(self, db, id):
        row = self._row(db, "jobs", id)
        return {
            "id": id,
            "kind": row["kind"],
            "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
        }

    def _workspace(self, db, id):
        row = self._row(db, "workspace", id)
        state = json.loads(row["state_json"])
        if not state.get("scenario_id"):
            state["scenario_id"] = (
                self._branch(db, state["branch_id"])["scenario_id"]
                if state["branch_id"]
                else db.execute("SELECT id FROM scenario ORDER BY rowid LIMIT 1").fetchone()[0]
            )
        state.setdefault("compare_branch_id", None)
        return {"id": id, "revision": row["revision"], **state}

    @staticmethod
    def _save_branch(db, branch):
        db.execute(
            "INSERT INTO branch VALUES(?,?,?,?,?,?,?)",
            (
                branch["id"],
                branch["scenario_id"],
                branch["parent_id"],
                branch["fork_tick"],
                branch["name"],
                canonical(branch["trajectory"]),
                canonical(branch),
            ),
        )
        return branch

    def _verify_branch(self, branch):
        spec, trajectory = branch.spec, branch.trajectory
        # The rule label is a pure function of the frozen specification. A bundle
        # that claims the pre-disturbance rules while carrying a schedule (or a
        # loss) is rejected rather than silently relabelled.
        expected_rules = kernel.rule_version_for(spec)
        if trajectory.rule_version != expected_rules:
            raise ValueError(
                "Declared rule version does not match the frozen specification "
                f"({trajectory.rule_version} vs {expected_rules})"
            )
        if branch.provenance.rule_version != expected_rules:
            raise ValueError("Branch provenance rule version contradicts its specification")
        prefix = branch.provenance.prefix_actions
        state = kernel.initial_state(spec)
        for action in prefix:
            state = kernel.step(spec, state, action).state
        if not trajectory.frames or trajectory.frames[0].state != state:
            raise ValueError(
                "Starting state is not reachable from the scenario and recorded prefix"
            )
        if branch.fork_tick is not None and branch.fork_tick != state.tick:
            raise ValueError("fork_tick does not match replay start")
        if state.tick and branch.fork_tick is None:
            raise ValueError("Continuation requires a fork_tick")
        if not kernel.validate_trajectory(spec, trajectory, start=state):
            raise ValueError("Trajectory replay failed")
        replay = kernel.simulate(spec, trajectory.actions, goal=branch.provenance.goal, start=state)
        if replay.model_dump() != trajectory.model_dump():
            raise ValueError("Trajectory metadata, goal or replay mismatch")

    def _observation(self, db, id):
        row = self._row(db, "observation", id)
        # JSON validation accepts JSON shipment arrays while preserving the core's
        # immutable tuple representation. Never trust persisted hashes implicitly.
        observation = ObservationEnvelope.model_validate_json(row["observation_json"])
        observation.verify_integrity()
        return {"id": id, "observation": observation.model_dump(mode="json")}

    def _observation_source(self, db, branch_id, tick):
        branch = Branch.model_validate(self._branch(db, branch_id))
        self._verify_branch(branch)
        state = next((f.state for f in branch.trajectory.frames if f.state.tick == tick), None)
        if state is None:
            raise ValueError("Tick is not a recorded frame")
        context = ObservationContext(
            branch_id=branch.id,
            scenario_revision=branch.scenario_revision,
            spec_hash=digest(branch.spec.model_dump(mode="json")),
        )
        return branch.spec, state, context

    @staticmethod
    def _adjudication(row):
        result = SavedAdjudication.model_validate_json(row["result_json"])
        if (
            result.id != row["id"]
            or result.record.record_id != row["id"]
            or result.observation_id != row["observation_id"]
            or result.record.context.branch_id != row["branch_id"]
        ):
            raise ValueError("Adjudication relational identity mismatch")
        if kernel.state_hash(result.next_state) != result.record.post_state_hash:
            raise ValueError("Adjudication next-state hash mismatch")
        return result.model_dump(mode="json")

    @staticmethod
    def _record_capacity(db, table, branch_id):
        # Only fixed internal table names reach this helper.
        if (
            db.execute(f"SELECT count(*) FROM {table} WHERE branch_id=?", (branch_id,)).fetchone()[
                0
            ]
            >= 100
        ):
            raise OperationError("record_limit", f"At most 100 {table} records per branch", 409)

    def _dispatch(self, db, name, a):
        if name == "observation_create":
            _, state, context = self._observation_source(db, a.branch_id, a.tick)
            self._record_capacity(db, "observation", a.branch_id)
            observation = observe_envelope(state, a.actor_id, a.role, context=context)
            id = uid()
            db.execute(
                "INSERT INTO observation VALUES(?,?,?)",
                (id, a.branch_id, canonical(observation.model_dump(mode="json"))),
            )
            return self._observation(db, id)
        if name == "observation_get":
            return self._observation(db, a.id)
        if name == "adjudication_create":
            row = self._row(db, "observation", a.observation_id)
            observation = ObservationEnvelope.model_validate_json(row["observation_json"])
            spec, state, context = self._observation_source(db, row["branch_id"], observation.tick)
            self._record_capacity(db, "adjudication", row["branch_id"])
            id = uid()
            record, next_state = adjudicate(
                spec,
                state,
                observation,
                a.proposal,
                context=context,
                adjudicator_id=a.adjudicator_id,
                record_id=id,
            )
            result = {
                "id": id,
                "observation_id": a.observation_id,
                "record": record.model_dump(mode="json"),
                "next_state": next_state.model_dump(mode="json"),
            }
            db.execute(
                "INSERT INTO adjudication VALUES(?,?,?,?)",
                (id, row["branch_id"], a.observation_id, canonical(result)),
            )
            return result
        if name == "adjudication_get":
            return self._adjudication(self._row(db, "adjudication", a.id))
        if name == "adjudication_list":
            self._branch(db, a.branch_id)
            return {
                "items": [
                    self._adjudication(row)
                    for row in db.execute(
                        "SELECT * FROM adjudication WHERE branch_id=? ORDER BY rowid",
                        (a.branch_id,),
                    )
                ]
            }
        if name == "scenario_list":
            return {
                "items": [
                    self._scenario(db, row[0])
                    for row in db.execute("SELECT id FROM scenario ORDER BY rowid")
                ]
            }
        if name == "scenario_create":
            id = uid()
            db.execute(
                "INSERT INTO scenario VALUES(?,?,?)", (id, 1, canonical(a.spec.model_dump()))
            )
            return self._scenario(db, id)
        if name == "scenario_update":
            current = self._scenario(db, a.id)
            if current["revision"] >= 2_147_483_647:
                raise OperationError(
                    "revision_limit", "Create a new scenario at revision limit", 409
                )
            if current["revision"] != a.revision:
                raise OperationError("stale_revision", "Scenario revision changed", 409)
            db.execute(
                "UPDATE scenario SET revision=revision+1,spec_json=? WHERE id=?",
                (canonical(a.spec.model_dump()), a.id),
            )
            return self._scenario(db, a.id)
        if name == "branch_list":
            self._scenario(db, a.scenario_id)
            return {
                "items": [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT branch_json FROM branch WHERE scenario_id=? ORDER BY rowid",
                        (a.scenario_id,),
                    )
                ]
            }
        if name == "branch_get":
            return self._branch(db, a.id)
        if name in ("run_forward", "run_backward", "branch_fork"):
            if (
                db.execute(
                    "SELECT count(*) FROM jobs WHERE status IN ('queued','running')"
                ).fetchone()[0]
                >= 32
            ):
                raise OperationError("queue_full", "At most 32 outstanding jobs", 409)
            payload = a.model_dump(mode="json")
            payload["kind"] = name
            payload["prefix_actions"] = []
            if name == "branch_fork":
                parent = Branch.model_validate(self._branch(db, a.id))
                self._verify_branch(parent)
                index = next(
                    (i for i, f in enumerate(parent.trajectory.frames) if f.state.tick == a.tick),
                    None,
                )
                if index is None:
                    raise ValueError("Tick is not a recorded frame")
                payload.update(
                    spec=parent.spec.model_dump(),
                    scenario_id=parent.scenario_id,
                    scenario_revision=parent.scenario_revision,
                    parent_id=parent.id,
                    fork_tick=a.tick,
                    start=parent.trajectory.frames[index].state.model_dump(),
                    prefix_actions=parent.provenance.prefix_actions
                    + parent.trajectory.actions[:index],
                )
            else:
                scenario = self._scenario(db, a.scenario_id)
                payload.update(
                    spec=scenario["spec"],
                    scenario_revision=scenario["revision"],
                    parent_id=None,
                    fork_tick=None,
                )
            if name != "run_backward":
                remaining = payload["spec"]["horizon"] - payload.get("start", {}).get("tick", 0)
                if len(a.actions) > remaining:
                    raise ValueError("Too many actions for remaining horizon")
            id = uid()
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?, ?,NULL,NULL,?)",
                (id, name, "queued", canonical(payload), now()),
            )
            return self._job(db, id)
        if name == "branch_compare":
            left, right = self._branch(db, a.left_id), self._branch(db, a.right_id)
            if left["spec"] != right["spec"]:
                raise OperationError("incompatible_scenarios", "Frozen specifications differ", 409)
            return {
                "left": left,
                "right": right,
                "delta": {
                    key: right["trajectory"]["final_state"][key]
                    - left["trajectory"]["final_state"][key]
                    for key in ("inventory", "cash", "shortage", "spent", "delivered")
                },
            }
        if name == "branch_export":
            branch = self._branch(db, a.id)
            return {
                "schema_version": "tianji.lab.bundle.v1",
                "branch": branch,
                "digest": digest(branch),
            }
        if name == "branch_import":
            canonical(a.bundle)
            if (
                set(a.bundle) != {"schema_version", "branch", "digest"}
                or a.bundle["schema_version"] != "tianji.lab.bundle.v1"
            ):
                raise ValueError("Unsupported bundle schema")
            if a.bundle["digest"] != digest(a.bundle["branch"]):
                raise ValueError("Bundle digest mismatch")
            branch = Branch.model_validate(a.bundle["branch"])
            self._verify_branch(branch)
            imported = branch.model_dump(mode="json")
            imported.update(id=uid(), parent_id=None, mode="import", created_at=now())
            imported["provenance"]["imported_parent_id"] = (
                branch.parent_id or branch.provenance.imported_parent_id
            )
            # Preserve frozen assumptions, even when an existing scenario has been revised.
            if not db.execute(
                "SELECT 1 FROM scenario WHERE id=?", (branch.scenario_id,)
            ).fetchone():
                new_scenario_id = uid()
                db.execute(
                    "INSERT INTO scenario VALUES(?,?,?)",
                    (
                        new_scenario_id,
                        branch.scenario_revision,
                        canonical(branch.spec.model_dump()),
                    ),
                )
                imported["scenario_id"] = new_scenario_id
            return self._save_branch(db, imported)
        if name == "job_get":
            return self._job(db, a.id)
        if name == "job_cancel":
            self._row(db, "jobs", a.id)
            db.execute(
                "UPDATE jobs SET status='cancelled',error='Cancelled; no result committed' "
                "WHERE id=? AND status IN ('queued','running')",
                (a.id,),
            )
            return self._job(db, a.id)
        if name == "workspace_attach":
            if a.id:
                result = self._workspace(db, a.id)
                db.execute("UPDATE workspace SET last_seen=? WHERE id=?", (now(), a.id))
                return result
            id = uid()
            db.execute(
                "INSERT INTO workspace VALUES(?,?,?,?)",
                (id, 1, canonical({"branch_id": None, "tick": 0, "panel": "timeline"}), now()),
            )
            return self._workspace(db, id)
        if name == "workspace_get":
            return self._workspace(db, a.id)
        if name == "workspace_update":
            old = self._workspace(db, a.id)
            if old["revision"] >= 2_147_483_647:
                raise OperationError(
                    "revision_limit", "Create a new workspace at revision limit", 409
                )
            if a.revision != old["revision"]:
                raise OperationError(
                    "stale_revision", "Workspace revision changed; reload before updating", 409
                )
            state_keys = ("scenario_id", "branch_id", "compare_branch_id", "tick", "panel")
            # The published JSON schema accepts null for every field, so null on a
            # non-nullable field means "unchanged", matching an omitted field;
            # branch/comparison null clears that selection instead.
            provided = {
                key
                for key in state_keys
                if key in a.model_fields_set
                and (getattr(a, key) is not None or key in ("branch_id", "compare_branch_id"))
            }
            state = {k: old[k] for k in state_keys}
            for key in provided:
                state[key] = getattr(a, key)
            self._scenario(db, state["scenario_id"])
            if "scenario_id" in provided and a.scenario_id != old["scenario_id"]:
                if "branch_id" not in provided:
                    state.update(branch_id=None, tick=0)
            if state["branch_id"] != old["branch_id"] and "compare_branch_id" not in provided:
                state["compare_branch_id"] = None
            if "branch_id" in provided and "tick" not in provided:
                state["tick"] = (
                    self._branch(db, state["branch_id"])["trajectory"]["frames"][0]["state"]["tick"]
                    if state["branch_id"]
                    else 0
                )
            if state["branch_id"]:
                branch = self._branch(db, state["branch_id"])
                if "scenario_id" in provided and branch["scenario_id"] != state["scenario_id"]:
                    raise ValueError("Branch does not belong to selected scenario")
                state["scenario_id"] = branch["scenario_id"]
                if state["tick"] not in [
                    f["state"]["tick"] for f in branch["trajectory"]["frames"]
                ]:
                    raise ValueError("Workspace tick is not a recorded frame")
            elif state["tick"] != 0:
                raise ValueError("Workspace without a branch must use tick zero")
            if state["compare_branch_id"]:
                if not state["branch_id"]:
                    raise ValueError("Comparison requires a selected branch")
                other = self._branch(db, state["compare_branch_id"])
                if other["spec"] != self._branch(db, state["branch_id"])["spec"]:
                    raise OperationError(
                        "incompatible_scenarios", "Frozen specifications differ", 409
                    )
            db.execute(
                "UPDATE workspace SET revision=revision+1,state_json=?,last_seen=? WHERE id=?",
                (canonical(state), now(), a.id),
            )
            return self._workspace(db, a.id)
        raise OperationError("not_found", "Unknown operation", 404)

    def _worker(self):
        context = multiprocessing.get_context("spawn")
        while not self.stopping.is_set():
            with self.store.transaction() as db:
                row = db.execute(
                    "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1"
                ).fetchone()
                if row:
                    db.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
            if not row:
                self.wake.wait(0.2)
                self.wake.clear()
                continue
            payload = json.loads(row["input_json"])
            receive, send = context.Pipe(duplex=False)
            process = context.Process(target=compute, args=(payload, send), daemon=True)
            result = None
            try:
                process.start()
                send.close()
                deadline = time.monotonic() + 30
                while not self.stopping.is_set() and time.monotonic() < deadline:
                    if receive.poll(0.1):
                        result = receive.recv()
                        break
                    with self.store.transaction() as db:
                        if self._job(db, row["id"])["status"] == "cancelled":
                            break
                    if not process.is_alive():
                        break
                if result is None:
                    result = {"error": "Worker stopped or exceeded 30 second execution limit"}
                with self.store.transaction() as db:
                    if self._job(db, row["id"])["status"] != "running":
                        continue
                    if self.stopping.is_set():
                        db.execute(
                            "UPDATE jobs SET status='interrupted',error='Service stopped' "
                            "WHERE id=?",
                            (row["id"],),
                        )
                    elif "error" in result:
                        db.execute(
                            "UPDATE jobs SET status='failed',error=? WHERE id=?",
                            (result["error"], row["id"]),
                        )
                    else:
                        branches = []
                        trajectories = (
                            result["search"]["plans"]
                            if "search" in result
                            else [result["trajectory"]]
                        )
                        for trajectory in trajectories:
                            provenance = Provenance(
                                prefix_actions=payload["prefix_actions"],
                                goal=payload.get("goal"),
                                rule_version=kernel.rule_version_for(payload["spec"]),
                            )
                            branch = Branch(
                                id=uid(),
                                name=payload["name"],
                                scenario_id=payload["scenario_id"],
                                scenario_revision=payload["scenario_revision"],
                                spec=payload["spec"],
                                parent_id=payload["parent_id"],
                                fork_tick=payload["fork_tick"],
                                trajectory=trajectory,
                                mode={
                                    "run_forward": "forward",
                                    "run_backward": "backward",
                                    "branch_fork": "fork",
                                }[row["kind"]],
                                created_at=now(),
                                provenance=provenance,
                            )
                            self._verify_branch(branch)
                            branches.append(self._save_branch(db, branch.model_dump(mode="json")))
                        output = (
                            {"search": result["search"], "branches": branches}
                            if "search" in result
                            else {"branch": branches[0]}
                        )
                        db.execute(
                            "UPDATE jobs SET status='succeeded',result_json=?,error=NULL "
                            "WHERE id=?",
                            (canonical(output), row["id"]),
                        )
            except Exception as exc:
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE jobs SET status='failed',error=? WHERE id=? AND status='running'",
                        (str(exc)[:500], row["id"]),
                    )
            finally:
                if process.pid:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=2)
                receive.close()
                send.close()
