"""Durable director-only observation and adjudication through the real service."""

import copy
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tianji_lab import kernel
from tianji_lab.api import create_app
from tianji_lab.models import Scenario, State
from tianji_lab.service import OperationError, Service, digest


def call(service, name, **arguments):
    return service.execute(name, arguments, str(uuid.uuid4()))


def finish(service, job):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = call(service, "job_get", id=job["id"])
        if job["status"] not in ("queued", "running"):
            assert job["status"] == "succeeded", job
            return job["result"]["branch"]
        time.sleep(0.02)
    pytest.fail("job timed out")


@pytest.fixture
def lab(tmp_path):
    service = Service(tmp_path)
    scenario = call(service, "scenario_list")["items"][0]
    branch = finish(service, call(service, "run_forward", scenario_id=scenario["id"], actions=[]))
    yield service, branch
    service.close()


def observation(service, branch, role="retailer", tick=0):
    return call(
        service,
        "observation_create",
        branch_id=branch["id"],
        tick=tick,
        actor_id=f"{role}-1",
        role=role,
    )


def proposal(saved, action="wait"):
    view = saved["observation"]
    return {
        "actor_id": view["actor_id"],
        "role": view["role"],
        "action": action,
        "observation_hash": view["observation_hash"],
        "policy_id": "manual.director.v1",
    }


def adjudication(service, saved, action="wait"):
    return call(
        service,
        "adjudication_create",
        observation_id=saved["id"],
        proposal=proposal(saved, action),
        adjudicator_id="referee-1",
    )


def test_durable_preview_is_forward_exact_and_does_not_mutate_branch(lab, tmp_path):
    service, branch = lab
    workspace = call(service, "workspace_attach")
    saved = observation(service, branch)
    assert call(service, "observation_get", id=saved["id"]) == saved
    result = adjudication(service, saved, "order_express")
    assert result["record"]["status"] == "accepted"
    expected = kernel.step(
        Scenario.model_validate(branch["spec"]),
        State.model_validate(branch["trajectory"]["frames"][0]["state"]),
        "order_express",
    )
    assert result["next_state"] == expected.state.model_dump(mode="json")
    assert result["record"]["post_state_hash"] == expected.state_hash
    assert call(service, "adjudication_get", id=result["id"]) == result
    assert call(service, "adjudication_list", branch_id=branch["id"])["items"] == [result]
    assert call(service, "branch_get", id=branch["id"]) == branch
    assert call(service, "branch_list", scenario_id=branch["scenario_id"])["items"] == [branch]
    assert call(service, "workspace_get", id=workspace["id"]) == workspace
    with service.store.transaction() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    service.close()
    restarted = Service(tmp_path, start_worker=False)
    try:
        assert call(restarted, "observation_get", id=saved["id"]) == saved
        assert call(restarted, "adjudication_get", id=result["id"]) == result
    finally:
        restarted.close()


def test_observation_and_adjudication_idempotency_and_rollback(lab):
    service, branch = lab
    args = {"branch_id": branch["id"], "tick": 0, "actor_id": "retailer", "role": "retailer"}
    saved = service.execute("observation_create", args, "same-observation")
    assert service.execute("observation_create", args, "same-observation") == saved
    with pytest.raises(OperationError) as conflict:
        service.execute("observation_create", {**args, "tick": 1}, "same-observation")
    assert conflict.value.code == "idempotency_conflict"
    args = {"observation_id": saved["id"], "proposal": proposal(saved), "adjudicator_id": "referee"}
    result = service.execute("adjudication_create", args, "same-adjudication")
    assert service.execute("adjudication_create", args, "same-adjudication") == result
    with pytest.raises(OperationError) as conflict:
        service.execute(
            "adjudication_create", {**args, "adjudicator_id": "other"}, "same-adjudication"
        )
    assert conflict.value.code == "idempotency_conflict"
    with pytest.raises(OperationError):
        service.execute("adjudication_create", {**args, "adjudicator_id": "retailer"}, "invalid")
    assert call(service, "adjudication_list", branch_id=branch["id"])["items"] == [result]
    with service.store.transaction() as db:
        assert (
            db.execute("SELECT count(*) FROM idempotency WHERE request_id='invalid'").fetchone()[0]
            == 0
        )


def test_multiple_roles_are_separate_proposals_and_supplier_cannot_spend(lab):
    service, branch = lab
    retailer, supplier = observation(service, branch), observation(service, branch, "supplier")
    retail_projection = retailer["observation"]["projection"]
    supplier_projection = supplier["observation"]["projection"]
    assert set(retail_projection) == {
        "tick",
        "inventory",
        "cash",
        "delivered",
        "shortage",
        "spent",
        "shipments",
    }
    assert set(supplier_projection) == {"tick", "supplier_stock", "shipments"}
    assert "pre_state_hash" not in str(retailer)
    accepted = adjudication(service, retailer, "order_standard")
    rejected = adjudication(service, supplier, "order_standard")
    assert accepted["record"]["status"] == "accepted"
    assert rejected["record"]["status"] == "rejected"
    assert rejected["next_state"] == branch["trajectory"]["frames"][0]["state"]
    assert rejected["record"]["post_state_hash"] == rejected["record"]["pre_state_hash"]
    assert call(service, "adjudication_list", branch_id=branch["id"])["items"] == [
        accepted,
        rejected,
    ]
    assert call(service, "branch_get", id=branch["id"]) == branch


def test_frozen_revision_fork_ticks_and_imported_identity(lab):
    service, branch = lab
    saved = observation(service, branch)
    call(
        service,
        "scenario_update",
        id=branch["scenario_id"],
        revision=1,
        spec={"name": "live revision changed", "initial_cash": 0},
    )
    assert adjudication(service, saved, "order_express")["record"]["status"] == "accepted"
    assert saved["observation"]["context"]["scenario_revision"] == 1
    fork = finish(service, call(service, "branch_fork", id=branch["id"], tick=2, actions=[]))
    with pytest.raises(OperationError, match="recorded frame"):
        observation(service, fork, tick=0)
    at_fork = observation(service, fork, tick=2)
    assert at_fork["observation"]["tick"] == 2
    imported = call(
        service, "branch_import", bundle=call(service, "branch_export", id=branch["id"])
    )
    imported_observation = observation(service, imported)
    assert (
        imported_observation["observation"]["observation_hash"]
        != saved["observation"]["observation_hash"]
    )
    invalid = call(
        service,
        "adjudication_create",
        observation_id=imported_observation["id"],
        proposal=proposal(saved),
        adjudicator_id="referee",
    )
    assert invalid["record"]["status"] == "rejected"
    assert (
        call(service, "adjudication_list", branch_id=branch["id"])["items"][0]["record"]["status"]
        == "accepted"
    )
    assert call(service, "adjudication_list", branch_id=fork["id"])["items"] == []


def test_horizon_and_illegal_orders_are_rejections_without_substitution(lab):
    service, branch = lab
    terminal = observation(service, branch, tick=branch["spec"]["horizon"])
    result = adjudication(service, terminal)
    assert result["record"]["status"] == "rejected"
    assert result["next_state"] == branch["trajectory"]["final_state"]
    assert result["record"]["action"] == "wait"


@pytest.mark.parametrize("table", ["observation", "adjudication"])
def test_record_caps_are_atomic_and_reads_bounded(lab, table):
    service, branch = lab
    saved = observation(service, branch)
    if table == "observation":
        for _ in range(99):
            observation(service, branch)
        args = {"branch_id": branch["id"], "tick": 0, "actor_id": "r", "role": "retailer"}
        name = "observation_create"
    else:
        for _ in range(100):
            adjudication(service, saved)
        args = {
            "observation_id": saved["id"],
            "proposal": proposal(saved),
            "adjudicator_id": "referee",
        }
        name = "adjudication_create"
        assert len(call(service, "adjudication_list", branch_id=branch["id"])["items"]) == 100
    with pytest.raises(OperationError) as limit:
        service.execute(name, args, "over-limit")
    assert limit.value.status == 409 and limit.value.code == "record_limit"
    with service.store.transaction() as db:
        assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 100
        assert (
            db.execute("SELECT count(*) FROM idempotency WHERE request_id='over-limit'").fetchone()[
                0
            ]
            == 0
        )


def test_strict_validation_and_missing_objects(lab):
    service, branch = lab
    for patch in (
        {"role": "director"},
        {"tick": True},
        {"actor_id": ""},
        {"state": {}},
        {"tick": 11},
    ):
        args = {"branch_id": branch["id"], "tick": 0, "actor_id": "r", "role": "retailer", **patch}
        with pytest.raises(OperationError) as error:
            service.execute("observation_create", args, str(uuid.uuid4()))
        assert error.value.code == "validation"
    for operation, args in [
        ("observation_get", {"id": "missing"}),
        ("adjudication_get", {"id": "missing"}),
        ("adjudication_list", {"branch_id": "missing"}),
    ]:
        with pytest.raises(OperationError) as error:
            call(service, operation, **args)
        assert error.value.status == 404
    saved = observation(service, branch)
    malformed = proposal(saved)
    malformed["actor_id"] = "another actor"
    with pytest.raises(OperationError):
        call(
            service,
            "adjudication_create",
            observation_id=saved["id"],
            proposal=malformed,
            adjudicator_id="referee",
        )
    assert call(service, "adjudication_list", branch_id=branch["id"])["items"] == []


def test_rejected_retailer_order_and_tampered_persisted_observation(lab):
    service, branch = lab
    scenario = call(service, "scenario_create", spec={"name": "No cash", "initial_cash": 0})
    poor_branch = finish(
        service, call(service, "run_forward", scenario_id=scenario["id"], actions=[])
    )
    saved = observation(service, poor_branch)
    result = adjudication(service, saved, "order_express")
    assert result["record"]["status"] == "rejected"
    assert "kernel rejected" in result["record"]["reason"]
    assert result["next_state"] == poor_branch["trajectory"]["frames"][0]["state"]
    assert result["record"]["action"] == "order_express"
    assert call(service, "branch_get", id=poor_branch["id"]) == poor_branch
    # A database edit is not a supported API input, but readback must not certify
    # a hash-bearing observation that no longer matches its recorded projection.
    from tianji_lab.store import canonical

    corrupted = copy.deepcopy(saved["observation"])
    corrupted["projection"]["cash"] = 123
    with service.store.transaction() as db:
        db.execute(
            "UPDATE observation SET observation_json=? WHERE id=?",
            (canonical(corrupted), saved["id"]),
        )
    with pytest.raises(OperationError, match="hash mismatch"):
        call(service, "observation_get", id=saved["id"])
    rejected = adjudication(service, saved)
    assert rejected["record"]["status"] == "rejected"
    assert call(service, "adjudication_list", branch_id=branch["id"])["items"] == []


@pytest.mark.parametrize(
    "field", ["reason", "state", "id", "observation_id", "record_id", "branch_id"]
)
def test_corrupt_adjudication_readback_fails_closed(lab, field):
    from tianji_lab.store import canonical

    service, branch = lab
    saved = observation(service, branch)
    result = adjudication(service, saved)
    corrupted = copy.deepcopy(result)
    if field == "reason":
        corrupted["record"]["reason"] = "corrupted reason"
    elif field == "state":
        corrupted["next_state"]["cash"] += 1
    elif field in ("id", "observation_id"):
        corrupted[field] = "different"
    else:
        # A self-consistent record digest cannot override relational identity.
        if field == "branch_id":
            corrupted["record"]["context"]["branch_id"] = "different"
        else:
            corrupted["record"]["record_id"] = "different"
        corrupted["record"]["record_hash"] = digest(
            {k: v for k, v in corrupted["record"].items() if k != "record_hash"}
        )
    with service.store.transaction() as db:
        db.execute(
            "UPDATE adjudication SET result_json=? WHERE id=?", (canonical(corrupted), result["id"])
        )
    for name, args in [
        ("adjudication_get", {"id": result["id"]}),
        ("adjudication_list", {"branch_id": branch["id"]}),
    ]:
        with pytest.raises(OperationError) as error:
            call(service, name, **args)
        assert error.value.code == "validation"


def test_http_projection_allowlists_and_real_preview(tmp_path):
    with TestClient(create_app(tmp_path, token="test-only")) as client:
        service = client.app.state.service
        scenario = call(service, "scenario_list")["items"][0]
        branch = finish(
            service, call(service, "run_forward", scenario_id=scenario["id"], actions=[])
        )
        args = {"branch_id": branch["id"], "tick": 0, "actor_id": "retailer-1", "role": "retailer"}
        path = "/api/operations/observation_create"
        assert (
            client.post(path, json={"arguments": args, "request_id": "unauth"}).status_code == 401
        )
        client.headers["Authorization"] = "Bearer test-only"
        response = client.post(path, json={"arguments": args, "request_id": "http"})
        assert response.status_code == 200
        saved = response.json()["data"]
        assert set(saved) == {"id", "observation"}
        assert set(saved["observation"]["projection"]) == {
            "tick",
            "inventory",
            "cash",
            "delivered",
            "shortage",
            "spent",
            "shipments",
        }
        args = {**args, "actor_id": "supplier-1", "role": "supplier"}
        supplier = client.post(
            path, json={"arguments": args, "request_id": "http-supplier"}
        ).json()["data"]
        assert set(supplier["observation"]["projection"]) == {"tick", "supplier_stock", "shipments"}
        body = {
            "observation_id": supplier["id"],
            "proposal": proposal(supplier, "order_express"),
            "adjudicator_id": "referee",
        }
        adjudicated = client.post(
            "/api/operations/adjudication_create",
            json={"arguments": body, "request_id": "http-adjudicate"},
        )
        assert adjudicated.status_code == 200
        result = adjudicated.json()["data"]
        assert result["record"]["status"] == "rejected"
        readback = client.post(
            "/api/operations/adjudication_get", json={"arguments": {"id": result["id"]}}
        )
        assert readback.json()["data"] == result
        forged = copy.deepcopy(body)
        forged["proposal"]["role"] = "director"
        assert (
            client.post(
                "/api/operations/adjudication_create",
                json={"arguments": forged, "request_id": "forged"},
            ).status_code
            == 422
        )
