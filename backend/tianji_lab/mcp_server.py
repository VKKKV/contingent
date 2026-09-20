"""Official MCP stdio transport; discovers and proxies the authenticated API."""

import json
import os
import uuid

import httpx
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .api import validate_url


async def run(url):
    token = os.environ.get("TIANJI_TOKEN")
    if not token:
        raise ValueError("Set TIANJI_TOKEN for the MCP adapter")
    url = validate_url(url)
    async with httpx.AsyncClient(
        base_url=url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = await client.get("/api/capabilities")
        response.raise_for_status()
        catalog = {item["name"]: item for item in response.json()}
        server = Server("tianji-lab", version="0.3.0")

        @server.list_tools()
        async def list_tools():
            return [
                types.Tool(
                    name=item["name"],
                    description=item["description"],
                    inputSchema=item["input_schema"],
                )
                for item in catalog.values()
            ]

        @server.call_tool()
        async def call_tool(name, arguments):
            if name not in catalog:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text="Unknown tool")], isError=True
                )
            payload = {"arguments": arguments or {}}
            if catalog[name]["mutating"]:
                payload["request_id"] = str(uuid.uuid4())
            try:
                result = await client.post(
                    f"/api/operations/{name}",
                    json=payload,
                    timeout={"vision_generate": 190, "actor_propose": 40}.get(name, 15),
                )
                body = result.json()
                error = result.is_error or not body.get("ok", False)
                return types.CallToolResult(
                    content=[
                        types.TextContent(type="text", text=json.dumps(body, ensure_ascii=False))
                    ],
                    isError=error,
                )
            except (httpx.HTTPError, ValueError):
                return types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text", text="Local API unavailable or returned invalid JSON"
                        )
                    ],
                    isError=True,
                )

        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
