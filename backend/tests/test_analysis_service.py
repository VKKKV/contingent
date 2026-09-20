"""Durable lifecycle tests. Coordinators and structured outputs here are test doubles only."""

import asyncio
import json
import sqlite3
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tianji_lab import service as service_module
from tianji_lab.analysis import AnalysisRun, AnalysisStart, AnalysisTask, Frame, IssueNode
from tianji_lab.api import create_app
from tianji_lab.service import OperationError, Service, now

REQUEST = {"request": {"vision": "Improve access to community education"}}


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", "http://127.0.0.1:18789")
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", "test-local")


@pytest.fixture
def lab(tmp_path):
    service = Service(tmp_path, start_worker=False)
    yield service
    service.close()


def call(service, name, arguments=None, request_id=None):
    return service.execute(name, arguments or {}, request_id or str(uuid.uuid4()))


def start(service):
    return call(service, "analysis_start", REQUEST)


def get(service, job):
    return call(service, "analysis_get", {"id": job["id"]})


def wait_job(service, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = call(service, "job_get", {"id": job["id"]})
        if current["status"] not in ("queued", "running"):
            return current
        time.sleep(0.01)
    pytest.fail("Analysis worker did not finish")


def completed_task():
    return AnalysisTask(
        id="framing",
        role="framing",
        brief="Frame the goal",
        model="test-local",
        status="succeeded",
        started_at=now(),
        finished_at=now(),
        result=Frame(
            objective="Accessible education",
            criteria=["Participation"],
            assumptions=["People can collaborate"],
            unknowns=["Resources"],
            perspectives=["Local community"],
        ),
    )


def checkpoint(run):
    return run.model_copy(
        update={
            "tasks": [
                completed_task(),
                AnalysisTask(
                    id="strategy",
                    role="strategy",
                    brief="Consider alternatives",
                    model="test-local",
                    status="running",
                    started_at=now(),
                    dependencies=["framing"],
                    parent_id="framing",
                ),
                AnalysisTask(
                    id="critic", role="critic", brief="Review alternatives", model="test-local"
                ),
            ],
            "nodes": [
                IssueNode(
                    id="question",
                    kind="question",
                    title="Accessible education",
                    detail="Test hypothesis",
                    task_id="framing",
                )
            ],
            "calls": 2,
        }
    )


async def success(run, model, save, cancelled):
    assert model.model == "test-local"
    assert cancelled() is None
    result = run.model_copy(
        update={
            "status": "succeeded",
            "tasks": [completed_task()],
            "calls": 1,
            "finished_at": now(),
            "summary": "Test-only structured result",
            "nodes": [
                IssueNode(
                    id="question",
                    kind="question",
                    title="Accessible education",
                    detail="Test hypothesis",
                    task_id="framing",
                )
            ],
        }
    )
    assert save(result)
    return result


def test_enqueue_idempotency_persistence_and_listing(lab, tmp_path):
    first = call(lab, "analysis_start", REQUEST, "same")
    assert first == call(lab, "analysis_start", REQUEST, "same")
    assert first == {
        "id": first["id"],
        "kind": "analysis_start",
        "status": "queued",
        "result": None,
        "error": None,
    }
    run = AnalysisRun.model_validate(get(lab, first))
    assert run.request.vision == REQUEST["request"]["vision"]
    assert run.budget == AnalysisStart.model_validate(REQUEST).budget
    second = start(lab)
    assert [item["id"] for item in call(lab, "analysis_list")["items"]] == [
        second["id"],
        first["id"],
    ]
    with pytest.raises(OperationError) as error:
        call(lab, "analysis_start", {"request": {"vision": "Different"}}, "same")
    assert error.value.code == "idempotency_conflict"
    with lab.store.transaction() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM analysis").fetchone()[0] == 2
        assert json.loads(db.execute("SELECT input_json FROM jobs LIMIT 1").fetchone()[0]) == {
            "analysis_id": first["id"]
        }
    lab.close()
    restarted = Service(tmp_path, start_worker=False)
    try:
        assert get(restarted, first) == run.model_dump(mode="json")
        assert call(restarted, "analysis_start", REQUEST, "same") == first
    finally:
        restarted.close()


def test_success_is_atomic_persisted_not_branch_and_legacy_stats_unchanged(lab, monkeypatch):
    monkeypatch.setattr(service_module, "run_analysis", success)
    job = start(lab)
    lab.start()
    finished = wait_job(lab, job)
    assert finished["status"] == "succeeded"
    assert finished["result"] == {"analysis_id": job["id"]}
    run = get(lab, job)
    assert run["status"] == "succeeded" and run["tasks"][0]["result"]["objective"]
    assert call(lab, "job_cancel", {"id": job["id"]}) == finished
    stats = call(lab, "analysis_stats")
    assert stats["architecture"] == "single_model_single_call"
    assert stats["scope"] == "saved_analyses_only"
    assert stats["saved_analyses"] == stats["nodes"] == stats["paths"] == 0
    assert (
        stats["multi_agent_runs"] == stats["multi_agent_tasks"] == stats["multi_agent_nodes"] == 1
    )
    with lab.store.transaction() as db:
        assert db.execute("SELECT count(*) FROM branch").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM vision").fetchone()[0] == 0


def test_partial_is_new_job_result_not_branch(lab, monkeypatch):
    async def partial(run, model, save, cancelled):
        return run.model_copy(
            update={"status": "partial", "finished_at": now(), "error": "Call budget exhausted"}
        )

    monkeypatch.setattr(service_module, "run_analysis", partial)
    job = start(lab)
    lab.start()
    finished = wait_job(lab, job)
    assert finished["status"] == "partial"
    assert finished["result"] == {"analysis_id": job["id"]}
    assert get(lab, job)["status"] == "partial"


def test_queued_cancel_updates_run_immediately_and_retry_returns_original(lab):
    job = call(lab, "analysis_start", REQUEST, "cancel-me")
    assert call(lab, "job_cancel", {"id": job["id"]})["status"] == "cancelled"
    run = get(lab, job)
    assert run["status"] == "cancelled" and run["finished_at"]
    assert call(lab, "analysis_start", REQUEST, "cancel-me") == job


@pytest.mark.parametrize("stop", ["cancel", "shutdown", "restart", "failure"])
def test_stopped_durations_persist_from_explicit_starts(lab, monkeypatch, tmp_path, stop):
    timestamp = "2026-01-02T00:00:10+00:00"
    monkeypatch.setattr(service_module, "now", lambda: "2026-01-01T00:00:00+00:00")
    job = start(lab)
    run = checkpoint(AnalysisRun.model_validate(get(lab, job)))
    run.status = "running"
    run.duration_ms = 1000
    run.tasks[0].started_at = "2026-01-02T00:00:00+00:00"
    run.tasks[0].finished_at = "2026-01-02T00:00:01+00:00"
    run.tasks[0].duration_ms = 1000
    run.tasks[1].started_at = "2026-01-02T00:00:02.500000+00:00"
    before = run.tasks[0].model_dump(mode="json")
    with lab.store.transaction() as db:
        lab._write_analysis(db, run)
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (job["id"],))
    monkeypatch.setattr(service_module, "now", lambda: timestamp)

    if stop == "cancel":
        call(lab, "job_cancel", {"id": job["id"]})
    elif stop in ("shutdown", "failure"):

        async def interrupted(run, model, save, cancelled):
            if stop == "shutdown":
                lab.stopping.set()
                return run.model_copy(update={"status": "interrupted"})
            raise RuntimeError("test-only coordinator failure")

        monkeypatch.setattr(service_module, "run_analysis", interrupted)
        asyncio.run(lab._run_analysis_job(job))
    lab.close()

    restarted = Service(tmp_path, start_worker=False)
    try:
        saved = get(restarted, job)
        status = {"cancel": "cancelled", "failure": "failed"}.get(stop, "interrupted")
        assert saved["status"] == status
        assert saved["duration_ms"] == 10000  # Queue wait is not execution time.
        assert saved["finished_at"] == timestamp
        assert saved["tasks"][0] == before
        assert saved["tasks"][1]["duration_ms"] == 7500
        assert saved["tasks"][2]["duration_ms"] is None
        assert saved["tasks"][2]["started_at"] is None
        assert [task["status"] for task in saved["tasks"]] == ["succeeded", status, status]
        assert call(restarted, "job_get", {"id": job["id"]})["status"] == status
        with restarted.store.transaction() as db:
            persisted = json.loads(
                db.execute("SELECT run_json FROM analysis WHERE id=?", (job["id"],)).fetchone()[0]
            )
        assert persisted == saved
    finally:
        restarted.close()


@pytest.mark.parametrize("started_at", [None, "invalid", "2026-01-02T00:00:20+00:00"])
def test_cancel_without_elapsed_start_preserves_unknown_and_prior_duration(
    lab, monkeypatch, tmp_path, started_at
):
    job = start(lab)
    with lab.store.transaction() as db:
        run = lab._analysis(db, job["id"])
        run.duration_ms = 123
        run.tasks = [
            AnalysisTask(
                id="framing",
                role="framing",
                brief="Frame the goal",
                model="test-local",
                started_at=started_at,
                status="running" if started_at else "queued",
            )
        ]
        lab._write_analysis(db, run)
    monkeypatch.setattr(service_module, "now", lambda: "2026-01-02T00:00:10+00:00")
    call(lab, "job_cancel", {"id": job["id"]})
    lab.close()
    restarted = Service(tmp_path, start_worker=False)
    try:
        saved = get(restarted, job)
        assert saved["duration_ms"] == 123
        assert saved["tasks"][0]["duration_ms"] == (
            0 if started_at and started_at != "invalid" else None
        )
    finally:
        restarted.close()


def test_running_cancel_preserves_completed_tasks_rejects_late_save(lab, monkeypatch):
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    late = []

    async def delayed(run, model, save, cancelled):
        run = checkpoint(run)
        assert save(run)
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        assert cancelled() == "cancelled"
        run = run.model_copy(update={"status": "succeeded", "summary": "LATE PRIVATE RESULT"})
        late.append(save(run))
        returned.set()
        return run

    monkeypatch.setattr(service_module, "run_analysis", delayed)
    job = start(lab)
    lab.start()
    try:
        assert entered.wait(3)
        before = get(lab, job)
        cancel = call(lab, "job_cancel", {"id": job["id"]})
        assert cancel["status"] == "cancelled" and cancel["result"] is None
        run = get(lab, job)
        assert run["tasks"][0] == before["tasks"][0]
        assert [task["status"] for task in run["tasks"]] == ["succeeded", "cancelled", "cancelled"]
        assert run["nodes"] == before["nodes"]
        release.set()
        assert returned.wait(3) and late == [False]
        assert get(lab, job) == run
        monkeypatch.setattr(service_module, "run_analysis", success)
        next_job = start(lab)
        assert wait_job(lab, next_job)["status"] == "succeeded"
    finally:
        release.set()


def test_shutdown_interrupts_running_and_preserves_checkpoint(lab, monkeypatch, tmp_path):
    entered = threading.Event()

    async def stopping(run, model, save, cancelled):
        run = checkpoint(run)
        assert save(run)
        entered.set()
        while not cancelled():
            await asyncio.sleep(0.01)
        assert cancelled() == "interrupted"
        assert not save(run.model_copy(update={"summary": "LATE"}))
        return run.model_copy(update={"status": "succeeded"})

    monkeypatch.setattr(service_module, "run_analysis", stopping)
    job = start(lab)
    queued = start(lab)
    lab.start()
    assert entered.wait(3)
    before = get(lab, job)
    lab.close()
    restarted = Service(tmp_path, start_worker=False)
    try:
        run = get(restarted, job)
        assert run["status"] == "interrupted"
        assert run["tasks"][0] == before["tasks"][0]
        assert [task["status"] for task in run["tasks"]] == [
            "succeeded",
            "interrupted",
            "interrupted",
        ]
        assert get(restarted, queued)["status"] == "queued"
        assert call(restarted, "job_get", {"id": job["id"]})["status"] == "interrupted"
    finally:
        restarted.close()


@pytest.mark.parametrize("job_status", ["queued", "running"])
def test_restart_never_resumes_started_tasks(lab, tmp_path, monkeypatch, job_status):
    job = start(lab)
    queued = start(lab)
    with lab.store.transaction() as db:
        run = checkpoint(lab._analysis(db, job["id"]))
        lab._write_analysis(db, run)
        db.execute("UPDATE jobs SET status=? WHERE id=?", (job_status, job["id"]))
    with pytest.raises(RuntimeError, match="already in use"):
        Service(tmp_path, start_worker=False)
    before = get(lab, job)
    assert before["tasks"][1]["status"] == "running"
    lab.close()
    monkeypatch.setattr(service_module, "run_analysis", success)
    restarted = Service(tmp_path)
    try:
        run = get(restarted, job)
        assert run["status"] == "interrupted"
        assert run["tasks"][0] == before["tasks"][0]
        assert run["tasks"][1]["status"] == "interrupted"
        assert call(restarted, "job_get", {"id": job["id"]})["status"] == "interrupted"
        assert wait_job(restarted, queued)["status"] == "succeeded"
    finally:
        restarted.close()


@pytest.mark.parametrize("failure", ["exception", "invalid", "identity", "unfinished"])
def test_failure_sanitized_no_invalid_or_late_commit(lab, monkeypatch, failure):
    async def broken(run, model, save, cancelled):
        assert save(checkpoint(run))
        if failure == "exception":
            raise RuntimeError("PRIVATE PROMPT OR PROVIDER COMPLETION")
        if failure == "invalid":
            save(run.model_copy(update={"summary": "PRIVATE" * 1000}))
        if failure == "identity":
            save(run.model_copy(update={"id": "different"}))
        return run

    monkeypatch.setattr(service_module, "run_analysis", broken)
    job = start(lab)
    lab.start()
    finished = wait_job(lab, job)
    assert finished["status"] == "failed" and finished["result"] is None
    run = get(lab, job)
    assert run["status"] == "failed" and run["tasks"][0]["status"] == "succeeded"
    assert [task["status"] for task in run["tasks"]][1:] == ["failed", "failed"]
    with lab.store.transaction() as db:
        assert "PRIVATE" not in "\n".join(db.iterdump())


def test_shared_queue_capacity_atomic_rollback(lab):
    scenario = call(lab, "scenario_list")["items"][0]
    for _ in range(31):
        call(lab, "run_forward", {"scenario_id": scenario["id"], "actions": []})
    start(lab)
    for name, arguments in [
        ("analysis_start", REQUEST),
        ("run_forward", {"scenario_id": scenario["id"], "actions": []}),
    ]:
        with pytest.raises(OperationError) as error:
            call(lab, name, arguments, "overflow")
        assert error.value.code == "queue_full"
    with lab.store.transaction() as db:
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 32
        assert db.execute("SELECT count(*) FROM analysis").fetchone()[0] == 1
        assert (
            db.execute("SELECT count(*) FROM idempotency WHERE request_id='overflow'").fetchone()[0]
            == 0
        )


def test_project_limit_and_list_newest_100(lab):
    jobs = []
    for _ in range(100):
        job = start(lab)
        jobs.append(job)
        call(lab, "job_cancel", {"id": job["id"]})
    with pytest.raises(OperationError) as error:
        call(lab, "analysis_start", REQUEST, "over-cap")
    assert error.value.code == "record_limit"
    items = call(lab, "analysis_list")["items"]
    assert len(items) == 100
    assert [item["id"] for item in items] == [job["id"] for job in reversed(jobs)]
    assert set(items[0]) == {"id", "status", "created_at", "request"}


def test_enqueue_rolls_back_job_and_idempotency_when_project_write_fails(lab):
    with lab.store.transaction() as db:
        db.execute(
            "CREATE TRIGGER reject_analysis BEFORE INSERT ON analysis "
            "BEGIN SELECT RAISE(ABORT, 'test-only write rejection'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="test-only write rejection"):
        call(lab, "analysis_start", REQUEST, "retry-after-rollback")
    with lab.store.transaction() as db:
        for table in ("jobs", "analysis", "idempotency"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        db.execute("DROP TRIGGER reject_analysis")
    assert call(lab, "analysis_start", REQUEST, "retry-after-rollback")["status"] == "queued"


def test_completed_project_survives_restart_without_reexecution(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "run_analysis", success)
    job = call(lab, "analysis_start", REQUEST, "original")
    lab.start()
    finished = wait_job(lab, job)
    before = get(lab, job)
    lab.close()

    async def forbidden(*args):
        pytest.fail("A completed analysis must not be executed again")

    monkeypatch.setattr(service_module, "run_analysis", forbidden)
    restarted = Service(tmp_path)
    try:
        assert get(restarted, job) == before
        assert call(restarted, "job_get", {"id": job["id"]}) == finished
        assert call(restarted, "analysis_start", REQUEST, "original") == job
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "url,name,code",
    [
        ("", "", "analysis_disabled"),
        ("http://example.com", "test-local", "analysis_unavailable"),
        ("http://127.0.0.1:18789", " ", "analysis_unavailable"),
        ("http://127.0.0.1:18789", "test\nmodel", "analysis_unavailable"),
    ],
)
def test_configuration_rejected_before_enqueue(tmp_path, monkeypatch, url, name, code):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", url)
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", name)
    service = Service(tmp_path, start_worker=False)
    try:
        with pytest.raises(OperationError) as error:
            start(service)
        assert error.value.code == code and error.value.status == 503
        with service.store.transaction() as db:
            for table in ("analysis", "jobs", "idempotency"):
                assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    finally:
        service.close()


def test_http_registry_strict_schemas_and_legacy_compatibility(tmp_path):
    with TestClient(create_app(tmp_path, token="test-analysis", start_worker=False)) as client:
        route = "/api/operations/analysis_start"
        payload = {"arguments": REQUEST, "request_id": "http-analysis"}
        assert client.post(route, json=payload).status_code == 401
        client.headers["Authorization"] = "Bearer test-analysis"
        catalog = {entry["name"]: entry for entry in client.get("/api/capabilities").json()}
        assert catalog["analysis_start"]["input_schema"] == AnalysisStart.model_json_schema()
        assert catalog["analysis_start"]["mutating"] is True
        assert "persists" in catalog["analysis_start"]["description"]
        assert not catalog["analysis_get"]["mutating"] and not catalog["analysis_list"]["mutating"]
        assert {"run_forward", "run_backward", "vision_generate", "vision_save"} <= catalog.keys()
        assert client.post(route, json={"arguments": REQUEST}).status_code == 422
        invalid = {"arguments": {**REQUEST, "budget": {"max_calls": True}}, "request_id": "bad"}
        assert client.post(route, json=invalid).status_code == 422
        response = client.post(route, json=payload)
        assert response.status_code == 200
        job = response.json()["data"]
        assert client.post(route, json=payload).json()["data"] == job
        result = client.post("/api/operations/analysis_get", json={"arguments": {"id": job["id"]}})
        assert AnalysisRun.model_validate(result.json()["data"]).id == job["id"]
        cancel = client.post(
            "/api/operations/job_cancel",
            json={"arguments": {"id": job["id"]}, "request_id": "http-cancel"},
        )
        assert cancel.json()["data"]["status"] == "cancelled"
        assert (
            client.post(
                "/api/operations/analysis_get", json={"arguments": {"id": "missing"}}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/operations/analysis_list", json={"arguments": {"extra": True}}
            ).status_code
            == 422
        )
