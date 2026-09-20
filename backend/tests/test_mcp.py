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
from test_vision import draft_data


def test_real_mcp_stdio_and_cli(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "TIANJI_TOKEN": "integration-test-only",
        "TIANJI_LOCAL_MODEL_URL": "",
        "TIANJI_LOCAL_MODEL_NAME": "",
    }
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
                    names = {tool.name for tool in tools.tools}
                    assert "run_backward" in names
                    assert {"vision_generate", "vision_save", "vision_get", "vision_list"} <= names
                    assert {"analysis_start", "analysis_get", "analysis_list"} <= names
                    # The exogenous-disturbance schema must be published to agents, not
                    # only accepted by the browser.
                    create_schema = json.dumps(
                        next(
                            tool for tool in tools.tools if tool.name == "scenario_create"
                        ).inputSchema
                    )
                    assert "disturbances" in create_schema and "supplier_loss" in create_schema
                    result = await session.call_tool("scenario_list", {})
                    assert not result.isError
                    scenarios = json.loads(result.content[0].text)["data"]["items"]
                    assert len(scenarios) == 1
                    created = await session.call_tool(
                        "scenario_create",
                        {
                            "spec": {
                                "name": "MCP-created",
                                "horizon": 3,
                                "disturbances": [{"tick": 2, "kind": "supplier_loss", "amount": 4}],
                            }
                        },
                    )
                    assert not created.isError
                    created_id = json.loads(created.content[0].text)["data"]["id"]
                    queued = await session.call_tool(
                        "run_forward", {"scenario_id": created_id, "actions": []}
                    )
                    job = json.loads(queued.content[0].text)["data"]
                    for _ in range(300):
                        if job["status"] not in ("queued", "running"):
                            break
                        await asyncio.sleep(0.05)
                        job = json.loads(
                            (await session.call_tool("job_get", {"id": job["id"]})).content[0].text
                        )["data"]
                    assert job["status"] == "succeeded", job
                    scheduled_branch = job["result"]["branch"]
                    assert scheduled_branch["trajectory"]["rule_version"] == "supply-chain.v2"
                    assert scheduled_branch["provenance"]["rule_version"] == "supply-chain.v2"
                    assert scheduled_branch["trajectory"]["final_state"]["lost"] == 4
                    assert (
                        scheduled_branch["trajectory"]["final_state"]["delivered"]
                        + (scheduled_branch["trajectory"]["final_state"]["shortage"])
                        == 3 * 4
                    )
                    # The same capability schemas and director operations are exposed
                    # over MCP, not a second implementation or participant auth layer.
                    with httpx.Client(
                        base_url=url,
                        headers={"Authorization": "Bearer integration-test-only"},
                        trust_env=False,
                    ) as http:
                        catalog = http.get("/api/capabilities").json()
                    assert {t.name: t.inputSchema for t in tools.tools} == {
                        item["name"]: item["input_schema"] for item in catalog
                    }

                    async def invoke(name, args):
                        response = await session.call_tool(name, args)
                        assert not response.isError, response
                        return json.loads(response.content[0].text)["data"]

                    assert await invoke("vision_list", {}) == {"items": []}
                    assert await invoke("analysis_list", {}) == {"items": []}
                    no_model = await session.call_tool(
                        "analysis_start", {"request": {"vision": "教育平等"}}
                    )
                    assert no_model.isError
                    assert (
                        json.loads(no_model.content[0].text)["error"]["code"] == "analysis_disabled"
                    )
                    disabled = await session.call_tool("vision_generate", {"vision": "教育平等"})
                    assert disabled.isError
                    assert (
                        json.loads(disabled.content[0].text)["error"]["code"] == "vision_disabled"
                    )
                    vision = await invoke("vision_save", {"draft": draft_data()})
                    assert vision["draft"] == draft_data()
                    assert await invoke("vision_get", {"id": vision["id"]}) == vision
                    assert (await invoke("vision_list", {}))["items"][0]["id"] == vision["id"]
                    invalid = await session.call_tool("vision_save", {"draft": {}})
                    assert invalid.isError

                    observed = await invoke(
                        "observation_create",
                        {
                            "branch_id": scheduled_branch["id"],
                            "tick": 0,
                            "actor_id": "supplier-1",
                            "role": "supplier",
                        },
                    )
                    assert set(observed["observation"]["projection"]) == {
                        "tick",
                        "supplier_stock",
                        "shipments",
                    }
                    assert await invoke("observation_get", {"id": observed["id"]}) == observed
                    checked = await invoke(
                        "adjudication_create",
                        {
                            "observation_id": observed["id"],
                            "adjudicator_id": "referee-1",
                            "proposal": {
                                "actor_id": "supplier-1",
                                "role": "supplier",
                                "action": "order_express",
                                "policy_id": "manual.director.v1",
                                "observation_hash": observed["observation"]["observation_hash"],
                            },
                        },
                    )
                    assert checked["record"]["status"] == "rejected"
                    assert (
                        checked["next_state"]
                        == scheduled_branch["trajectory"]["frames"][0]["state"]
                    )
                    assert await invoke("adjudication_get", {"id": checked["id"]}) == checked
                    assert (
                        await invoke("adjudication_list", {"branch_id": scheduled_branch["id"]})
                    )["items"] == [checked]
                    retailer = await invoke(
                        "observation_create",
                        {
                            "branch_id": scheduled_branch["id"],
                            "tick": 0,
                            "actor_id": "retailer-1",
                            "role": "retailer",
                        },
                    )
                    assert set(retailer["observation"]["projection"]) == {
                        "tick",
                        "inventory",
                        "cash",
                        "delivered",
                        "shortage",
                        "spent",
                        "shipments",
                    }
                    accepted = await invoke(
                        "adjudication_create",
                        {
                            "observation_id": retailer["id"],
                            "adjudicator_id": "referee-1",
                            "proposal": {
                                "actor_id": "retailer-1",
                                "role": "retailer",
                                "action": "order_express",
                                "policy_id": "manual.director.v1",
                                "observation_hash": retailer["observation"]["observation_hash"],
                            },
                        },
                    )
                    assert accepted["record"]["status"] == "accepted"
                    assert (
                        await invoke("branch_get", {"id": scheduled_branch["id"]})
                        == scheduled_branch
                    )
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
