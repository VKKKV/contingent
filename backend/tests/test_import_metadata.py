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
