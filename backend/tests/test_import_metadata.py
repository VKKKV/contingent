"""Externally supplied bundle metadata must stay bounded and round-trip safely."""

import copy
import uuid

import pytest
from fastapi.testclient import TestClient

from tianji_lab.api import create_app
from tianji_lab.kernel import simulate
from tianji_lab.models import Scenario
from tianji_lab.service import digest


def bundle():
    spec = Scenario(name="Metadata boundary")
    branch = {
        "id": "external",
        "name": "external",
        "scenario_id": "unknown",
        "scenario_revision": 1,
        "spec": spec.model_dump(),
        "parent_id": "prior-parent",
        "fork_tick": 0,
        "trajectory": simulate(spec, []).model_dump(),
        "mode": "fork",
        "created_at": "external",
    }
    return {"schema_version": "tianji.lab.bundle.v1", "branch": branch, "digest": digest(branch)}


def post(client, name, arguments):
    return client.post(
        f"/api/operations/{name}",
        json={
            "arguments": arguments,
            "request_id": str(uuid.uuid4()),
        },
    )


@pytest.mark.parametrize("revision", [2**100, 2_147_483_648, 0, True])
def test_import_revision_is_bounded_without_partial_commit(tmp_path, revision):
    with TestClient(create_app(tmp_path, token="test", start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer test"
        before = post(client, "scenario_list", {}).json()["data"]
        value = bundle()
        value["branch"]["scenario_revision"] = revision
        value["digest"] = digest(value["branch"])
        response = post(client, "branch_import", {"bundle": value})
        assert response.status_code == 422 and not response.json()["ok"]
        assert post(client, "scenario_list", {}).json()["data"] == before


def test_repeated_import_preserves_parent_provenance_and_revision_limit(tmp_path):
    with TestClient(create_app(tmp_path, token="test", start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer test"
        value = bundle()
        value["branch"]["scenario_revision"] = 2_147_483_647
        value["digest"] = digest(value["branch"])
        first = post(client, "branch_import", {"bundle": value}).json()["data"]
        exported = post(client, "branch_export", {"id": first["id"]}).json()["data"]
        second = post(client, "branch_import", {"bundle": exported}).json()["data"]
        assert first["provenance"]["imported_parent_id"] == "prior-parent"
        assert second["provenance"]["imported_parent_id"] == "prior-parent"
        assert second["trajectory"] == first["trajectory"]
        assert (
            post(
                client,
                "scenario_update",
                {
                    "id": first["scenario_id"],
                    "revision": 2_147_483_647,
                    "spec": first["spec"],
                },
            ).status_code
            == 409
        )
        # A digest alone cannot bless edited events or a false goal assertion.
        forged = copy.deepcopy(exported)
        forged["branch"]["trajectory"]["goal_met"] = True
        forged["digest"] = digest(forged["branch"])
        assert post(client, "branch_import", {"bundle": forged}).status_code == 422


def test_pre_disturbance_bundles_still_import_and_mislabelled_schedules_are_rejected(tmp_path):
    with TestClient(create_app(tmp_path, token="test", start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer test"
        # Emulate a bundle exported before the exogenous-disturbance slice.
        legacy = bundle()
        del legacy["branch"]["spec"]["disturbances"]
        for frame in legacy["branch"]["trajectory"]["frames"]:
            del frame["state"]["lost"]
        del legacy["branch"]["trajectory"]["final_state"]["lost"]
        legacy["digest"] = digest(legacy["branch"])
        imported = post(client, "branch_import", {"bundle": legacy}).json()["data"]
        assert imported["spec"]["disturbances"] == []
        assert imported["trajectory"]["rule_version"] == "supply-chain.v1"
        assert imported["trajectory"]["final_state"]["lost"] == 0
        # A real schedule under the current label imports and keeps the schedule.
        schedule = [{"tick": 2, "kind": "supplier_loss", "amount": 4}]
        spec = Scenario(name="Scheduled import", horizon=3, disturbances=schedule)
        scheduled = bundle()
        scheduled["branch"]["spec"] = spec.model_dump()
        scheduled["branch"]["trajectory"] = simulate(spec, []).model_dump()
        scheduled["branch"]["provenance"] = {"rule_version": "supply-chain.v2"}
        scheduled["digest"] = digest(scheduled["branch"])
        accepted = post(client, "branch_import", {"bundle": scheduled}).json()["data"]
        assert accepted["trajectory"]["rule_version"] == "supply-chain.v2"
        assert accepted["spec"]["disturbances"] == schedule
        assert accepted["trajectory"]["final_state"]["lost"] == 4
        # Claiming the pre-disturbance rules while carrying a schedule is refused,
        # never silently relabelled.
        relabelled = copy.deepcopy(scheduled)
        relabelled["branch"]["trajectory"]["rule_version"] = "supply-chain.v1"
        relabelled["digest"] = digest(relabelled["branch"])
        assert post(client, "branch_import", {"bundle": relabelled}).status_code == 422
        inconsistent = copy.deepcopy(scheduled)
        inconsistent["branch"]["provenance"] = {"rule_version": "supply-chain.v1"}
        inconsistent["digest"] = digest(inconsistent["branch"])
        assert post(client, "branch_import", {"bundle": inconsistent}).status_code == 422
