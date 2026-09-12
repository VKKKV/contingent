"""Real CLI HTTP process + official SDK stdio initialization/tool calls."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_mcp_stdio_and_cli(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "TIANJI_TOKEN": "integration-test-only"}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tianji_lab",
            "serve",
            "--port",
            str(port),
            "--data-dir",
            str(tmp_path),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=url, trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 10
            while True:
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "CLI did not become ready"
                time.sleep(0.05)

        async def interact():
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "tianji_lab", "mcp", "--url", url], env=env
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "tianji-lab"
                    tools = await session.list_tools()
                    assert "run_backward" in {tool.name for tool in tools.tools}
                    result = await session.call_tool("scenario_list", {})
                    assert not result.isError
                    scenarios = json.loads(result.content[0].text)["data"]["items"]
                    assert len(scenarios) == 1
                    created = await session.call_tool(
                        "scenario_create", {"spec": {"name": "MCP-created"}}
                    )
                    assert not created.isError
                    attached = await session.call_tool("workspace_attach", {})
                    workspace = json.loads(attached.content[0].text)["data"]
                    changed = await session.call_tool(
                        "workspace_update", {"id": workspace["id"], "revision": 1, "panel": "goal"}
                    )
                    assert not changed.isError
                    readback = await session.call_tool("workspace_get", {"id": workspace["id"]})
                    assert json.loads(readback.content[0].text)["data"]["panel"] == "goal"
                    stale = await session.call_tool(
                        "workspace_update",
                        {"id": workspace["id"], "revision": 1, "panel": "timeline"},
                    )
                    assert stale.isError
                    with httpx.Client(
                        base_url=url,
                        headers={"Authorization": "Bearer integration-test-only"},
                        trust_env=False,
                    ) as http:
                        data = http.post(
                            "/api/operations/scenario_list", json={"arguments": {}}
                        ).json()["data"]
                        assert any(item["spec"]["name"] == "MCP-created" for item in data["items"])

        asyncio.run(interact())
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
