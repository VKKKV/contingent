"""Authenticated loopback HTTP adapter and optional production web assets."""

import hmac
import ipaddress
import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .service import Input, OperationError, Service
from .store import MAX_JSON_BYTES


class RequestEnvelope(Input):
    arguments: dict
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


def local_host(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def token_for(data_dir, supplied=None):
    token = supplied or os.environ.get("TIANJI_TOKEN")
    if token:
        return token
    path = Path(data_dir) / "token"
    if path.exists():
        path.chmod(0o600)
        token = path.read_text().strip()
        if not token:
            raise ValueError("Empty local token file")
    else:
        token = secrets.token_urlsafe(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(token)
    print(f"Local authentication token file: {path}", file=sys.stderr)
    return token


def failure(code, message, status):
    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": message}}, status_code=status
    )


class SecurityMiddleware:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        path, method = scope["path"], scope["method"]
        if path.startswith("/api"):
            supplied = headers.get("authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {self.token}".encode()):
                return await failure("unauthorized", "Bearer token required", 401)(
                    scope, receive, send
                )
        if method not in ("GET", "HEAD", "OPTIONS"):
            origin = headers.get("origin")
            host = headers.get("host", "")
            expected = f"{scope.get('scheme', 'http')}://{host}"
            if headers.get("sec-fetch-site") == "cross-site" or (origin and origin != expected):
                return await failure("origin_denied", "Cross-origin writes denied", 403)(
                    scope, receive, send
                )
            try:
                if int(headers.get("content-length", "0")) > MAX_JSON_BYTES:
                    return await failure("body_too_large", "Request body exceeds 1 MiB", 422)(
                        scope, receive, send
                    )
            except ValueError:
                return await failure("validation", "Invalid content length", 422)(
                    scope, receive, send
                )
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > MAX_JSON_BYTES:
                    return await failure("body_too_large", "Request body exceeds 1 MiB", 422)(
                        scope, receive, send
                    )
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            consumed = False

            async def bounded_receive():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            return await self.app(scope, bounded_receive, send)
        return await self.app(scope, receive, send)


def create_app(data_dir=".local-data", token=None, *, start_worker=True, web_dir=None):
    service = Service(data_dir, start_worker=False)
    try:
        token = token_for(service.store.data_dir, token)
    except Exception:
        service.close()
        raise

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            service.start()
        yield
        await run_in_threadpool(service.close)

    app = FastAPI(
        title="TianJi laboratory",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.service = service
    app.add_middleware(SecurityMiddleware, token=token)

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/capabilities")
    def capabilities():
        return service.capabilities()

    @app.post("/api/operations/{name}")
    async def operation(name: str, request: Request):
        try:
            envelope = RequestEnvelope.model_validate(await request.json())
            result = await run_in_threadpool(
                service.execute, name, envelope.arguments, envelope.request_id
            )
            return {"ok": True, "data": result}
        except OperationError as exc:
            return failure(exc.code, exc.message, exc.status)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return failure("validation", str(exc)[:1000], 422)

    @app.exception_handler(404)
    async def missing(request, exc):
        return failure("not_found", "Route not found", 404)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = "method_not_allowed" if exc.status_code == 405 else "http_error"
        return failure(code, str(exc.detail), exc.status_code)

    assets = Path(web_dir) if web_dir else Path(__file__).resolve().parents[2] / "web" / "dist"
    if assets.is_dir():
        app.mount("/", StaticFiles(directory=assets, html=True), name="web")
    return app


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not local_host(parsed.hostname or ""):
        raise ValueError("MCP API URL must be loopback HTTP")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("MCP URL must contain only loopback host and port")
    return url.rstrip("/")
