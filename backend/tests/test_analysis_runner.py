import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tianji_lab.analysis import (
    AnalysisBudget,
    AnalysisRun,
    Claim,
    Critique,
    Frame,
    Objection,
    Strategy,
    Synthesis,
)
from tianji_lab.analysis_runner import run_analysis
from tianji_lab.vision import VisionRequest


def fresh(**budget):
    return AnalysisRun(
        id="run-1",
        request=VisionRequest(vision="减少社区夏季高温伤害"),
        budget=AnalysisBudget(**budget),
        created_at="2026-09-19T00:00:00Z",
    )


class Model:
    model = "test-only-model"

    def __init__(self, perspectives=2, revision=True, bad_reference=False, hang=False):
        self.contexts = []
        self.perspectives = perspectives
        self.revision = revision
        self.bad_reference = bad_reference
        self.hang = hang
        self.aborted = False

    async def complete(self, role, instructions, context, output_type, max_tokens):
        self.contexts.append((role, deepcopy(context)))
        if self.hang:
            try:
                await asyncio.Future()
            finally:
                self.aborted = True
        if role == "framing":
            output = Frame(
                objective="降低热伤害",
                criteria=["未来就诊记录"],
                assumptions=[],
                unknowns=["未有实测"],
                perspectives=[f"视角{i}" for i in range(self.perspectives)],
            )
        elif role in ("strategy", "revision"):
            output = Strategy(
                title="干预",
                mechanism="降低暴露",
                claims=[
                    Claim(
                        id="act",
                        kind="intervention",
                        title="开放避暑点",
                        detail="延长开放时间",
                        stakeholders=["居民"],
                        signals=["未来登记人数"],
                    )
                ],
                links=[],
                prerequisites=["工作人员"],
                tradeoffs=["运营成本"],
            )
        elif role == "critic":
            output = Critique(
                objections=[
                    Objection(
                        target_claim_id="missing" if self.bad_reference else "strategy_1_0",
                        concern="有劳动成本",
                        test="核对未来预算",
                    )
                ],
                revision_task_id="strategy_1" if self.revision else "",
                limitation="不是独立证据",
            )
        else:
            output = Synthesis(
                summary="同模型假设，仍需验证",
                alternatives=[context["candidates"][-1]["id"]],
                unresolved=["缺少预算"],
            )
        return SimpleNamespace(output=output, output_tokens=100)


def execute(model, **budget):
    saved = []
    result = asyncio.run(
        run_analysis(
            fresh(**budget),
            model,
            lambda run: saved.append(run.model_dump(mode="json")) or True,
            lambda: None,
        )
    )
    return result, saved


def test_real_task_roles_separate_contexts_lineage_and_objections():
    model = Model()
    result, saved = execute(model)
    assert result.status == "succeeded"
    assert [role for role, _ in model.contexts] == [
        "framing",
        "strategy",
        "strategy",
        "critic",
        "revision",
        "synthesis",
    ]
    assert result.calls == 6
    strategies = [context for role, context in model.contexts if role == "strategy"]
    assert all(set(context) == {"request", "frame", "perspective"} for context in strategies)
    assert strategies[0]["perspective"] != strategies[1]["perspective"]
    assert result.candidates[-1].supersedes == "strategy_1"
    revision_context = next(c for role, c in model.contexts if role == "revision")
    assert revision_context["claim_id_map"] == {"act": "strategy_1_0"}
    assert (
        revision_context["objections"][0]["target_claim_id"]
        in revision_context["claim_id_map"].values()
    )
    assert any(edge.kind == "challenges" for edge in result.edges)
    assert "有劳动成本" in result.unresolved
    assert all(task.duration_ms is not None for task in result.tasks)
    assert all(AnalysisRun.model_validate(snapshot) for snapshot in saved)
    assert any(t["status"] == "queued" for s in saved for t in s["tasks"])
    assert any(t["status"] == "running" for s in saved for t in s["tasks"])
    assert all(n.grounding in {"model_hypothesis", "model_objection"} for n in result.nodes)


@pytest.mark.parametrize("perspectives,expected", [(1, 4), (3, 6)])
def test_variable_task_counts_not_fixed_topology(perspectives, expected):
    result, _ = execute(Model(perspectives=perspectives, revision=False))
    assert result.status == "succeeded"
    assert result.calls == expected
    assert len(result.candidates) == perspectives


def test_exhaustion_returns_partial_not_fabricated_synthesis():
    result, _ = execute(Model(), max_calls=2)
    assert result.status == "partial"
    assert result.calls == 2
    assert not result.summary
    assert len(result.candidates) == 1
    assert "budget exhausted" in result.error


def test_token_budget_reserves_before_call_and_does_not_retry():
    model = Model()
    result, _ = execute(model, max_output_tokens=1100)
    assert result.status == "partial"
    assert result.calls == len(model.contexts) == 1
    assert result.reserved_output_tokens == 1000


def test_invalid_reference_does_not_become_graph_or_success():
    model = Model(bad_reference=True)
    result, _ = execute(model)
    assert result.status == "partial"
    assert result.tasks[-1].status == "failed"
    assert result.tasks[-1].result is None
    assert not any(n.kind == "objection" for n in result.nodes)
    assert result.calls == 4


def test_cancellation_aborts_active_await_and_no_later_tasks():
    async def scenario():
        model = Model(hang=True)
        result = await run_analysis(
            fresh(), model, lambda run: True, lambda: "cancelled" if model.contexts else None
        )
        return model, result

    model, result = asyncio.run(scenario())
    assert result.status == "cancelled"
    assert result.tasks[0].status == "cancelled"
    assert result.tasks[0].result is None
    assert model.aborted
    assert result.calls == 1


def test_cancelled_callback_rejects_late_success_commit():
    saved = []

    def save(run):
        if any(t.status == "succeeded" for t in run.tasks):
            return False
        saved.append(run.model_dump())
        return True

    result = asyncio.run(run_analysis(fresh(), Model(), save, lambda: None))
    assert result.status == "cancelled"
    assert result.calls == 1
    assert all(not s["nodes"] for s in saved)


def test_parent_and_dependency_cycles_rejected_issue_feedback_allowed():
    run, _ = execute(Model(revision=False))
    data = run.model_dump(mode="json")
    data["tasks"][0]["parent_id"] = "strategy_1"
    with pytest.raises(ValidationError, match="acyclic"):
        AnalysisRun.model_validate(data)
    data = run.model_dump(mode="json")
    data["edges"] += [
        {"source": "strategy_1_0", "target": "strategy_2_0", "kind": "may-influence"},
        {"source": "strategy_2_0", "target": "strategy_1_0", "kind": "may-influence"},
    ]
    AnalysisRun.model_validate(data)
