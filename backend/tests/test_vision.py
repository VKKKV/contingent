"""Contract, transport and persistence tests; completions below are test fixtures only."""

import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tianji_lab import local_actor, vision
from tianji_lab.api import create_app
from tianji_lab.service import OperationError, Service
from tianji_lab.vision import LocalVision, VisionDraft, VisionPlan, VisionRequest


def plan_data():
    return {
        "title": "社区教育目标的候选转折",
        "interpretation": "以公共利益为视角探索教育机会，以下为待验证的假设。",
        "assumptions": ["参与者愿意协作"],
        "tensions": ["覆盖范围与资源投入之间的冲突"],
        "nodes": [
            {
                "id": f"n{i}",
                "title": title,
                "stage": stage,
                "actors": ["社区组织"],
                "action": "召开协作会议",
                "mechanism": "信息交流可能减少误解，也可能暴露利益冲突",
                "prerequisites": ["参与意愿"],
                "risks": ["参与不足"],
                "signals": ["后续可以观察持续参与人数"],
            }
            for i, title, stage in [
                (1, "共识", 1),
                (2, "试点", 2),
                (3, "替代协作", 2),
                (4, "扩展", 4),
            ]
        ],
        "paths": [
            {
                "id": f"p{i}",
                "title": title,
                "summary": "从协作条件到目标状态的候选路径",
                "node_ids": ids,
                "tradeoff": "需要投入时间和资源",
            }
            for i, title, ids in [
                (1, "试点优先", ["n1", "n2", "n4"]),
                (2, "替代组织", ["n1", "n3", "n4"]),
            ]
        ],
    }


def draft_data():
    return {
        "request": VisionRequest(vision="让社区的孩子拥有平等教育机会").model_dump(),
        "plan": plan_data(),
        "model": "test-local",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "grounding": "model_hypothesis",
    }


def test_analysis_stats_counts_only_explicit_saves(tmp_path):
    with TestClient(create_app(tmp_path, token="stats-test")) as client:
        url = "/api/operations/analysis_stats"
        assert client.post(url, json={"arguments": {}}).status_code == 401
        client.headers["Authorization"] = "Bearer stats-test"

        def stats():
            response = client.post(url, json={"arguments": {}})
            assert response.status_code == 200
            return response.json()["data"]

        assert stats() == {
            "saved_analyses": 0,
            "nodes": 0,
            "paths": 0,
            "scope": "saved_analyses_only",
            "architecture": "single_model_single_call",
        }
        payload = {"arguments": {"draft": draft_data()}, "request_id": "save-count"}
        for _ in range(2):
            assert client.post("/api/operations/vision_save", json=payload).status_code == 200
        assert stats()["saved_analyses"] == 1
        assert stats()["nodes"] == 4 and stats()["paths"] == 2
        payload["request_id"] = "second-copy"
        assert client.post("/api/operations/vision_save", json=payload).status_code == 200
        assert stats()["saved_analyses"] == 2
        assert stats()["nodes"] == 8 and stats()["paths"] == 4


def completion(content=None, **choice):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(plan_data()) if content is None else content,
                    },
                    **choice,
                }
            ]
        },
    )


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    calls = []

    def client(**kwargs):
        assert kwargs == {
            "trust_env": False,
            "follow_redirects": False,
            "timeout": vision.TIMEOUT_SECONDS,
        }
        calls.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(vision.httpx, "AsyncClient", client)
    return calls


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", "http://127.0.0.1:18789")
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", "test-local")


@pytest.fixture
def lab(tmp_path):
    service = Service(tmp_path, start_worker=False)
    yield service
    service.close()


def generate(service):
    return service.execute("vision_generate", {"vision": "让社区的孩子拥有平等教育机会"})


def snapshot(service):
    with service.store.transaction() as db:
        return list(db.iterdump())


def test_contract_and_schema():
    request = VisionRequest(vision="和平")
    assert request.model_dump() == {
        "vision": "和平",
        "horizon": "未来十年",
        "perspective": "公共利益与可协作的行动者",
        "constraints": "",
    }
    schema = VisionRequest.model_json_schema()
    assert schema["required"] == ["vision"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["vision"]["maxLength"] == 1200
    schema = VisionPlan.model_json_schema()
    for definition in [schema, *schema["$defs"].values()]:
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    assert VisionPlan.model_validate(plan_data()).model_dump() == plan_data()
    no_tensions = plan_data()
    no_tensions["tensions"] = []
    assert VisionPlan.model_validate(no_tensions).tensions == []
    assert VisionDraft.model_validate(draft_data()).grounding == "model_hypothesis"


@pytest.mark.parametrize(
    "field,value",
    [
        ("vision", ""),
        ("vision", "x" * 1201),
        ("vision", True),
        ("horizon", ""),
        ("horizon", "x" * 101),
        ("perspective", ""),
        ("perspective", "x" * 201),
        ("constraints", "x" * 1001),
        ("sources", []),
    ],
)
def test_request_bounds(field, value):
    with pytest.raises(ValidationError):
        VisionRequest.model_validate({"vision": "和平", field: value})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["nodes"][1].update(id="n1"),
        lambda p: p["paths"][1].update(id="p1"),
        lambda p: p["paths"][0].update(node_ids=["n1", "missing"]),
        lambda p: p["paths"][0].update(node_ids=["n2", "n1", "n4"]),
        lambda p: p["paths"][0].update(node_ids=["n1", "n1", "n4"]),
        lambda p: p["paths"][0].update(node_ids=["n2", "n3", "n4"]),
        lambda p: p["paths"][1].update(node_ids=["n1", "n2", "n4"]),
        lambda p: p["paths"][1].update(node_ids=["n1", "n4"]),
        lambda p: p["nodes"][0].update(stage=True),
        lambda p: p["nodes"][0].update(stage=5),
        lambda p: p["nodes"][0].update(stage=0),
        lambda p: p["nodes"][0].update(stage="1"),
        lambda p: p["nodes"][0].update(actors=[]),
        lambda p: p["nodes"][0].update(risks=["风险"] * 4),
        lambda p: p["nodes"][0].update(action="x" * 401),
        lambda p: p.update(interpretation="x" * 601),
        lambda p: p.update(assumptions=[]),
        lambda p: p.update(tensions=["冲突"] * 4),
        lambda p: p.update(nodes=p["nodes"][:3]),
        lambda p: p.update(nodes=p["nodes"] * 3),
        lambda p: p.update(paths=p["paths"][:1]),
        lambda p: p.update(paths=p["paths"] * 2),
        lambda p: p["paths"][0].update(node_ids=["n1"]),
        lambda p: p["paths"][0].update(node_ids=["n1"] * 6),
        lambda p: p.update(probability=0.9),
        lambda p: p.update(sources=["伪造来源"]),
    ],
)
def test_invalid_graph_and_bounds(mutation):
    data = plan_data()
    mutation(data)
    with pytest.raises(ValidationError):
        VisionPlan.model_validate(data)


def test_subset_path_is_not_a_distinct_strategy():
    data = plan_data()
    data["nodes"][2]["stage"] = 3
    data["paths"][0]["node_ids"] = ["n1", "n2", "n3", "n4"]
    data["paths"][1]["node_ids"] = ["n1", "n3", "n4"]
    with pytest.raises(ValidationError, match="distinct intervention"):
        VisionPlan.model_validate(data)


def test_real_transport_contract_ephemeral_no_secret_or_supply_chain_mapping(lab, monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        assert str(request.url) == "http://127.0.0.1:18789/v1/chat/completions"
        assert "authorization" not in request.headers
        payload = json.loads(request.content)
        assert payload["model"] == "test-local"
        assert payload["max_tokens"] == 3500
        assert payload["stream"] is False and payload["cache_prompt"] is False
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert payload["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "vision_plan",
                "strict": True,
                "schema": VisionPlan.model_json_schema(),
            },
        }
        assert json.loads(payload["messages"][1]["content"]) == draft_data()["request"]
        prompt = payload["messages"][0]["content"]
        for required in ["回溯", "反应", "信号", "AI 必然带来和平", "中文", "概率", "正式仿真"]:
            assert required in prompt
        assert "order_standard" not in request.content.decode()
        return completion()

    install_transport(monkeypatch, handle)
    before = snapshot(lab)
    first = generate(lab)
    assert VisionDraft.model_validate(first).plan.model_dump() == plan_data()
    assert first["grounding"] == "model_hypothesis" and first["model"] == "test-local"
    generate(lab)
    assert len(requests) == 2 and snapshot(lab) == before


@pytest.mark.parametrize(
    "response",
    [
        completion("not-json-private"),
        completion("```json\n{}\n```"),
        completion('{"title":"duplicate","title":"private"}'),
        completion(json.dumps({**plan_data(), "grounding": "verified"})),
        completion(finish_reason="length"),
        completion(message={"role": "assistant", "content": "{}", "reasoning_content": "private"}),
        completion(message={"role": "assistant", "content": "{}", "reasoning": "private"}),
        completion(message={"role": "assistant", "content": "{}", "tool_calls": [{}]}),
        completion(message={"role": "assistant", "content": "{}", "refusal": "private"}),
        completion(message={"role": "assistant", "content": None}),
        httpx.Response(200, content=b"x" * 65_537),
        httpx.Response(200, content=b"\xff"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": "private"}),
        httpx.Response(200, json={"choices": [None]}),
    ],
)
def test_invalid_output_no_fallback_or_retention(lab, monkeypatch, response):
    install_transport(monkeypatch, lambda _: response)
    before = snapshot(lab)
    with pytest.raises(OperationError) as error:
        generate(lab)
    assert (error.value.code, error.value.status) == ("vision_invalid_output", 502)
    assert error.value.message == "Local model output is invalid"
    assert snapshot(lab) == before
    assert local_actor._CALL_SLOT.acquire(blocking=False)
    local_actor._CALL_SLOT.release()


@pytest.mark.parametrize(
    "url,model,code",
    [
        (None, None, "vision_disabled"),
        ("http://127.0.0.1", None, "vision_disabled"),
        (None, "local", "vision_disabled"),
        ("https://example.com/private", "local", "vision_unavailable"),
        ("http://localhost:8080", "local", "vision_unavailable"),
        ("http://127.0.0.1/", "local", "vision_unavailable"),
        ("http://127.0.0.1", " ", "vision_unavailable"),
        ("http://127.0.0.1", "x" * 201, "vision_unavailable"),
    ],
)
def test_disabled_and_invalid_config(lab, monkeypatch, url, model, code):
    lab.local_vision = LocalVision(url, model)
    calls = install_transport(monkeypatch, lambda _: pytest.fail("must not send"))
    with pytest.raises(OperationError) as error:
        generate(lab)
    assert error.value.code == code and error.value.status == 503
    assert not calls and "private" not in error.value.message


@pytest.mark.parametrize("status", [302, 400, 500])
def test_status_error_sanitized_and_redirects_not_followed(lab, monkeypatch, status):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status, text="private", headers={"location": "https://remote.invalid"}
        )

    install_transport(monkeypatch, handle)
    with pytest.raises(OperationError) as error:
        generate(lab)
    assert error.value.code == "vision_unavailable" and "private" not in error.value.message
    assert len(requests) == 1


@pytest.mark.parametrize("failure", [httpx.ConnectError("private"), httpx.ReadTimeout("private")])
def test_network_failure(lab, monkeypatch, failure):
    def handle(_):
        raise failure

    install_transport(monkeypatch, handle)
    with pytest.raises(OperationError) as error:
        generate(lab)
    assert error.value.code == "vision_unavailable" and "private" not in error.value.message


def test_total_deadline_releases_shared_slot(lab, monkeypatch):
    cancelled = threading.Event()

    async def handle(_):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
        return completion()

    assert vision.TIMEOUT_SECONDS == 180
    monkeypatch.setattr(vision, "TIMEOUT_SECONDS", 0.02)
    install_transport(monkeypatch, handle)
    with pytest.raises(OperationError) as error:
        generate(lab)
    assert error.value.code == "vision_unavailable" and cancelled.is_set()
    assert local_actor._CALL_SLOT.acquire(blocking=False)
    local_actor._CALL_SLOT.release()


def test_busy_and_no_transaction_during_network(lab, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def handle(_):
        entered.set()
        assert release.wait(5)
        return completion()

    install_transport(monkeypatch, handle)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(generate, lab)
        assert entered.wait(2)
        try:
            saved = pool.submit(lab.execute, "vision_save", {"draft": draft_data()}, "during-io")
            assert saved.result(timeout=1)["draft"] == draft_data()
            with pytest.raises(OperationError) as error:
                generate(lab)
            assert error.value.code == "vision_busy" and error.value.status == 409
            assert not local_actor._CALL_SLOT.acquire(blocking=False)
        finally:
            release.set()
        assert pending.result(timeout=2)["grounding"] == "model_hypothesis"
    assert generate(lab)["plan"] == plan_data()


def test_explicit_save_idempotency_immutable_read_list_restart_and_cap(tmp_path):
    service = Service(tmp_path, start_worker=False)
    try:
        assert service.execute("vision_list", {}) == {"items": []}
        args = {"draft": draft_data()}
        with pytest.raises(OperationError, match="request_id"):
            service.execute("vision_save", args)
        first = service.execute("vision_save", args, "first")
        assert service.execute("vision_save", args, "first") == first
        changed = copy.deepcopy(args)
        changed["draft"]["plan"]["title"] = "不同标题"
        with pytest.raises(OperationError) as conflict:
            service.execute("vision_save", changed, "first")
        assert conflict.value.code == "idempotency_conflict"
        second = service.execute("vision_save", changed, "second")
        assert service.execute("vision_get", {"id": first["id"]}) == first
        assert service.execute("vision_list", {})["items"] == [
            {
                "id": s["id"],
                "created_at": s["created_at"],
                "title": s["draft"]["plan"]["title"],
                "vision": s["draft"]["request"]["vision"],
            }
            for s in [second, first]
        ]
        service.close()
        service = Service(tmp_path, start_worker=False)
        assert service.execute("vision_get", {"id": first["id"]}) == first
        for i in range(98):
            service.execute("vision_save", args, f"save-{i}")
        before = snapshot(service)
        with pytest.raises(OperationError) as cap:
            service.execute("vision_save", args, "over-cap")
        assert (cap.value.code, cap.value.status) == ("record_limit", 409)
        assert snapshot(service) == before
        assert service.execute("vision_save", args, "first") == first
        assert len(service.execute("vision_list", {})["items"]) == 100
        with pytest.raises(OperationError) as missing:
            service.execute("vision_get", {"id": "missing"})
        assert missing.value.status == 404
    finally:
        service.close()


def test_save_revalidates_graph_and_grounding_without_partial_write(lab):
    before = snapshot(lab)
    for mutation in [
        lambda d: d.update(grounding="verified"),
        lambda d: d["plan"]["nodes"][0].update(stage=True),
        lambda d: d["plan"]["paths"][0].update(node_ids=["unknown", "n4"]),
    ]:
        data = draft_data()
        mutation(data)
        with pytest.raises(OperationError) as error:
            lab.execute("vision_save", {"draft": data}, "bad")
        assert error.value.code == "validation"
        assert snapshot(lab) == before


def test_http_registry_auth_strict_args_generate_save_read(tmp_path, monkeypatch):
    install_transport(monkeypatch, lambda _: completion())
    with TestClient(create_app(tmp_path, token="test-token", start_worker=False)) as client:
        generate_url = "/api/operations/vision_generate"
        assert (
            client.post(generate_url, json={"arguments": {"vision": "教育平等"}}).status_code == 401
        )
        client.headers["Authorization"] = "Bearer test-token"
        catalog = {c["name"]: c for c in client.get("/api/capabilities").json()}
        assert catalog["vision_generate"]["input_schema"] == VisionRequest.model_json_schema()
        assert catalog["vision_generate"]["mutating"] is False
        assert catalog["vision_save"]["mutating"] is True
        assert catalog["vision_get"]["mutating"] is False
        assert catalog["vision_list"]["mutating"] is False
        assert (
            client.post(
                generate_url, json={"arguments": {"vision": "和平", "model": "forged"}}
            ).status_code
            == 422
        )
        response = client.post(generate_url, json={"arguments": {"vision": "和平"}})
        assert response.status_code == 200
        draft = response.json()["data"]
        save_url = "/api/operations/vision_save"
        payload = {"arguments": {"draft": draft}, "request_id": "save"}
        saved = client.post(save_url, json=payload).json()["data"]
        assert client.post(save_url, json=payload).json()["data"] == saved
        assert (
            client.post(
                "/api/operations/vision_get", json={"arguments": {"id": saved["id"]}}
            ).json()["data"]
            == saved
        )
        assert (
            client.post("/api/operations/vision_list", json={"arguments": {}}).json()["data"][
                "items"
            ][0]["id"]
            == saved["id"]
        )
        assert (
            client.post(
                save_url, json=payload, headers={"Origin": "https://remote.invalid"}
            ).status_code
            == 403
        )
        client.app.state.service.local_vision = LocalVision(None, None)
        disabled = client.post(generate_url, json={"arguments": {"vision": "和平"}})
        assert disabled.status_code == 503 and disabled.json()["error"]["code"] == "vision_disabled"
