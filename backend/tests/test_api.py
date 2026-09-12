from fastapi.testclient import TestClient

from tianji_lab.api import create_app


def test_auth_origin_capabilities_validation_and_limit(tmp_path):
    with TestClient(create_app(tmp_path, token="test-only", start_worker=False)) as client:
        assert client.get("/health").json() == {"ok": True, "version": "0.3.0"}
        assert client.get("/api/capabilities").status_code == 401
        client.headers["Authorization"] = "Bearer test-only"
        catalog = client.get("/api/capabilities").json()
        assert any(item["name"] == "run_backward" and item["input_schema"] for item in catalog)
        route = "/api/operations/scenario_list"
        assert client.post(route, json={"arguments": {}}).json()["ok"]
        assert (
            client.post(
                route, json={"arguments": {}}, headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                route, json={"arguments": {}}, headers={"Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                route, json={"arguments": {}}, headers={"Origin": "http://testserver"}
            ).status_code
            == 200
        )
        assert client.post(route, content=b"x" * 1_048_577).status_code == 422
        assert client.post(route, content=b"not-json").status_code == 422
        assert client.post(route, json={"arguments": {"unexpected": True}}).status_code == 422
        assert client.post("/api/operations/missing", json={"arguments": {}}).status_code == 404
        method_error = client.put("/api/capabilities")
        assert method_error.status_code == 405
        assert method_error.json()["ok"] is False
        assert method_error.json()["error"]["code"] == "method_not_allowed"
        assert (
            client.post(
                "/api/operations/scenario_create", json={"arguments": {"spec": {"name": "X"}}}
            ).status_code
            == 422
        )
        response = client.post(
            "/api/operations/scenario_create",
            json={"arguments": {"spec": {"name": "X", "horizon": True}}, "request_id": "strict"},
        )
        assert response.status_code == 422


def test_generated_token_is_private_and_persistent(tmp_path, monkeypatch):
    monkeypatch.delenv("TIANJI_TOKEN", raising=False)
    first = create_app(tmp_path, start_worker=False)
    first.state.service.close()
    token = (tmp_path / "token").read_text()
    assert (tmp_path / "token").stat().st_mode & 0o777 == 0o600
    with TestClient(create_app(tmp_path, start_worker=False)) as client:
        assert (
            client.get(
                "/api/capabilities", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 200
        )
