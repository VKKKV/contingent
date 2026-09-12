"""Portable CLI for the loopback API and real MCP stdio adapter."""

import argparse
import asyncio

import uvicorn

from .api import create_app, local_host
from .mcp_server import run


def main():
    parser = argparse.ArgumentParser(prog="tianji-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Serve the isolated fictional laboratory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--data-dir", default=".local-data")
    mcp = commands.add_parser("mcp", help="Official MCP stdio adapter; token via TIANJI_TOKEN")
    mcp.add_argument("--url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    if args.command == "serve":
        if not local_host(args.host):
            parser.error("Only loopback binding is supported")
        uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port, access_log=False)
    else:
        asyncio.run(run(args.url))


if __name__ == "__main__":
    main()
