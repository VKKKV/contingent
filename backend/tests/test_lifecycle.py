"""Ownership and actual running-worker cancellation regressions."""

import time
import uuid

import pytest

from tianji_lab.service import Service


def call(service, name, **arguments):
    return service.execute(name, arguments, str(uuid.uuid4()))


def test_second_owner_cannot_interrupt_an_active_job(tmp_path):
    first = Service(tmp_path, start_worker=False)
    try:
        scenario = call(first, "scenario_list")["items"][0]
        job = call(first, "run_forward", scenario_id=scenario["id"], actions=[])
        with first.store.transaction() as db:
            db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
        with pytest.raises(RuntimeError, match="already in use"):
            Service(tmp_path, start_worker=False)
        assert call(first, "job_get", id=job["id"])["status"] == "running"
    finally:
        first.close()
    reopened = Service(tmp_path, start_worker=False)
    try:
        assert call(reopened, "job_get", id=job["id"])["status"] == "interrupted"
    finally:
        reopened.close()


def test_running_cancel_prevents_result_commit_and_worker_can_continue(tmp_path):
    service = Service(tmp_path)
    try:
        scenario = call(service, "scenario_create", spec={"name": "Cancel test", "horizon": 10})
        job = call(service, "run_backward", scenario_id=scenario["id"], goal={}, max_nodes=50000)
        deadline = time.monotonic() + 15
        while call(service, "job_get", id=job["id"])["status"] == "queued":
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert call(service, "job_get", id=job["id"])["status"] == "running"
        assert call(service, "job_cancel", id=job["id"])["status"] == "cancelled"
        next_job = call(service, "run_forward", scenario_id=scenario["id"], actions=[])
        while call(service, "job_get", id=next_job["id"])["status"] in ("queued", "running"):
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert call(service, "job_get", id=next_job["id"])["status"] == "succeeded"
        cancelled = call(service, "job_get", id=job["id"])
        assert cancelled["status"] == "cancelled" and cancelled["result"] is None
        assert len(call(service, "branch_list", scenario_id=scenario["id"])["items"]) == 1
    finally:
        service.close()
