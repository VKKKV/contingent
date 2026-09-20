"""Loopback-only registry client. Authentication is never accepted on the command line.

Token precedence: --token-file, TIANJI_TOKEN, repository .local-data/token.
Relative input/token paths are relative to the caller's working directory.
"""

import argparse
import ipaddress
import json
import math
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

MAX_JSON_BYTES = 1_048_576
DEFAULT_TOKEN_FILE = Path(__file__).resolve().parents[2] / ".local-data" / "token"
DEFAULT_URL = "http://127.0.0.1:8787"


class CLIError(Exception):
    def __init__(self, code, message, **details):
        self.envelope = {"ok": False, "error": {"code": code, "message": message, **details}}
        super().__init__(message)


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_abbrev=False, **kwargs)

    def error(self, message):
        # argparse's message can contain an accidentally supplied credential or JSON.
        raise CLIError("usage", "Invalid command or options; use --help for syntax")


def timeout_value(value):
    try:
        value = float(value)
        if not math.isfinite(value) or not 1 <= value <= 300:
            raise ValueError
        return value
    except ValueError:
        raise argparse.ArgumentTypeError("Timeout must be 1..300 seconds") from None


def parser():
    common = Parser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument("--url", help="Loopback HTTP origin (TIANJI_URL or http://127.0.0.1:8787)")
    common.add_argument(
        "--token-file",
        type=Path,
        help="Token file; overrides TIANJI_TOKEN, then default repository .local-data/token",
    )
    common.add_argument(
        "--timeout",
        type=timeout_value,
        help="Timeout in seconds, 1..300 (vision_generate 190, actor_propose 40, others 15)",
    )
    root = Parser(
        prog="tianji",
        parents=[common],
        description="Control every operation in the live TianJi registry over loopback HTTP.",
        epilog="JSON envelopes on stdout; mutation request_id on stderr. No automatic retries. "
        "Relative paths use your current directory. Authentication: --token-file PATH, "
        "then TIANJI_TOKEN, then repository .local-data/token. Never pass a token as an argument.",
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("health", parents=[common], help="Unauthenticated service health")
    commands.add_parser("operations", parents=[common], help="Full live catalog including schemas")
    schema = commands.add_parser(
        "schema", parents=[common], help="One operation's schema and metadata"
    )
    schema.add_argument("name")
    call = commands.add_parser("call", parents=[common], help="Call any live registry operation")
    call.add_argument("name")
    source = call.add_mutually_exclusive_group()
    source.add_argument("--json", help="Strict JSON argument object (default: {})")
    source.add_argument(
        "--file", type=Path, help="Read argument object from a UTF-8 file (up to 1 MiB)"
    )
    source.add_argument("--stdin", action="store_true", help="Read argument object from stdin")
    call.add_argument(
        "--request-id",
        help="Idempotency key, 1..128 characters; mutations default to a new UUID. "
        "Reuse the printed ID with identical arguments to recover an ambiguous result.",
    )
    serve = commands.add_parser("serve", help="Serve the local scenario analysis service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--data-dir", default=".local-data")
    mcp = commands.add_parser("mcp", help="MCP stdio adapter (uses TIANJI_TOKEN only)")
    mcp.add_argument("--url", default=argparse.SUPPRESS, help="Loopback HTTP origin or TIANJI_URL")
    return root


def validate_url(value):
    try:
        if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
            raise ValueError
        url = urlsplit(value)
        host = url.hostname
        loopback = host == "localhost" or ipaddress.ip_address(host or "").is_loopback
        if (
            url.scheme != "http"
            or not loopback
            or url.username is not None
            or url.password is not None
            or url.path not in ("", "/")
            or "?" in value
            or "#" in value
            or "\\" in value
            or (url.port is not None and not 1 <= url.port <= 65535)
            or url.netloc.endswith(":")
        ):
            raise ValueError
        return value.rstrip("/")
    except ValueError:
        raise CLIError(
            "invalid_url", "URL must be a loopback HTTP origin with an optional port"
        ) from None


def read_token(path):
    try:
        if path is None and "TIANJI_TOKEN" in os.environ:
            token = os.environ["TIANJI_TOKEN"]
        else:
            with (path or DEFAULT_TOKEN_FILE).open("rb") as stream:
                raw = stream.read(8193)
            if len(raw) > 8192:
                raise ValueError
            token = raw.decode("ascii").strip()
        if not token or len(token) > 8192 or any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError
        return token
    except (OSError, ValueError):
        raise CLIError(
            "credentials", "Cannot read a valid token; set TIANJI_TOKEN or use --token-file PATH"
        ) from None


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError
        return result

    def constant(value):
        raise ValueError

    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def arguments(args):
    try:
        if args.file is not None:
            with args.file.open("rb") as stream:
                raw = stream.read(MAX_JSON_BYTES + 1)
        elif args.stdin:
            stream = getattr(sys.stdin, "buffer", sys.stdin)
            raw = stream.read(MAX_JSON_BYTES + 1)
        else:
            raw = args.json if args.json is not None else "{}"
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if len(raw) > MAX_JSON_BYTES:
            raise CLIError("body_too_large", "Argument JSON exceeds 1 MiB")
        value = strict_json(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        # Reject unpaired surrogate escapes before httpx's encoder sees them.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except OSError:
        raise CLIError("input", "Cannot read argument input") from None
    except (ValueError, RecursionError):
        raise CLIError(
            "validation",
            "Arguments must be a UTF-8 JSON object without duplicate keys or nonfinite numbers",
        ) from None


def redact(value, token):
    if isinstance(value, str):
        return value.replace(token, "[REDACTED]") if token else value
    if isinstance(value, list):
        return [redact(item, token) for item in value]
    if isinstance(value, dict):
        return {redact(key, token): redact(item, token) for key, item in value.items()}
    return value


def emit(value, token=None, *, stream=None):
    print(
        json.dumps(redact(value, token), ensure_ascii=True, allow_nan=False),
        file=stream or sys.stdout,
        flush=True,
    )


def request(client, method, path, *, mutating=False, request_id=None, **kwargs):
    details = {"ambiguous": True, "request_id": request_id} if mutating else {}
    ambiguity = (
        " Mutation outcome is ambiguous; no automatic retry. Inspect state or retry with the same "
        "request_id and identical arguments."
        if mutating
        else ""
    )
    try:
        response = client.request(method, path, **kwargs)
        if response.is_redirect:
            raise CLIError("redirect_denied", "API redirect refused." + ambiguity, **details)
        try:
            body = strict_json(response.content.decode("utf-8"))
        except (ValueError, RecursionError):
            raise CLIError(
                "invalid_response", "API returned invalid JSON." + ambiguity, **details
            ) from None
        if response.is_error:
            if (
                isinstance(body, dict)
                and body.get("ok") is False
                and isinstance(body.get("error"), dict)
            ):
                if mutating and response.status_code >= 500:
                    body["error"].update(details)
                    body["error"]["message"] = "API failed." + ambiguity
                return body
            raise CLIError("http_error", "API returned an HTTP error." + ambiguity, **details)
        return body
    except (httpx.HTTPError, KeyboardInterrupt):
        raise CLIError(
            "network", "Local API request failed or was interrupted." + ambiguity, **details
        ) from None


def catalog(client, timeout):
    body = request(client, "GET", "/api/capabilities", timeout=timeout)
    if isinstance(body, dict) and body.get("ok") is False and isinstance(body.get("error"), dict):
        return None, body
    if (
        not isinstance(body, list)
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item["name"])
            or not isinstance(item.get("mutating"), bool)
            or not isinstance(item.get("input_schema"), dict)
            for item in body
        )
        or len({item["name"] for item in body}) != len(body)
    ):
        raise CLIError("invalid_response", "API returned an invalid operation catalog")
    return body, None


def run_client(args, url, token, *, transport=None):
    timeout = getattr(args, "timeout", 15)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(
        base_url=url,
        headers=headers,
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
        transport=transport,
    ) as client:
        if args.command == "health":
            body = request(client, "GET", "/health")
            if isinstance(body, dict) and body.get("ok") is True:
                return {"ok": True, "data": body}
            if (
                isinstance(body, dict)
                and body.get("ok") is False
                and isinstance(body.get("error"), dict)
            ):
                return body
            raise CLIError("invalid_response", "API returned invalid health data")
        items, error = catalog(client, timeout)
        if error:
            return error
        assert items is not None
        if args.command == "operations":
            return {"ok": True, "data": items}
        item = next((item for item in items if item["name"] == args.name), None)
        if item is None:
            raise CLIError("not_found", "Unknown operation in the live registry")
        if args.command == "schema":
            return {"ok": True, "data": item}
        payload = {"arguments": args.arguments}
        request_id = args.request_id
        if item["mutating"] and request_id is None:
            request_id = str(uuid.uuid4())
        if request_id is not None:
            payload["request_id"] = request_id
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(content) > MAX_JSON_BYTES:
            raise CLIError("body_too_large", "Complete request envelope exceeds 1 MiB")
        if request_id is not None:
            emit({"request_id": request_id}, token, stream=sys.stderr)
        body = request(
            client,
            "POST",
            f"/api/operations/{item['name']}",
            content=content,
            headers={"Content-Type": "application/json"},
            mutating=item["mutating"],
            request_id=request_id,
            timeout=getattr(
                args, "timeout", {"vision_generate": 190, "actor_propose": 40}.get(args.name, 15)
            ),
        )
        if not isinstance(body, dict) or (
            not (body.get("ok") is True and "data" in body)
            and not (body.get("ok") is False and isinstance(body.get("error"), dict))
        ):
            if item["mutating"]:
                raise CLIError(
                    "invalid_response",
                    "Invalid result; mutation outcome is ambiguous. No automatic "
                    "retry; inspect state or retry the same request_id and arguments.",
                    ambiguous=True,
                    request_id=request_id,
                )
            raise CLIError("invalid_response", "API returned an invalid operation envelope")
        return body


def is_mcp_command(argv):
    # Locate the subcommand without mistaking a global option's value for it.
    # This also routes argparse failures before the MCP adapter starts to stderr.
    index = 0
    while index < len(argv):
        option = argv[index]
        if option in ("--url", "--token-file", "--timeout"):
            index += 2
        elif any(option.startswith(name + "=") for name in ("--url", "--token-file", "--timeout")):
            index += 1
        else:
            return option == "mcp"
    return False


def main(argv=None, *, transport=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    mcp_mode = is_mcp_command(argv)
    token = os.environ.get("TIANJI_TOKEN") if mcp_mode else None
    try:
        args = parser().parse_args(argv)
        if args.command in ("serve", "mcp") and (
            hasattr(args, "token_file") or hasattr(args, "timeout")
        ):
            raise CLIError("usage", "--token-file and --timeout are client-only options")
        if args.command == "serve" and hasattr(args, "url"):
            raise CLIError("usage", "serve uses --host and --port, not --url")
        if args.command == "serve":
            import uvicorn

            from .api import create_app, local_host

            if not local_host(args.host) or not 1 <= args.port <= 65535:
                raise CLIError("usage", "Serve requires a loopback host and port 1..65535")
            uvicorn.run(create_app(args.data_dir), host=args.host, port=args.port, access_log=False)
            return 0
        url = validate_url(getattr(args, "url", os.environ.get("TIANJI_URL", DEFAULT_URL)))
        if args.command == "mcp":
            if not token:
                raise CLIError("credentials", "Set TIANJI_TOKEN for the MCP adapter")
            import asyncio

            from .mcp_server import run

            asyncio.run(run(url))
            return 0
        if args.command == "call":
            args.arguments = arguments(args)
            if args.request_id is not None and not 1 <= len(args.request_id) <= 128:
                raise CLIError("validation", "request_id must contain 1..128 characters")
        if args.command != "health":
            token = read_token(getattr(args, "token_file", None))
        result = run_client(args, url, token, transport=transport)
    except CLIError as exc:
        result = exc.envelope
    except KeyboardInterrupt:
        result = {"ok": False, "error": {"code": "interrupted", "message": "Command interrupted"}}
    except Exception:
        # Never expose exception text: it may contain credentials, URLs or argument data.
        result = {"ok": False, "error": {"code": "client_error", "message": "Local client failed"}}
    try:
        # MCP stdout belongs exclusively to the SDK JSON-RPC transport.
        emit(result, token, stream=sys.stderr if mcp_mode else sys.stdout)
    except BrokenPipeError:
        return 1
    return 0 if result.get("ok") is True else 1
