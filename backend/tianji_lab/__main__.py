"""Module entry point for the registry CLI, HTTP service and MCP adapter."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
