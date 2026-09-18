"""Offline actor transport tests: no model download, GPU or external service."""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from tianji_lab import kernel, local_actor
from tianji_lab.api import create_app
from tianji_lab.local_actor import LocalActor, validate_origin
from tianji_lab.models import Scenario
from tianji_lab.offline_adjudication import ActionProposal
from tianji_lab.service import Branch, OperationError, Provenance, Service, digest
from tianji_lab.store import canonical


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", "test-local-model")
    monkeypatch.setenv("TIANJI_TOKEN", "director-secret-not-for-model")


def seed(service, role="retailer"):
    spec = Scenario(
        name="private-scenario-name",
        description="private-scenario-description",
        demand_per_tick=7,
        shipment_size=9,
        standard_cost=23,
        express_cost=41,
        standard_lead=3,
        express_lead=2,
        disturbances=[{"tick": 2, "kind": "supplier_loss", "amount": 3}],
    )
    branch = Branch(
        id="source-branch",
        name="private-branch",
        scenario_id="source-scenario",
        scenario_revision=1,
        spec=spec,
        parent_id=None,
        fork_tick=None,
        trajectory=kernel.simulate(spec, []),
        mode="forward",
        created_at="test",
        provenance=Provenance(rule_version=kernel.rule_version_for(spec)),
    ).model_dump(mode="json")
    branch = service.execute(
        "branch_import",
        {
            "bundle": {
                "schema_version": "tianji.lab.bundle.v1",
                "branch": branch,
                "digest": digest(branch),
            }
        },
        "import",
    )
    saved = service.execute(
        "observation_create",
        {"branch_id": branch["id"], "tick": 0, "actor_id": "actor-1", "role": role},
        "observe",
    )
    return branch, saved


@pytest.fixture
def lab(tmp_path):
    service = Service(tmp_path, start_worker=False)
    branch, saved = seed(service)
    yield service, branch, saved
    service.close()


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    calls = []

    def client(**kwargs):
        assert kwargs == {
            "trust_env": False,
            "follow_redirects": False,
            "timeout": local_actor.TIMEOUT_SECONDS,
        }
        calls.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(local_actor.httpx, "AsyncClient", client)
    return calls


def completion(content='{"action":"order_standard"}', **choice):
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                    **choice,
                }
            ]
        },
    )


def propose(service, saved):
    return service.execute("actor_propose", {"observation_id": saved["id"]})


def snapshot(service):
    with service.store.transaction() as db:
        return list(db.iterdump())


def test_request_projection_rules_binding_no_retention_or_adjudication(lab, monkeypatch):
    service, branch, saved = lab
    requests = []
    # The latest scenario differs, but the public rules must remain branch-frozen.
    service.execute(
        "scenario_update",
        {
            "id": branch["scenario_id"],
            "revision": 1,
            "spec": {"name": "new", "standard_cost": 999, "demand_per_tick": 1},
        },
        "update",
    )

    def handle(request):
        requests.append(request)
        assert str(request.url) == "http://127.0.0.1:8080/v1/chat/completions"
        assert "authorization" not in request.headers
        data = json.loads(request.content)
        assert data["model"] == "test-local-model"
        assert data["max_tokens"] == 96 and data["temperature"] == 0
        assert data["stream"] is False
        assert data["chat_template_kwargs"] == {"enable_thinking": False}
        schema = data["response_format"]["json_schema"]
        assert data["response_format"]["type"] == "json_schema" and schema["strict"]
        assert schema["schema"]["additionalProperties"] is False
        assert schema["schema"]["required"] == ["action"]
        view = json.loads(data["messages"][1]["content"])
        assert view == {
            "role": "retailer",
            "projection": saved["observation"]["projection"],
            "public_rules": {
                "horizon": 6,
                "demand_per_tick": 7,
                "shipment_size": 9,
                "standard_cost": 23,
                "express_cost": 41,
                "standard_lead": 3,
                "express_lead": 2,
            },
        }
        for forbidden in (
            "supplier_stock",
            "initial_inventory",
            "initial_cash",
            "supplier_loss",
            "spec_hash",
            "state_hash",
            "director-secret-not-for-model",
            "private-scenario",
            "private-branch",
            saved["observation"]["observation_hash"],
        ):
            assert forbidden not in request.content.decode()
        return completion()

    install_transport(monkeypatch, handle)
    before = snapshot(service)
    result = propose(service, saved)
    assert ActionProposal.model_validate(result).model_dump() == {
        "actor_id": "actor-1",
        "role": "retailer",
        "action": "order_standard",
        "observation_hash": saved["observation"]["observation_hash"],
        "policy_id": "local.llamacpp.v1",
    }
    assert snapshot(service) == before
    assert propose(service, saved) == result  # No durable cache or idempotent model replay.
    assert len(requests) == 2
    assert snapshot(service) == before


def test_supplier_projection_and_no_permission_substitution(tmp_path, monkeypatch):
    service = Service(tmp_path, start_worker=False)
    try:
        _, saved = seed(service, "supplier")

        def handle(request):
            view = json.loads(json.loads(request.content)["messages"][1]["content"])
            assert view["projection"] == saved["observation"]["projection"]
            assert set(view["projection"]) == {"tick", "supplier_stock", "shipments"}
            return completion()  # Forbidden, but well-formed: adjudication remains independent.

        install_transport(monkeypatch, handle)
        assert propose(service, saved)["action"] == "order_standard"
    finally:
        service.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080",
        "https://127.0.0.1",
        "http://example.org",
        "http://0.0.0.0",
        "http://127.0.0.1/",
        "http://127.0.0.1/v1",
        "http://user@127.0.0.1",
        "http://@127.0.0.1",
        "http://127.0.0.1?",
        "http://127.0.0.1#",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://127.0.0.1:",
        " http://127.0.0.1",
        "http://127.0.0.1\n",
        "http://[::1%lo]",
        "http://2130706433",
    ],
)
def test_invalid_origin_fails_closed(url, lab, monkeypatch):
    service, _, saved = lab
    service.local_actor = LocalActor(url, "local")
    calls = install_transport(monkeypatch, lambda _: pytest.fail("must not send"))
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_unavailable"
    assert url not in error.value.message
    assert not calls


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://127.1.2.3:8080", "http://[::1]:8080"])
def test_literal_loopback_origin(url):
    assert validate_origin(url) == url


@pytest.mark.parametrize("url,model", [(None, None), (None, "local"), ("http://127.0.0.1", None)])
def test_disabled(lab, monkeypatch, url, model):
    service, _, saved = lab
    service.local_actor = LocalActor(url, model)
    calls = install_transport(monkeypatch, lambda _: pytest.fail("must not send"))
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_disabled" and error.value.status == 503
    assert not calls


@pytest.mark.parametrize(
    "content",
    [
        "not-json-secret",
        '```json\n{"action":"wait"}\n```',
        '{"action":"unknown"}',
        '{"action":"wait","actor_id":"forged"}',
        '{"action":"wait","reason":"secret"}',
        '{"action":true}',
        "{}",
        '[{"action":"wait"}]',
        '{"action":"wait","action":"order_express"}',
        '"wait"',
        None,
    ],
)
def test_invalid_action_output_is_sanitized_and_not_retained(lab, monkeypatch, content):
    service, _, saved = lab
    install_transport(monkeypatch, lambda _: completion(content))
    before = snapshot(service)
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_invalid_output" and error.value.status == 502
    assert error.value.message == "Local model output is invalid"
    assert snapshot(service) == before


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json-secret"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, content=b"x" * 16_385),
        completion(finish_reason="length"),
        completion(message={"content": '{"action":"wait"}', "tool_calls": [{}]}),
        completion(message={"content": '{"action":"wait"}', "reasoning_content": "secret"}),
    ],
)
def test_invalid_envelope(lab, monkeypatch, response):
    service, _, saved = lab
    install_transport(monkeypatch, lambda _: response)
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_invalid_output"


@pytest.mark.parametrize("status", [302, 400, 500])
def test_failed_http_and_redirect_never_followed(lab, monkeypatch, status):
    service, _, saved = lab
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            status, headers={"location": "https://remote.invalid/secret"}, text="private-error"
        )

    install_transport(monkeypatch, handle)
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_unavailable"
    assert len(seen) == 1 and "private-error" not in error.value.message


@pytest.mark.parametrize("failure", [httpx.ConnectError("private"), httpx.ReadTimeout("private")])
def test_network_error_sanitized(lab, monkeypatch, failure):
    service, _, saved = lab

    def handle(_):
        raise failure

    install_transport(monkeypatch, handle)
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_unavailable" and "private" not in error.value.message


def test_total_deadline_cancels_io_and_releases_slot(lab, monkeypatch):
    service, _, saved = lab
    cancelled = threading.Event()

    async def handle(_):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
        return completion()

    assert local_actor.TIMEOUT_SECONDS <= 30
    monkeypatch.setattr(local_actor, "TIMEOUT_SECONDS", 0.02)
    install_transport(monkeypatch, handle)
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "actor_unavailable" and cancelled.is_set()
    assert local_actor._CALL_SLOT.acquire(blocking=False)
    local_actor._CALL_SLOT.release()


def test_busy_is_nonblocking_and_network_holds_no_sqlite_transaction(lab, monkeypatch):
    service, _, saved = lab
    entered, release = threading.Event(), threading.Event()

    def handle(_):
        entered.set()
        assert release.wait(5)
        return completion()

    install_transport(monkeypatch, handle)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(propose, service, saved)
        assert entered.wait(2)
        try:
            # A real write succeeds while model IO is blocked, proving the DB lock is gone.
            writing = pool.submit(service.execute, "workspace_attach", {}, "while-model-busy")
            assert writing.result(timeout=1)["revision"] == 1
            with pytest.raises(OperationError) as error:
                propose(service, saved)
            assert error.value.code == "actor_busy" and error.value.status == 409
        finally:
            release.set()
        assert pending.result(timeout=2)["action"] == "order_standard"
    assert propose(service, saved)["action"] == "order_standard"


def test_saved_observation_tampering_blocked_before_io(lab, monkeypatch):
    service, _, saved = lab
    calls = install_transport(monkeypatch, lambda _: pytest.fail("must not send"))
    value = saved["observation"]
    value["projection"]["cash"] = 123
    # Even self-consistent hashes cannot replace the actual frozen role projection.
    value["projection_hash"] = digest(value["projection"])
    value["observation_hash"] = digest({k: v for k, v in value.items() if k != "observation_hash"})
    with service.store.transaction() as db:
        db.execute(
            "UPDATE observation SET observation_json=? WHERE id=?", (canonical(value), saved["id"])
        )
    with pytest.raises(OperationError) as error:
        propose(service, saved)
    assert error.value.code == "validation" and not calls


def test_http_operation_registry_and_strict_input(tmp_path, monkeypatch):
    install_transport(monkeypatch, lambda _: completion())
    with TestClient(create_app(tmp_path, token="director-test", start_worker=False)) as client:
        _, saved = seed(client.app.state.service)
        path = "/api/operations/actor_propose"
        arguments = {"observation_id": saved["id"]}
        assert client.post(path, json={"arguments": arguments}).status_code == 401
        client.headers["Authorization"] = "Bearer director-test"
        capability = next(
            c for c in client.get("/api/capabilities").json() if c["name"] == "actor_propose"
        )
        assert capability["mutating"] is False
        assert capability["input_schema"]["required"] == ["observation_id"]
        assert set(capability["input_schema"]["properties"]) == {"observation_id"}
        result = client.post(path, json={"arguments": arguments})
        assert result.status_code == 200
        assert result.json()["data"]["policy_id"] == "local.llamacpp.v1"
        for extra in ("url", "model", "role", "actor_id", "policy_id", "projection"):
            assert (
                client.post(path, json={"arguments": {**arguments, extra: "forged"}}).status_code
                == 422
            )
        assert (
            client.post(path, json={"arguments": {"observation_id": "missing"}}).status_code == 404
        )
        assert client.post(path, json={"arguments": {"observation_id": True}}).status_code == 422
