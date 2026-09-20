import asyncio

import pytest
from pydantic import ValidationError
from test_analysis_runner import Model, execute, fresh

from tianji_lab.analysis import AnalysisRun, Objection
from tianji_lab.analysis_runner import run_analysis


def test_terminal_save_is_once_and_contains_finished_timestamp():
    snapshots = []
    terminal = False

    def save(run):
        nonlocal terminal
        assert not terminal, "save after terminal CAS"
        terminal = run.status not in ("queued", "running")
        snapshots.append(run.model_dump())
        return True

    result = asyncio.run(run_analysis(fresh(), Model(), save, lambda: None))
    assert result.status == "succeeded"
    assert snapshots[-1]["finished_at"]
    assert snapshots[-1]["tasks"][-1]["finished_at"]


def test_external_asyncio_cancel_persists_cancelled_state_and_aborts_io():
    async def scenario():
        model, snapshots = Model(hang=True), []
        task = asyncio.create_task(
            run_analysis(
                fresh(), model, lambda run: snapshots.append(run.model_dump()) or True, lambda: None
            )
        )
        while not model.contexts:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert model.aborted
        assert snapshots[-1]["status"] == "cancelled"
        assert snapshots[-1]["tasks"][0]["status"] == "cancelled"
        assert snapshots[-1]["finished_at"]

    asyncio.run(scenario())


@pytest.mark.parametrize("usage", [-1, True, "10", 100000])
def test_invalid_usage_fails_safely(usage):
    class BadUsage(Model):
        async def complete(self, *args, **kwargs):
            result = await super().complete(*args, **kwargs)
            result.output_tokens = usage
            return result

    result, snapshots = execute(BadUsage())
    assert result.status == "failed"
    assert result.tasks[0].result is None
    assert result.tasks[0].output_tokens is None
    assert snapshots[-1]["finished_at"]


def test_critic_cannot_target_the_framing_question():
    class QuestionCritic(Model):
        async def complete(self, role, *args, **kwargs):
            result = await super().complete(role, *args, **kwargs)
            if role == "critic":
                result.output = result.output.model_copy(
                    update={
                        "objections": [
                            Objection(target_claim_id="question", concern="Concern", test="Test")
                        ]
                    }
                )
            return result

    model = QuestionCritic()
    result, snapshots = execute(model)
    assert result.status == "partial"
    assert result.tasks[-1].role == "critic"
    assert result.tasks[-1].status == "failed"
    assert result.tasks[-1].result is None
    assert not any(node.kind == "objection" for node in result.nodes)
    assert [role for role, _ in model.contexts] == ["framing", "strategy", "strategy", "critic"]
    assert all(AnalysisRun.model_validate(snapshot) for snapshot in snapshots)


@pytest.mark.parametrize("target", ["question", "objection_1", "revision_0"])
def test_persisted_critique_requires_an_original_strategy_claim(target):
    result, _ = execute(Model())
    data = result.model_dump(mode="json")
    critic = next(task for task in data["tasks"] if task["role"] == "critic")
    critic["result"]["objections"][0]["target_claim_id"] = target
    with pytest.raises(ValidationError, match="critique"):
        AnalysisRun.model_validate(data)


def test_role_result_and_synthesis_and_supersession_validated():
    run, _ = execute(Model())
    for mutate in (
        lambda data: data["tasks"][0].update(result=data["tasks"][-1]["result"]),
        lambda data: data["tasks"][-1]["result"].update(alternatives=["missing"]),
        lambda data: data["candidates"][0].update(supersedes="strategy_1"),
        lambda data: data["candidates"][0].update(supersedes="revision"),
    ):
        data = run.model_dump(mode="json")
        mutate(data)
        with pytest.raises(ValidationError):
            AnalysisRun.model_validate(data)
