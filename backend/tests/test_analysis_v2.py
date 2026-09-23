"""V2 lifecycle/traceability regression tests; model/research doubles are test-only."""

import asyncio
import hashlib
import json
import threading
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_analysis_runner import Model as LegacyModel
from test_analysis_runner import fresh as fresh_v1
from test_analysis_service import call, get, wait_job

from tianji_lab import research
from tianji_lab import service as service_module
from tianji_lab.analysis import AnalysisBudget, AnalysisTask, Frame
from tianji_lab.analysis_runner import run_analysis
from tianji_lab.analysis_v2 import (
    AnalysisRunV2,
    AnalysisStartV2,
    ResearchHooks,
    parse_analysis,
    run_analysis_v2,
)
from tianji_lab.api import create_app
from tianji_lab.research_types import (
    Passage,
    ResearchBudget,
    ResearchOptions,
    ResearchState,
    Source,
)
from tianji_lab.service import OperationError, Service, now
from tianji_lab.vision import VisionRequest

REQUEST = {"request": {"vision": "Improve access to community education"}}


def fresh(**options):
    return AnalysisRunV2(
        id="research-run",
        request=VisionRequest(**REQUEST["request"]),
        budget=AnalysisBudget(),
        created_at=now(),
        **options,
    )


def evidence(many=False):
    sources, passages = [], []
    for i in range(1, 6 if many else 2):
        text = (f"Source {i} reports a public test observation. " * 150)[:6000]
        sources.append(
            Source(
                id=f"source_{i}",
                title=f"Test-only source {i}",
                url=f"https://example.org/{i}",
                resolved_url=f"https://example.org/{i}",
                retrieved_at=now(),
                publisher="example.org",
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                extractor="test-only",
            )
        )
        for j in range(1, 4 if many else 2):
            start = (j - 1) * 800
            quote = text[start : start + 800]
            passages.append(
                Passage(
                    id=f"source_{i}_p{j}",
                    source_id=f"source_{i}",
                    start=start,
                    end=start + len(quote),
                    quote=quote,
                )
            )
    return ResearchState(
        status="succeeded",
        sources=sources,
        passages=passages,
        queries_used=1,
        pages_used=len(sources),
        finished_at=now(),
    )


async def collected(queries, options, state, checkpoint, check):
    check()
    assert queries == ["public education access"]
    if options.mode != "offline":
        state.status = "running"
        state.started_at = now()
        checkpoint()
    if options.mode == "offline":
        state.status = "skipped"
        state.finished_at = now()
    else:
        for key, value in evidence().model_dump().items():
            if key not in ("queries", "started_at", "sources", "passages"):
                setattr(state, key, value)
        state.sources = evidence().sources
        state.passages = evidence().passages
    checkpoint()


class Model(LegacyModel):
    url = "http://127.0.0.1:18789"

    def __init__(self, *, bad=None, cited=True):
        super().__init__(perspectives=1, revision=False)
        self.bad, self.cited = bad, cited
        self.visible = []

    async def complete(self, role, instructions, context, output_type, max_tokens):
        self.visible.append(deepcopy(context.get("visible_passages", [])))
        base_context = {
            key: value
            for key, value in context.items()
            if key not in ("visible_passages", "research_status", "research_gaps")
        }
        base = await super().complete(role, instructions, base_context, Frame, max_tokens)
        if role == "framing":
            data = {
                "content": base.output.model_dump(),
                "search_queries": ["public education access"],
            }
        else:
            assert context["research_status"] in ("succeeded", "failed", "skipped", "partial")
            targets = {"strategy": "/mechanism", "critic": "/limitation", "synthesis": "/summary"}
            citations = []
            if context["visible_passages"] and self.cited:
                citations = [
                    {
                        "target": targets[role],
                        "passage_id": context["visible_passages"][0]["id"],
                        "relation": "support",
                        "epistemic": "inference",
                    }
                ]
                if role == "strategy" and self.bad:
                    citations[0].update(self.bad)
            data = {"content": base.output.model_dump(), "citations": citations}
        return SimpleNamespace(output=output_type.model_validate(data), output_tokens=100)


def execute(monkeypatch, model=None, run=None, collector=collected):
    monkeypatch.setattr(research, "collect_research", collector)
    snapshots = []
    model = model or Model()
    result = asyncio.run(
        run_analysis_v2(
            run or fresh(),
            model,
            lambda run: snapshots.append(run.model_dump(mode="json")) or True,
            lambda: None,
        )
    )
    return result, snapshots, model


def test_framing_research_then_strategies_and_exact_citations(monkeypatch):
    result, snapshots, model = execute(monkeypatch)
    assert result.status == "succeeded"
    assert result.research.status == "succeeded"
    assert [role for role, _ in model.contexts] == ["framing", "strategy", "critic", "synthesis"]
    assert model.visible[0] == [] and all(model.visible[1:])
    assert result.task_passages["strategy_1"] == ["source_1_p1"]
    assert {c.task_id for c in result.citations} == {"strategy_1", "critic", "synthesis"}
    assert all(AnalysisRunV2.model_validate(snapshot) for snapshot in snapshots)
    researching = next(s for s in snapshots if s["research"]["status"] == "running")
    assert [task["id"] for task in researching["tasks"]] == ["framing"]
    assert researching["tasks"][0]["status"] == "succeeded"
    assert result.research.passages[0].quote == result.research.sources[0].text[:800]
    assert parse_analysis(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "bad",
    [
        {"passage_id": "foreign_project_p1"},
        {"target": "/claims/0/id"},
        {"target": "/claims/2/detail"},
        {"target": "/unknown"},
        {"target": "/claims/00/detail"},
    ],
)
def test_invalid_citation_never_publishes_task_or_graph(monkeypatch, bad):
    result, snapshots, _ = execute(monkeypatch, Model(bad=bad))
    assert result.status == "partial" and result.tasks[-1].status == "failed"
    assert result.tasks[-1].result is None and not result.citations and not result.candidates
    assert len(result.tasks) == 2
    assert all(not snapshot["citations"] for snapshot in snapshots)


def test_persistence_rejects_unseen_passage_and_detached_target(monkeypatch):
    result, _, _ = execute(monkeypatch)
    for mutate in (
        lambda d: d["task_passages"].update(strategy_1=[]),
        lambda d: d["citations"][0].update(target="/claims/0/id"),
        lambda d: d["citations"][0].update(task_id="other-project-task"),
        lambda d: d["research"]["passages"][0].update(quote="invented"),
        lambda d: d["research"]["sources"][0].update(text_sha256="0" * 64),
    ):
        data = result.model_dump(mode="json")
        mutate(data)
        with pytest.raises(ValidationError):
            AnalysisRunV2.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["research"].update(queries_used=999),
        lambda d: d["research"].update(pages_used=999),
        lambda d: d["research"].update(fetched_bytes=999999999),
        lambda d: d["research"].update(errors=["search_failed"]),
        lambda d: d["research_options"].update(mode="offline"),
    ],
)
def test_persistence_rejects_research_budget_and_status_lies(monkeypatch, mutation):
    import sqlite3

    result, _, _ = execute(monkeypatch)
    data = result.model_dump(mode="json")
    mutation(data)
    invalid = result.model_copy(
        update={
            "research": ResearchState.model_validate(data["research"]),
            "research_options": ResearchOptions.model_validate(data["research_options"]),
        }
    )
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE analysis(id TEXT PRIMARY KEY, run_json TEXT)")
        db.execute("INSERT INTO analysis VALUES(?,?)", (result.id, result.model_dump_json()))
        with pytest.raises(ValidationError):
            Service._write_analysis(db, invalid)
        assert parse_analysis(db.execute("SELECT run_json FROM analysis").fetchone()[0]) == result


def test_prompt_passage_budget_records_only_actually_visible_ids():
    run = fresh(
        research=evidence(many=True), research_options=ResearchOptions(budget={"max_pages": 5})
    )
    task = AnalysisTask(id="strategy_1", role="strategy", brief="Explore", model="test")
    run.tasks.append(task)
    from tianji_lab.analysis import Strategy

    _, context, _ = ResearchHooks(run).prepare(task, {"request": REQUEST}, Strategy)
    visible = context["visible_passages"]
    assert 0 < len(visible) < len(run.research.passages)
    assert sum(len(p["quote"]) for p in visible) <= 4000
    assert run.task_passages[task.id] == [p["id"] for p in visible]
    unseen = next(p.id for p in run.research.passages if p.id not in run.task_passages[task.id])
    assert unseen not in json.dumps(context)


def test_critic_wire_targets_are_role_specific_and_still_resolve_actual_text():
    from tianji_lab.analysis import Critique

    run = fresh(research=evidence())
    task = AnalysisTask(id="critic", role="critic", brief="Review", model="test")
    run.tasks.append(task)
    hooks = ResearchHooks(run)
    instructions, _, wire = hooks.prepare(task, {}, Critique)
    assert "/mechanism" not in instructions and "claim_relations" not in instructions
    assert "/objections/0/concern" in instructions
    data = {
        "content": {
            "objections": [],
            "revision_task_id": "",
            "limitation": "Same model only",
        },
        "citations": [
            {"target": "/limitation", "passage_id": "source_1_p1", "relation": "context"}
        ],
    }
    assert type(hooks.decode(task, wire.model_validate(data))) is Critique
    for target in ("/mechanism", "/content/objectioins/0/concern", "/content/objections/0/concern"):
        data["citations"][0]["target"] = target
        with pytest.raises(ValidationError):
            wire.model_validate(data)
    data["citations"][0]["target"] = "/objections/0/concern"
    with pytest.raises(ValueError, match="Invalid citation target"):
        hooks.decode(task, wire.model_validate(data))
    data["citations"][0].update(target="/limitation", passage_id="unseen")
    with pytest.raises(ValidationError):
        wire.model_validate(data)


@pytest.mark.parametrize(
    "mode,cited,status", [("online", False, "succeeded"), ("offline", True, "skipped")]
)
def test_no_citations_or_offline_is_partial_not_researched_success(
    monkeypatch, mode, cited, status
):
    result, _, _ = execute(
        monkeypatch, Model(cited=cited), fresh(research_options=ResearchOptions(mode=mode))
    )
    assert result.status == "partial" and result.research.status == status
    assert not result.citations and result.summary and result.unresolved


def test_failed_research_keeps_explicit_gaps_without_fabrication(monkeypatch):
    async def failed(queries, options, state, checkpoint, check):
        state.status = "failed"
        state.errors = ["search_failed"]
        checkpoint()

    result, _, model = execute(monkeypatch, collector=failed)
    assert result.status == "partial" and result.summary
    assert not result.research.sources and not result.citations
    assert all(not visible for visible in model.visible)


def test_research_exception_sanitized_preserves_frame(monkeypatch):
    async def broken(*args):
        raise RuntimeError("PRIVATE PROVIDER PAYLOAD")

    result, snapshots, _ = execute(monkeypatch, collector=broken)
    assert result.status == "partial" and result.research.status == "failed"
    assert result.tasks[0].status == "succeeded" and len(result.tasks) == 1
    assert "PRIVATE" not in json.dumps(snapshots)


@pytest.mark.parametrize("external", [False, True])
def test_cancel_research_closes_await_and_starts_no_strategy(monkeypatch, external):
    entered = asyncio.Event()
    closed = []
    saved = []

    async def hanging(queries, options, state, checkpoint, check):
        state.status = "running"
        checkpoint()
        entered.set()
        try:
            await asyncio.Future()
        finally:
            closed.append(True)

    monkeypatch.setattr(research, "collect_research", hanging)

    async def scenario():
        model = Model()
        job = asyncio.create_task(
            run_analysis_v2(
                fresh(),
                model,
                lambda r: saved.append(r.model_dump(mode="json")) or True,
                lambda: "cancelled" if entered.is_set() and not external else None,
            )
        )
        await entered.wait()
        if external:
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await job
        else:
            assert (await job).status == "cancelled"
        assert len(model.contexts) == 1

    asyncio.run(scenario())
    assert closed == [True]
    assert saved[-1]["research"]["status"] == "cancelled"
    assert saved[-1]["tasks"][0]["status"] == "succeeded"


def test_real_collector_receives_proposed_queries_as_unattempted(monkeypatch):
    attempted = []

    async def empty_search(query, **kwargs):
        attempted.append(query)
        return []

    monkeypatch.setattr(research, "search_public", empty_search)
    result = asyncio.run(run_analysis_v2(fresh(), Model(), lambda r: True, lambda: None))
    assert attempted == ["public education access"]
    assert result.search_queries == result.research.queries == attempted
    assert result.research.queries_used == 1
    assert result.research.status == "failed" and result.status == "partial"
    assert result.research.sources == []


def test_real_offline_collector_never_calls_search(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Explicit offline mode must not search")

    monkeypatch.setattr(research, "search_public", forbidden)
    result = asyncio.run(
        run_analysis_v2(
            fresh(research_options=ResearchOptions(mode="offline")),
            Model(),
            lambda r: True,
            lambda: None,
        )
    )
    assert result.research.status == "skipped" and result.status == "partial"
    assert result.search_queries and not result.research.queries
    assert result.research.queries_used == result.research.fetched_bytes == 0


def test_v1_runner_never_invokes_research(monkeypatch):
    async def forbidden(*args):
        pytest.fail("v1 must not start public research")

    monkeypatch.setattr(research, "collect_research", forbidden)
    run = asyncio.run(run_analysis(fresh_v1(), LegacyModel(), lambda r: True, lambda: None))
    assert run.status == "succeeded" and run.schema_version == "tianji.analysis.v1"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", "http://127.0.0.1:18789")
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", "test-only-model")
    service = Service(tmp_path, start_worker=False)
    yield service
    service.close()


def start(lab, request=REQUEST, request_id=None):
    return call(lab, "analysis_start_v2", request, request_id)


def test_service_version_lists_stats_idempotency_and_offline_input(lab):
    old = call(lab, "analysis_start", REQUEST)
    new = start(lab, request_id="same")
    assert start(lab, request_id="same") == new
    assert get(lab, new)["research_options"]["mode"] == "online"
    assert [r["id"] for r in call(lab, "analysis_list")["items"]] == [old["id"]]
    mixed = call(lab, "analysis_list_v2")["items"]
    assert [r["schema_version"] for r in mixed] == ["tianji.analysis.v2", "tianji.analysis.v1"]
    stats = call(lab, "analysis_stats")
    assert stats["multi_agent_runs"] == stats["research_runs"] == 1
    assert stats["saved_analyses"] == stats["nodes"] == stats["paths"] == 0
    offline = {**REQUEST, "research": {"mode": "offline"}}
    with pytest.raises(OperationError) as error:
        start(lab, offline, "same")
    assert error.value.code == "idempotency_conflict"
    off = start(lab, offline)
    assert get(lab, off)["research_options"]["mode"] == "offline"
    call(lab, "job_cancel", {"id": new["id"]})
    assert get(lab, new)["research"]["status"] == "cancelled"
    assert start(lab, request_id="same") == new


def test_service_real_coordinator_double_adapters_atomic_readback(lab, monkeypatch, tmp_path):
    lab.local_analysis = Model()
    monkeypatch.setattr(research, "collect_research", collected)
    job = start(lab)
    lab.start()
    terminal = wait_job(lab, job)
    assert terminal["status"] == "succeeded"
    assert terminal["result"] == {"analysis_id": job["id"]}
    before = get(lab, job)
    assert AnalysisRunV2.model_validate(before).citations
    assert call(lab, "analysis_stats")["research_sources"] == 1
    lab.close()
    restarted = Service(tmp_path, start_worker=False)
    try:
        assert get(restarted, job) == before
        assert call(restarted, "job_get", {"id": job["id"]}) == terminal
    finally:
        restarted.close()


def test_research_evidence_is_paginated_and_legacy_snapshots_are_backfilled(tmp_path):
    service = Service(tmp_path, start_worker=False)
    run = fresh(
        research=evidence(many=True),
        research_options=ResearchOptions(budget=ResearchBudget(max_pages=5)),
    ).model_copy(update={"status": "partial"})
    try:
        with service.store.transaction() as db:
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,NULL,NULL,?)",
                (run.id, "analysis_start_v2", "partial", "{}", run.created_at),
            )
            db.execute(
                "INSERT INTO analysis VALUES(?,?,?)",
                (run.id, run.model_dump_json(), run.created_at),
            )
            service._write_analysis(db, run)
        first = call(
            service,
            "research_evidence",
            {"id": run.id, "kind": "sources", "limit": 2},
        )
        assert [item["id"] for item in first["items"]] == ["source_1", "source_2"]
        assert first["next_cursor"] == "source_2"
        second = call(
            service,
            "research_evidence",
            {
                "id": run.id,
                "kind": "sources",
                "after": first["next_cursor"],
                "limit": 10,
            },
        )
        assert [item["id"] for item in second["items"]] == [
            "source_3",
            "source_4",
            "source_5",
        ]
        passages = call(
            service,
            "research_evidence",
            {"id": run.id, "kind": "passages", "limit": 50},
        )
        assert len(passages["items"]) == 15
        with service.store.transaction() as db:
            db.execute("DELETE FROM research_source WHERE analysis_id=?", (run.id,))
            db.execute("DELETE FROM research_passage WHERE analysis_id=?", (run.id,))
    finally:
        service.close()

    reopened = Service(tmp_path, start_worker=False)
    try:
        restored = call(
            reopened,
            "research_evidence",
            {"id": run.id, "kind": "sources", "limit": 50},
        )
        assert len(restored["items"]) == 5
    finally:
        reopened.close()


def test_research_evidence_rejects_v1_project(tmp_path, monkeypatch):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", "http://127.0.0.1:18789")
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", "test-local")
    service = Service(tmp_path, start_worker=False)
    try:
        v1 = call(service, "analysis_start", REQUEST)
        with pytest.raises(OperationError, match="v2"):
            call(service, "research_evidence", {"id": v1["id"], "kind": "sources"})
    finally:
        service.close()


def test_research_evidence_rejects_invalid_cursor(tmp_path):
    service = Service(tmp_path, start_worker=False)
    run = fresh(
        research=evidence(many=True),
        research_options=ResearchOptions(budget=ResearchBudget(max_pages=5)),
    ).model_copy(update={"status": "partial"})
    try:
        with service.store.transaction() as db:
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,NULL,NULL,?)",
                (run.id, "analysis_start_v2", "partial", "{}", run.created_at),
            )
            db.execute(
                "INSERT INTO analysis VALUES(?,?,?)",
                (run.id, run.model_dump_json(), run.created_at),
            )
            service._write_analysis(db, run)
        with pytest.raises(OperationError, match="validation"):
            call(
                service,
                "research_evidence",
                {"id": run.id, "kind": "sources", "after": "source_9!"},
            )
    finally:
        service.close()


def test_research_evidence_requires_cursor_to_match_kind(tmp_path):
    service = Service(tmp_path, start_worker=False)
    run = fresh(
        research=evidence(many=True),
        research_options=ResearchOptions(budget=ResearchBudget(max_pages=5)),
    ).model_copy(update={"status": "partial"})
    try:
        with service.store.transaction() as db:
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,NULL,NULL,?)",
                (run.id, "analysis_start_v2", "partial", "{}", run.created_at),
            )
            db.execute(
                "INSERT INTO analysis VALUES(?,?,?)",
                (run.id, run.model_dump_json(), run.created_at),
            )
            service._write_analysis(db, run)
        with pytest.raises(OperationError, match="Cursor"):
            call(
                service,
                "research_evidence",
                {"id": run.id, "kind": "passages", "after": "source_1"},
            )
    finally:
        service.close()


def test_research_frontier_projects_queries_and_paginates(tmp_path):
    service = Service(tmp_path, start_worker=False)
    run = fresh(
        search_queries=["first query", "second query"],
        research=evidence().model_copy(update={"queries": ["first query"]}),
        research_options=ResearchOptions(budget=ResearchBudget(max_queries=2, max_pages=5)),
    ).model_copy(update={"status": "partial"})
    try:
        with service.store.transaction() as db:
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,NULL,NULL,?)",
                (run.id, "analysis_start_v2", "partial", "{}", run.created_at),
            )
            db.execute(
                "INSERT INTO analysis VALUES(?,?,?)",
                (run.id, run.model_dump_json(), run.created_at),
            )
            service._write_analysis(db, run)
        first = call(service, "research_frontier", {"id": run.id, "limit": 1})
        assert first["items"][0]["state"] == "attempted"
        assert first["items"][0]["query"] == "first query"
        assert first["next_cursor"] == "frontier_1"
        second = call(
            service,
            "research_frontier",
            {"id": run.id, "after": first["next_cursor"], "limit": 10},
        )
        assert [item["id"] for item in second["items"]] == ["frontier_2"]
        assert second["items"][0]["state"] == "skipped"
        with pytest.raises(OperationError, match="Cursor"):
            call(service, "research_frontier", {"id": run.id, "after": "source_1"})
    finally:
        service.close()


@pytest.mark.parametrize("stop", ["cancel", "shutdown"])
def test_service_research_stop_preserves_checkpoint_and_rejects_late_save(
    lab, monkeypatch, tmp_path, stop
):
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    late = []

    async def delayed(run, model, save, cancelled):
        run.research = evidence()
        run.research.status = "running"
        assert save(run)
        entered.set()
        while not release.is_set() and not cancelled():
            await asyncio.sleep(0.01)
        late.append(save(run.model_copy(update={"summary": "LATE"})))
        returned.set()
        return run.model_copy(update={"status": "partial"})

    monkeypatch.setattr(service_module, "run_analysis_v2", delayed)
    job = start(lab)
    lab.start()
    try:
        assert entered.wait(3)
        if stop == "cancel":
            call(lab, "job_cancel", {"id": job["id"]})
            assert returned.wait(3)
        else:
            lab.close()
        expected = "cancelled" if stop == "cancel" else "interrupted"
        if stop == "cancel":
            saved = get(lab, job)
        else:
            reopened = Service(tmp_path, start_worker=False)
            try:
                saved = get(reopened, job)
            finally:
                reopened.close()
        assert late == [False]
        assert saved["status"] == saved["research"]["status"] == expected
        assert saved["research"]["sources"] and saved["summary"] == ""
    finally:
        release.set()


def test_restart_interrupts_research_without_replay_leaves_queued(lab, tmp_path):
    started, queued = start(lab), start(lab)
    with lab.store.transaction() as db:
        run = lab._analysis(db, started["id"])
        run.research.status = "running"
        run.research.queries_used = 1
        lab._write_analysis(db, run)
    lab.close()
    reopened = Service(tmp_path, start_worker=False)
    try:
        run = get(reopened, started)
        assert run["status"] == run["research"]["status"] == "interrupted"
        assert call(reopened, "job_get", {"id": started["id"]})["status"] == "interrupted"
        assert get(reopened, queued)["status"] == "queued"
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "failure", ["exception", "version", "options", "citation", "false_success"]
)
def test_service_invalid_checkpoint_sanitized_and_input_immutable(lab, monkeypatch, failure):
    async def broken(run, model, save, cancelled):
        run.research.status = "running"
        assert save(run)
        if failure == "exception":
            raise RuntimeError("PRIVATE RAW RESPONSE")
        if failure == "version":
            run.schema_version = "tianji.analysis.v1"
        elif failure == "options":
            run.research_options = ResearchOptions(mode="offline")
        elif failure == "citation":
            run.task_passages = {"not-a-task": ["foreign-passage"]}
        else:
            run.status = "succeeded"
        save(run)
        return run

    monkeypatch.setattr(service_module, "run_analysis_v2", broken)
    job = start(lab)
    lab.start()
    assert wait_job(lab, job)["status"] == "failed"
    run = get(lab, job)
    assert run["status"] == run["research"]["status"] == "failed"
    assert run["research_options"]["mode"] == "online"
    assert run["schema_version"] == "tianji.analysis.v2"
    with lab.store.transaction() as db:
        assert "PRIVATE" not in "\n".join(db.iterdump())


def test_http_v2_registry_input_validation_and_explicit_v1(lab, tmp_path):
    lab.close()
    with TestClient(create_app(tmp_path, token="test", start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer test"
        catalog = {op["name"]: op for op in client.get("/api/capabilities").json()}
        assert catalog["analysis_start_v2"]["input_schema"] == AnalysisStartV2.model_json_schema()
        assert "Online by default" in catalog["analysis_start_v2"]["description"]
        for args in (
            {**REQUEST, "research": {"mode": "unknown"}},
            {**REQUEST, "research": {"budget": {"max_pages": True}}},
        ):
            response = client.post(
                "/api/operations/analysis_start_v2",
                json={"arguments": args, "request_id": "invalid"},
            )
            assert response.status_code == 422
        response = client.post(
            "/api/operations/analysis_start_v2", json={"arguments": REQUEST, "request_id": "v2"}
        )
        assert response.status_code == 200
        id = response.json()["data"]["id"]
        saved = client.post("/api/operations/analysis_get", json={"arguments": {"id": id}}).json()[
            "data"
        ]
        assert (
            saved["schema_version"] == "tianji.analysis.v2"
            and saved["research"]["status"] == "not_started"
        )
