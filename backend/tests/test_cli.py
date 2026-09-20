"""Registry-wide transport coverage and real loopback subprocess acceptance tests."""

import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import pytest
import uvicorn

from tianji_lab import cli
from tianji_lab.api import create_app
from tianji_lab.service import OPERATIONS, Service

TOKEN = "test-cli-private-token"
ROOT = Path(__file__).resolve().parents[2]


def invoke(monkeypatch, capsys, argv, handler):
    monkeypatch.setenv("TIANJI_TOKEN", TOKEN)
    status = cli.main(argv, transport=httpx.MockTransport(handler))
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    return status, json.loads(captured.out), captured.err


@pytest.mark.parametrize("name", OPERATIONS)
def test_every_live_operation_dispatches(monkeypatch, capsys, name):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        if request.url.path == "/api/capabilities":
            return httpx.Response(200, json=Service.capabilities())
        assert request.url.path == f"/api/operations/{name}"
        payload = json.loads(request.content)
        assert payload["arguments"] == {"transport_test": True}
        if OPERATIONS[name][1]:
            uuid.UUID(payload["request_id"])
        else:
            assert "request_id" not in payload
        assert request.extensions["timeout"]["read"] == {
            "vision_generate": 190,
            "actor_propose": 40,
        }.get(name, 15)
        return httpx.Response(200, json={"ok": True, "data": {"called": name}})

    status, body, err = invoke(
        monkeypatch,
        capsys,
        ["call", name, "--json", '{"transport_test":true}'],
        handle,
    )
    assert status == 0 and body == {"ok": True, "data": {"called": name}}
    assert len(requests) == 2
    assert bool(err) == OPERATIONS[name][1]


def test_catalog_and_schema_are_dynamic(monkeypatch, capsys):
    item = {
        "name": "future_operation",
        "mutating": True,
        "input_schema": {"type": "object"},
        "description": "Added by server, not client",
    }

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=[item])
        assert request.url.path == "/api/operations/future_operation"
        assert json.loads(request.content)["request_id"] == "my-retry-key"
        assert request.extensions["timeout"]["read"] == 250
        return httpx.Response(200, json={"ok": True, "data": None})

    assert invoke(monkeypatch, capsys, ["operations"], handle)[1]["data"] == [item]
    assert invoke(monkeypatch, capsys, ["schema", item["name"]], handle)[1]["data"] == item
    status, _, err = invoke(
        monkeypatch,
        capsys,
        [
            "--timeout",
            "250",
            "call",
            item["name"],
            "--request-id",
            "my-retry-key",
        ],
        handle,
    )
    assert status == 0 and json.loads(err) == {"request_id": "my-retry-key"}
    status, body, _ = invoke(monkeypatch, capsys, ["call", "missing"], handle)
    assert status == 1 and body["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "true",
        "0",
        "bad",
        '{"x":1,"x":2}',
        '{"x":{"y":1,"y":2}}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":-Infinity}',
        '{"x":1e999}',
        '{"x":"\\ud800"}',
        "[" * 2000,
        '{"x":"' + "x" * cli.MAX_JSON_BYTES + '"}',
    ],
)
def test_invalid_json_is_local_sanitized_error(monkeypatch, capsys, raw):
    def handle(request):
        pytest.fail("Invalid input must not access network")

    status, body, _ = invoke(monkeypatch, capsys, ["call", "scenario_list", "--json", raw], handle)
    assert status == 1 and body["ok"] is False


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1",
        "http://example.com",
        "http://127.0.0.1@evil.invalid",
        "http://user:secret@localhost",
        "http://localhost/path",
        "http://localhost?",
        "http://localhost#",
        "http://127.0.0.1:0",
        "http://localhost:65536",
        "http://localhost:bad",
        "http://localhost:",
        "http://[",
        "http://localhost\n",
        "http://localhost\\@evil.invalid",
        "http://localhost%2f.evil.invalid",
        "http://127.1",
    ],
)
def test_url_rejected_before_credential_access(monkeypatch, capsys, url):
    def forbidden(*args):
        pytest.fail("Invalid URL must be rejected before token access")

    monkeypatch.setattr(cli, "read_token", forbidden)
    status = cli.main(["operations", "--url", url])
    assert status == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_url"


@pytest.mark.parametrize("url", ["http://localhost", "http://127.0.0.2:8787/", "http://[::1]:8787"])
def test_valid_loopback_url(url):
    assert cli.validate_url(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "argv",
    [
        ["call", "scenario_list", "--json", "{}", "--stdin"],
        ["call", "scenario_list", "--json", "{}", "--file", "input.json"],
        ["operations", "--token", TOKEN],
        ["operations", "--timeout", "nan"],
        ["operations", "--timeout", "0"],
        ["operations", "--timeout", "301"],
        ["operations", "--timeout", TOKEN],
        [TOKEN],
        ["call", "scenario_list", "--request-id", ""],
        ["call", "scenario_list", "--request-id", "x" * 129],
        ["--url", "http://localhost:8787", "serve"],
        ["--token-file", "token", "serve"],
    ],
)
def test_usage_errors_do_not_echo_arguments(monkeypatch, capsys, argv):
    status, body, _ = invoke(
        monkeypatch, capsys, argv, lambda r: pytest.fail("No request expected")
    )
    assert status == 1 and body["ok"] is False


@pytest.mark.parametrize(
    "argv",
    [
        ["mcp", "--token-file", TOKEN],
        ["--token-file", TOKEN, "mcp"],
        ["mcp", "--timeout", TOKEN],
        ["--timeout", TOKEN, "mcp"],
        ["--timeout=" + TOKEN, "mcp"],
        ["--timeout", "20", "mcp"],
        ["--timeout=20", "mcp"],
        ["mcp", "--timeout", "20"],
        ["mcp", "--unknown", TOKEN],
        ["mcp", "--url"],
    ],
)
def test_mcp_usage_errors_only_emit_sanitized_stderr(monkeypatch, capsys, argv):
    monkeypatch.setenv("TIANJI_TOKEN", TOKEN)
    assert cli.main(argv) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert TOKEN not in captured.err
    assert json.loads(captured.err)["error"]["code"] == "usage"


@pytest.mark.parametrize("failure", ["missing_token", "empty_token", "invalid_url", "global_url"])
def test_real_mcp_startup_errors_leave_stdout_empty(tmp_path, failure):
    env = {**os.environ, "TIANJI_URL": cli.DEFAULT_URL, "TIANJI_TOKEN": TOKEN}
    argv = ["mcp"]
    expected_code = "credentials"
    if failure == "missing_token":
        env.pop("TIANJI_TOKEN")
    elif failure == "empty_token":
        env["TIANJI_TOKEN"] = ""
    else:
        url = f"http://user:{TOKEN}@localhost/private"
        expected_code = "invalid_url"
        if failure == "global_url":
            argv = ["--url", url, "mcp"]
        else:
            env["TIANJI_URL"] = url
    result = subprocess.run(
        [sys.executable, "-m", "tianji_lab", *argv],
        cwd=tmp_path,
        env=env,
        input="",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert TOKEN not in result.stderr and "Traceback" not in result.stderr
    assert json.loads(result.stderr)["error"]["code"] == expected_code


def test_mcp_missing_token_never_reads_default_credentials(monkeypatch, capsys):
    monkeypatch.delenv("TIANJI_TOKEN", raising=False)
    monkeypatch.setattr(
        cli, "read_token", lambda *args: pytest.fail("MCP must not read local credentials")
    )
    assert cli.main(["mcp", "--url", cli.DEFAULT_URL]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "credentials"


def test_real_mcp_auth_failure_only_emits_sanitized_stderr(live_api, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "tianji_lab", "mcp", "--url", live_api],
        env={**os.environ, "TIANJI_TOKEN": "wrong-" + TOKEN},
        cwd=tmp_path,
        input="",
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 1 and result.stdout == ""
    assert TOKEN not in result.stderr and live_api not in result.stderr
    assert "Traceback" not in result.stderr
    assert json.loads(result.stderr)["error"]["code"] == "client_error"


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt, cli.CLIError])
def test_mcp_adapter_errors_are_sanitized_stderr(monkeypatch, capsys, failure):
    from tianji_lab import mcp_server

    async def failing_adapter(url):
        # Explicit test double: never opens HTTP or stdio transports.
        if failure is cli.CLIError:
            raise failure("test_error", TOKEN, detail=TOKEN)
        raise failure(TOKEN)

    monkeypatch.setenv("TIANJI_TOKEN", TOKEN)
    monkeypatch.setattr(mcp_server, "run", failing_adapter)
    assert cli.main(["mcp", "--url", cli.DEFAULT_URL]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert TOKEN not in captured.err and "Traceback" not in captured.err
    assert json.loads(captured.err)["ok"] is False


def test_mcp_success_does_not_append_cli_envelope(monkeypatch, capsys):
    from tianji_lab import mcp_server

    async def adapter_double(url):
        # Stand-in SDK output must pass through untouched, without a CLI envelope.
        assert url == cli.DEFAULT_URL
        print('{"jsonrpc":"2.0","id":1,"result":{}}')

    monkeypatch.setenv("TIANJI_TOKEN", TOKEN)
    monkeypatch.setattr(mcp_server, "run", adapter_double)
    assert cli.main(["mcp", "--url", cli.DEFAULT_URL]) == 0
    captured = capsys.readouterr()
    assert captured.out == '{"jsonrpc":"2.0","id":1,"result":{}}\n'
    assert captured.err == ""


def test_mcp_as_option_value_does_not_redirect_regular_cli(monkeypatch, capsys):
    monkeypatch.setenv("TIANJI_TOKEN", TOKEN)
    assert cli.main(["--url", "mcp", "health"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out)["error"]["code"] == "invalid_url"


def test_health_never_loads_or_sends_credentials(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "read_token", lambda p: pytest.fail("Health does not load credentials")
    )

    def handle(request):
        assert request.url.path == "/health" and "Authorization" not in request.headers
        return httpx.Response(200, json={"ok": True, "version": "test"})

    assert invoke(monkeypatch, capsys, ["health", "--token-file", "/missing"], handle)[1] == {
        "ok": True,
        "data": {"ok": True, "version": "test"},
    }


def test_token_file_precedence_and_default(monkeypatch, tmp_path):
    path = tmp_path / "token"
    path.write_text("file-token\n")
    monkeypatch.setattr(cli, "DEFAULT_TOKEN_FILE", path)
    monkeypatch.setenv("TIANJI_TOKEN", "environment-token")
    assert cli.read_token(path) == "file-token"
    assert cli.read_token(None) == "environment-token"
    monkeypatch.delenv("TIANJI_TOKEN")
    assert cli.read_token(None) == "file-token"


@pytest.mark.parametrize("content", [b"", b"x\ny", b"\xff", b"x" * 8193])
def test_invalid_token_files_fail_cleanly(monkeypatch, capsys, tmp_path, content):
    path = tmp_path / "token"
    path.write_bytes(content)
    status, body, _ = invoke(
        monkeypatch,
        capsys,
        ["operations", "--token-file", str(path)],
        lambda r: pytest.fail("No request expected"),
    )
    assert status == 1 and body["error"]["code"] == "credentials"


def test_bounded_stdin_and_files(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"x":"' + "x" * cli.MAX_JSON_BYTES + '"}'))
    status, body, _ = invoke(
        monkeypatch,
        capsys,
        ["call", "scenario_list", "--stdin"],
        lambda r: pytest.fail("No request expected"),
    )
    assert status == 1 and body["error"]["code"] == "body_too_large"
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (cli.MAX_JSON_BYTES + 1))
    assert (
        invoke(
            monkeypatch,
            capsys,
            ["call", "scenario_list", "--file", str(path)],
            lambda r: pytest.fail("No request expected"),
        )[0]
        == 1
    )
    path.write_bytes(b"\xff")
    assert (
        invoke(
            monkeypatch,
            capsys,
            ["call", "scenario_list", "--file", str(path)],
            lambda r: pytest.fail("No request expected"),
        )[0]
        == 1
    )
    path.unlink()
    assert (
        invoke(
            monkeypatch,
            capsys,
            ["call", "scenario_list", "--file", str(path)],
            lambda r: pytest.fail("No request expected"),
        )[1]["error"]["code"]
        == "input"
    )


@pytest.mark.parametrize(
    "failure", ["timeout", "connect", "redirect", "html", "envelope", "server"]
)
@pytest.mark.parametrize("name", ["scenario_create", "scenario_list"])
def test_failures_never_retry_and_mutations_are_ambiguous(monkeypatch, capsys, failure, name):
    posts = []

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=Service.capabilities())
        posts.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(TOKEN)
        if failure == "connect":
            raise httpx.ConnectError(TOKEN)
        if failure == "redirect":
            return httpx.Response(307, headers={"location": f"http://evil.invalid/{TOKEN}"})
        if failure == "html":
            return httpx.Response(502, text=f"<html>{TOKEN}</html>")
        if failure == "server":
            return httpx.Response(
                500, json={"ok": False, "error": {"code": "oops", "message": TOKEN}}
            )
        return httpx.Response(200, json={"secret": TOKEN})

    status, body, err = invoke(monkeypatch, capsys, ["call", name], handle)
    assert status == 1 and len(posts) == 1
    if OPERATIONS[name][1]:
        assert body["error"]["ambiguous"] is True
        assert "ambiguous" in body["error"]["message"]
        assert body["error"]["request_id"] == json.loads(err)["request_id"]
    else:
        assert not body["error"].get("ambiguous")


def test_server_envelope_secrets_are_redacted(monkeypatch, capsys):
    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=Service.capabilities())
        return httpx.Response(
            422,
            json={
                "ok": False,
                "error": {
                    "code": "validation",
                    "message": f"input_value=Bearer {TOKEN}",
                    "nested": [TOKEN],
                },
            },
        )

    status, body, _ = invoke(monkeypatch, capsys, ["call", "scenario_create"], handle)
    assert status == 1 and "[REDACTED]" in body["error"]["message"]


def test_proxy_environment_is_ignored(monkeypatch, capsys):
    original = httpx.Client
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    monkeypatch.setenv("HTTP_PROXY", "http://evil.invalid")
    invoke(
        monkeypatch,
        capsys,
        ["operations"],
        lambda r: httpx.Response(200, json=Service.capabilities()),
    )
    assert captured["trust_env"] is False and captured["follow_redirects"] is False


@pytest.fixture
def live_api(tmp_path):
    app = create_app(tmp_path / "data", token=TOKEN, start_worker=False)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        with httpx.Client(trust_env=False, timeout=0.2) as client:
            while time.monotonic() < deadline:
                try:
                    if client.get(url + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.02)
            else:
                pytest.fail("Live test API failed to start")
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


def subprocess_cli(live_api, tmp_path, *argv, stdin=None, wrapper=False, token=TOKEN):
    env = {
        **os.environ,
        "TIANJI_TOKEN": token,
        "TIANJI_URL": live_api,
        "HTTP_PROXY": "http://127.0.0.1:1",
        "ALL_PROXY": "http://127.0.0.1:1",
    }
    command = [str(ROOT / "tianji")] if wrapper else [sys.executable, "-m", "tianji_lab"]
    result = subprocess.run(
        command + list(argv),
        input=stdin,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        timeout=30,
    )
    assert TOKEN not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr + result.stdout
    return result, json.loads(result.stdout)


def test_real_cli_catalog_create_idempotency_update_stale_and_inputs(live_api, tmp_path):
    result, catalog = subprocess_cli(live_api, tmp_path, "operations", wrapper=True)
    assert result.returncode == 0
    assert {item["name"] for item in catalog["data"]} == set(OPERATIONS)
    _, schema = subprocess_cli(live_api, tmp_path, "schema", "scenario_create")
    assert schema["data"]["input_schema"]["properties"]["spec"]
    _, listing = subprocess_cli(live_api, tmp_path, "call", "scenario_list")
    assert listing["data"]
    create = json.dumps({"spec": {"name": "CLI scenario / 虚构"}})
    result, first = subprocess_cli(
        live_api, tmp_path, "call", "scenario_create", "--stdin", stdin=create
    )
    assert result.returncode == 0
    request_id = json.loads(result.stderr)["request_id"]
    uuid.UUID(request_id)
    result, replay = subprocess_cli(
        live_api, tmp_path, "call", "scenario_create", "--json", create, "--request-id", request_id
    )
    assert result.returncode == 0 and replay == first
    created = first["data"]
    update = {"id": created["id"], "revision": created["revision"], "spec": {"name": "Updated"}}
    path = tmp_path / "update.json"
    path.write_text(json.dumps(update))
    result, updated = subprocess_cli(
        live_api, tmp_path, "call", "scenario_update", "--file", path.name, wrapper=True
    )
    assert result.returncode == 0 and updated["data"]["revision"] == created["revision"] + 1
    result, stale = subprocess_cli(
        live_api, tmp_path, "call", "scenario_update", "--file", path.name
    )
    assert result.returncode != 0 and stale["ok"] is False
    assert stale["error"]["code"] == "stale_revision"
    _, final_listing = subprocess_cli(live_api, tmp_path, "call", "scenario_list")
    matching = [item for item in final_listing["data"]["items"] if item["id"] == created["id"]]
    assert matching == [updated["data"]]
    result, collision = subprocess_cli(
        live_api,
        tmp_path,
        "call",
        "scenario_create",
        "--request-id",
        request_id,
        "--json",
        '{"spec":{"name":"different"}}',
    )
    assert result.returncode != 0 and collision["error"]["code"] == "idempotency_conflict"


def test_real_cli_health_errors_and_secret_sanitization(live_api, tmp_path):
    result, body = subprocess_cli(live_api, tmp_path, "health", "--token-file", "missing", token="")
    assert result.returncode == 0 and body["data"]["ok"] is True
    for argv in [
        ["call", "missing"],
        ["call", "scenario_list", "--json", '{"x":1,"x":2}'],
        ["call", "scenario_list", "--stdin"],
        ["call", "scenario_list", "--file", "missing"],
        [
            "call",
            "scenario_create",
            "--json",
            json.dumps({"spec": {"name": TOKEN, "horizon": TOKEN}}),
        ],
        ["operations", "--token", TOKEN],
        ["operations", "--url", f"http://{TOKEN}@evil.invalid"],
    ]:
        result, body = subprocess_cli(live_api, tmp_path, *argv, stdin="[]")
        assert result.returncode != 0 and body["ok"] is False
    result, body = subprocess_cli(live_api, tmp_path, "operations", token="wrong-token")
    assert result.returncode != 0 and body["error"]["code"] == "unauthorized"
    token_path = tmp_path / "auth-token"
    token_path.write_text(TOKEN)
    result, body = subprocess_cli(
        live_api,
        tmp_path,
        "operations",
        "--token-file",
        token_path.name,
        token="wrong-token",
        wrapper=True,
    )
    assert result.returncode == 0 and body["ok"] is True
