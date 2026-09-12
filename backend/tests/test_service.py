import copy
import time
import uuid

import pytest

from tianji_lab import kernel
from tianji_lab.models import Scenario
from tianji_lab.service import OperationError, Service, digest


def call(service, name, **arguments):
    return service.execute(name, arguments, str(uuid.uuid4()))


def finish(service, job):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = call(service, "job_get", id=job["id"])
        if job["status"] not in ("running", "queued"):
            assert job["status"] == "succeeded", job
            return job["result"]
        time.sleep(0.03)
    pytest.fail(f"Job timed out: {job}")


@pytest.fixture
def service(tmp_path):
    service = Service(tmp_path)
    yield service
    service.close()


def test_idempotency_revision_and_seed(service):
    assert len(call(service, "scenario_list")["items"]) == 1
    args = {"spec": {"name": "test"}}
    first = service.execute("scenario_create", args, "same")
    assert first == service.execute("scenario_create", args, "same")
    with pytest.raises(OperationError, match="different arguments"):
        service.execute("scenario_create", {"spec": {"name": "other"}}, "same")
    call(service, "scenario_update", id=first["id"], revision=1, spec={"name": "updated"})
    with pytest.raises(OperationError, match="revision changed"):
        call(service, "scenario_update", id=first["id"], revision=1, spec={"name": "stale"})
    with pytest.raises(OperationError, match="request_id"):
        service.execute("scenario_create", args)


def test_forward_backward_frozen_fork_import(service):
    scenario = call(service, "scenario_list")["items"][0]
    forward = finish(service, call(service, "run_forward", scenario_id=scenario["id"], actions=[]))[
        "branch"
    ]
    call(
        service,
        "scenario_update",
        id=scenario["id"],
        revision=1,
        spec={"name": "Changed", "horizon": 3},
    )
    fork = finish(
        service, call(service, "branch_fork", id=forward["id"], tick=2, actions=["order_express"])
    )["branch"]
    assert fork["spec"] == forward["spec"]
    assert fork["trajectory"]["frames"][0]["state"]["tick"] == 2
    assert fork["parent_id"] == forward["id"]
    assert fork["provenance"]["prefix_actions"] == ["wait", "wait"]
    compared = call(service, "branch_compare", left_id=forward["id"], right_id=fork["id"])
    assert compared["delta"]["spent"] == 32
    bundle = call(service, "branch_export", id=fork["id"])
    imported = call(service, "branch_import", bundle=bundle)
    assert imported["trajectory"] == fork["trajectory"]
    assert imported["parent_id"] is None
    assert imported["provenance"]["imported_parent_id"] == forward["id"]
    forged = copy.deepcopy(bundle)
    # Reachable in the same model, but NOT under this bundle's recorded ancestry.
    alternate_start = kernel.step(
        Scenario.model_validate(fork["spec"]),
        kernel.initial_state(Scenario.model_validate(fork["spec"])),
        "order_express",
    ).state
    alternate_start = kernel.step(
        Scenario.model_validate(fork["spec"]), alternate_start, "wait"
    ).state
    forged["branch"]["trajectory"] = kernel.simulate(
        Scenario.model_validate(fork["spec"]), [], start=alternate_start
    ).model_dump()
    forged["digest"] = digest(forged["branch"])
    with pytest.raises(OperationError, match="Starting state"):
        call(service, "branch_import", bundle=forged)
    initial_forgery = call(service, "branch_export", id=forward["id"])
    initial_forgery["branch"]["trajectory"]["frames"][0]["state"]["inventory"] += 1
    initial_forgery["digest"] = digest(initial_forgery["branch"])
    with pytest.raises(OperationError, match="Starting state"):
        call(service, "branch_import", bundle=initial_forgery)
    backward = finish(
        service, call(service, "run_backward", scenario_id=scenario["id"], goal={}, max_nodes=5000)
    )
    assert backward["search"]["status"] == "found"
    assert all(b["trajectory"]["goal_met"] for b in backward["branches"])
    with pytest.raises(OperationError, match="specifications differ"):
        call(
            service, "branch_compare", left_id=forward["id"], right_id=backward["branches"][0]["id"]
        )


def test_workspace_cas_and_tick(service):
    workspace = call(service, "workspace_attach")
    updated = call(service, "workspace_update", id=workspace["id"], revision=1, panel="goal")
    assert updated["revision"] == 2
    assert call(service, "workspace_get", id=workspace["id"]) == updated
    with pytest.raises(OperationError, match="revision changed"):
        call(service, "workspace_update", id=workspace["id"], revision=1, panel="compare")
    with pytest.raises(OperationError, match="tick zero"):
        call(service, "workspace_update", id=workspace["id"], revision=2, tick=1)


def test_queued_cancel_restart_and_bounded_queue(tmp_path):
    service = Service(tmp_path, start_worker=False)
    scenario = call(service, "scenario_list")["items"][0]
    job = call(service, "run_forward", scenario_id=scenario["id"], actions=[])
    assert call(service, "job_cancel", id=job["id"])["status"] == "cancelled"
    running = call(service, "run_forward", scenario_id=scenario["id"], actions=[])
    queued = call(service, "run_forward", scenario_id=scenario["id"], actions=[])
    with service.store.transaction() as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (running["id"],))
    service.close()
    restarted = Service(tmp_path)
    try:
        assert call(restarted, "job_get", id=running["id"])["status"] == "interrupted"
        assert finish(restarted, queued)["branch"]
        assert call(restarted, "job_get", id=job["id"])["status"] == "cancelled"
    finally:
        restarted.close()
    bounded = Service(tmp_path, start_worker=False)
    for _ in range(32):
        call(bounded, "run_forward", scenario_id=scenario["id"], actions=[])
    with pytest.raises(OperationError, match="32 outstanding"):
        call(bounded, "run_forward", scenario_id=scenario["id"], actions=[])
    bounded.close()
