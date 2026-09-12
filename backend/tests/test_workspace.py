"""Semantic workspace parity includes empty scenarios and comparison targets."""

import time
import uuid

import pytest

from tianji_lab.service import OperationError, Service


def test_explicit_null_equals_omitted_for_non_nullable_fields(tmp_path):
    service = Service(tmp_path)

    def op(name, **args):
        return service.execute(name, args, str(uuid.uuid4()))

    def run(scenario_id):
        job = op("run_forward", scenario_id=scenario_id, actions=[])
        deadline = time.monotonic() + 10
        while job["status"] in ("queued", "running"):
            assert time.monotonic() < deadline
            time.sleep(0.02)
            job = op("job_get", id=job["id"])
        assert job["status"] == "succeeded", job
        return job["result"]["branch"]

    try:
        scenario = op("scenario_list")["items"][0]
        ws = op("workspace_attach")
        unchanged = op(
            "workspace_update",
            id=ws["id"],
            revision=ws["revision"],
            scenario_id=None,
            tick=None,
            panel=None,
        )
        for key in ("scenario_id", "branch_id", "compare_branch_id", "tick", "panel"):
            assert unchanged[key] == ws[key], key
        left = run(scenario["id"])
        ws = op(
            "workspace_update",
            id=ws["id"],
            revision=unchanged["revision"],
            branch_id=left["id"],
            tick=None,
        )
        assert ws["branch_id"] == left["id"] and ws["tick"] == 0
        ws = op("workspace_update", id=ws["id"], revision=ws["revision"], tick=3)
        assert ws["tick"] == 3
        ws = op("workspace_update", id=ws["id"], revision=ws["revision"], branch_id=None)
        assert ws["branch_id"] is None and ws["tick"] == 0 and ws["compare_branch_id"] is None
    finally:
        service.close()


def test_workspace_scenario_and_comparison_selection(tmp_path):
    service = Service(tmp_path)

    def op(name, **args):
        return service.execute(name, args, str(uuid.uuid4()))

    def run(id):
        job = op("run_forward", scenario_id=id, actions=[])
        deadline = time.monotonic() + 10
        while job["status"] in ("queued", "running"):
            assert time.monotonic() < deadline
            time.sleep(0.02)
            job = op("job_get", id=job["id"])
        assert job["status"] == "succeeded", job
        return job["result"]["branch"]

    try:
        initial = op("scenario_list")["items"][0]
        empty = op("scenario_create", spec={"name": "Empty selected scenario"})
        ws = op("workspace_attach")
        ws = op("workspace_update", id=ws["id"], revision=ws["revision"], scenario_id=empty["id"])
        assert ws["scenario_id"] == empty["id"] and ws["branch_id"] is None
        left, right = run(initial["id"]), run(initial["id"])
        ws = op(
            "workspace_update",
            id=ws["id"],
            revision=ws["revision"],
            branch_id=left["id"],
            compare_branch_id=right["id"],
            tick=3,
            panel="compare",
        )
        assert ws["scenario_id"] == initial["id"] and ws["compare_branch_id"] == right["id"]
        assert op("workspace_get", id=ws["id"]) == ws
        with pytest.raises(OperationError, match="does not belong"):
            op(
                "workspace_update",
                id=ws["id"],
                revision=ws["revision"],
                scenario_id=empty["id"],
                branch_id=left["id"],
            )
        ws = op("workspace_update", id=ws["id"], revision=ws["revision"], scenario_id=empty["id"])
        assert ws["branch_id"] is None and ws["compare_branch_id"] is None and ws["tick"] == 0
        with pytest.raises(OperationError, match="selected branch"):
            op(
                "workspace_update",
                id=ws["id"],
                revision=ws["revision"],
                compare_branch_id=right["id"],
            )
    finally:
        service.close()
