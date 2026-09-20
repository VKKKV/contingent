"""Exercise the real Agent/OpenAI stack through a mock HTTP transport."""

import asyncio
import gzip
import json
import logging
import zlib

import httpx
import httpx2
import pytest
from genai_prices import UpdatePrices
from opentelemetry import context as otel_context
from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_ai import Agent
from pydantic_ai.usage import RequestUsage

from tianji_lab import analysis_model as am
from tianji_lab import local_actor


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    count: int
    title: str


class GraphOutput(BaseModel):
    nodes: list[str]
    references: list[str]

    @model_validator(mode="after")
    def references_exist(self):
        if not set(self.references) <= set(self.nodes):
            raise ValueError("secret invalid reference")
        return self


def completion(content='{"count":1,"title":"ok"}', **message):
    return {
        "id": "test-completion",
        "object": "chat.completion",
        "created": 1,
        "model": "local-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    **message,
                },
            }
        ],
        "usage": {"prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26},
    }


class Stream(httpx.AsyncByteStream):
    def __init__(self, body, *, block=False):
        self.body = body
        self.block = block
        self.closed = False
        self.started = asyncio.Event()
        self.chunks = 0

    async def __aiter__(self):
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        for start in range(0, len(self.body), 997):
            self.chunks += 1
            yield self.body[start : start + 997]

    async def aclose(self):
        self.closed = True


@pytest.fixture
def wire(monkeypatch):
    state = {"requests": [], "streams": [], "transports": [], "client_options": []}
    state["body"] = json.dumps(completion()).encode()
    state["status"] = 200
    state["headers"] = {}
    original_client = httpx.AsyncClient

    class Transport(httpx.MockTransport):
        def __init__(self, **kwargs):
            assert kwargs == {"retries": 0, "trust_env": False}
            super().__init__(self.handler)
            self.closed = False
            state["transports"].append(self)

        async def handler(self, request):
            state["requests"].append(request)
            if state.get("exception"):
                raise state["exception"]
            stream = Stream(state["body"], block=state.get("block", False))
            state["streams"].append(stream)
            return httpx.Response(state["status"], headers=state["headers"], stream=stream)

        async def aclose(self):
            self.closed = True
            await super().aclose()

    class Client(original_client):
        def __init__(self, **kwargs):
            state["client_options"].append(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(am.httpx, "AsyncHTTPTransport", Transport)
    monkeypatch.setattr(am.httpx, "AsyncClient", Client)
    return state


def run(output_type=Output, **kwargs):
    return asyncio.run(
        am.LocalAnalysisModel("http://127.0.0.1:18789", "local-test").complete(
            "planner", "Return a typed answer.", {"goal": "hello"}, output_type, **kwargs
        )
    )


def assert_failure(wire, code="analysis_invalid_output", output_type=Output):
    with pytest.raises(am.AnalysisModelError) as caught:
        run(output_type)
    assert caught.value.code == code
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert len(wire["requests"]) == 1
    assert all(t.closed for t in wire["transports"])
    assert all(s.closed for s in wire["streams"])


def test_real_agent_native_output_usage_and_security(wire, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://remote.invalid/v1")
    monkeypatch.setenv("OPENAI_ORG_ID", "secret-org")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "secret-project")
    monkeypatch.setenv(
        "OPENAI_CUSTOM_HEADERS", "Authorization: secret-key\nX-Secret: secret-header"
    )
    monkeypatch.setenv("HTTP_PROXY", "http://remote.invalid:80")
    monkeypatch.setenv("ALL_PROXY", "http://remote.invalid:80")
    monkeypatch.setattr(Agent, "_instrument_default", True)

    def no_prices(*args, **kwargs):
        raise AssertionError("must not load price snapshots")

    monkeypatch.setattr(RequestUsage, "extract", no_prices)
    # Coordinator already owns the process-wide slot; adapter must not reacquire.
    assert local_actor._CALL_SLOT.acquire(blocking=False)
    try:
        result = run()
    finally:
        local_actor._CALL_SLOT.release()
    assert isinstance(result.output, Output)
    assert result.output.count == 1
    assert (result.input_tokens, result.output_tokens) == (17, 9)
    assert result.model == "local-test"
    assert result.duration_ms >= 0
    assert not hasattr(result, "messages")
    request = wire["requests"][0]
    assert str(request.url) == "http://127.0.0.1:18789/v1/chat/completions"
    assert "secret" not in str(request.headers)
    assert "authorization" not in request.headers
    payload = json.loads(request.content)
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 1800
    assert payload["stream"] is False
    assert payload["cache_prompt"] is False
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert wire["client_options"][0]["trust_env"] is False
    assert wire["client_options"][0]["follow_redirects"] is False
    assert all(t.closed for t in wire["transports"])


def test_fresh_context_and_optional_usage(wire):
    body = completion()
    del body["usage"]
    wire["body"] = json.dumps(body).encode()

    async def calls():
        adapter = am.LocalAnalysisModel("http://127.0.0.1:18789", "local-test")
        first = await adapter.complete("first", "first instructions", {"private": "first"}, Output)
        second = await adapter.complete(
            "second", "second instructions", {"private": "second"}, Output
        )
        return first, second

    first, second = asyncio.run(calls())
    assert first.input_tokens is None and second.output_tokens is None
    assert "first" not in wire["requests"][1].content.decode()
    assert len(json.loads(wire["requests"][1].content)["messages"]) == 2


@pytest.mark.parametrize(
    "content",
    [
        "not JSON secret",
        '```json\n{"count":1,"title":"ok"}\n```',
        '{"count":1,"count":2,"title":"ok"}',
        '{"count":"1","title":"ok"}',
        '{"count":true,"title":"ok"}',
        '{"count":1,"title":"ok","extra":"secret"}',
        '{"count":NaN,"title":"ok"}',
        '{"count":1,"title":"ok"} trailing',
        '[{"count":1,"title":"ok"}]',
        '<think>secret</think>{"count":1,"title":"ok"}',
    ],
)
def test_invalid_json_strict_schema_no_retry(wire, content):
    wire["body"] = json.dumps(completion(content)).encode()
    assert_failure(wire)


@pytest.mark.parametrize(
    "field,value",
    [
        (
            "tool_calls",
            [
                {
                    "id": "x",
                    "type": "function",
                    "function": {
                        "name": "secret",
                        "arguments": "{}",
                    },
                }
            ],
        ),
        ("function_call", {"name": "secret", "arguments": "{}"}),
        ("refusal", "secret"),
        ("reasoning", "secret"),
        ("reasoning_content", "secret"),
        ("content", None),
        ("role", "user"),
    ],
)
def test_reject_unsafe_messages(wire, field, value):
    payload = completion()
    payload["choices"][0]["message"][field] = value
    wire["body"] = json.dumps(payload).encode()
    assert_failure(wire)


@pytest.mark.parametrize("finish", [None, "length", "tool_calls", "content_filter"])
def test_reject_non_stop(wire, finish):
    payload = completion()
    payload["choices"][0]["finish_reason"] = finish
    wire["body"] = json.dumps(payload).encode()
    assert_failure(wire)


@pytest.mark.parametrize("count", [0, 2])
def test_reject_choice_count(wire, count):
    payload = completion()
    payload["choices"] *= count
    wire["body"] = json.dumps(payload).encode()
    assert_failure(wire)


def test_duplicate_envelope_keys(wire):
    wire["body"] = wire["body"].replace(b'"choices":', b'"choices":[],"choices":')
    assert_failure(wire)


def test_domain_references(wire):
    wire["body"] = json.dumps(completion('{"nodes":["a"],"references":["missing"]}')).encode()
    assert_failure(wire, output_type=GraphOutput)


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
def test_decoded_body_limit(wire, encoding):
    body = json.dumps(completion(json.dumps({"count": 1, "title": "s" * 70000}))).encode()
    wire["body"] = {"identity": lambda x: x, "gzip": gzip.compress, "deflate": zlib.compress}[
        encoding
    ](body)
    wire["headers"] = {"Content-Encoding": encoding}
    assert_failure(wire)


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_valid_compressed_response(wire, encoding):
    wire["body"] = (gzip.compress if encoding == "gzip" else zlib.compress)(wire["body"])
    wire["headers"] = {"Content-Encoding": encoding}
    assert run().output.count == 1


@pytest.mark.parametrize("status", [302, 429, 500, 503])
def test_http_error_no_redirect_no_retry_no_body_read(wire, status):
    wire["status"] = status
    wire["headers"] = {"Location": "https://remote.invalid/secret", "Retry-After": "0"}
    wire["body"] = b"secret provider diagnostics"
    assert_failure(wire, "analysis_unavailable")
    assert wire["streams"][0].chunks == 0


def test_network_failure_no_retry(wire):
    wire["exception"] = httpx.ConnectError("secret transport details")
    assert_failure(wire, "analysis_unavailable")


def test_whole_call_timeout_closes_client(wire, monkeypatch):
    wire["block"] = True
    monkeypatch.setattr(am, "TIMEOUT_SECONDS", 0.1)
    assert_failure(wire, "analysis_timeout")


def test_cancellation_closes_immediately(wire):
    wire["block"] = True

    async def cancel():
        task = asyncio.create_task(
            am.LocalAnalysisModel("http://127.0.0.1:18789", "local-test").complete(
                "planner", "answer", {}, Output
            )
        )
        async with asyncio.timeout(2):
            while not wire["streams"]:
                await asyncio.sleep(0)
            await wire["streams"][0].started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert wire["streams"][0].closed
        assert wire["transports"][0].closed

    asyncio.run(cancel())
    assert len(wire["requests"]) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:18789",
        "http://localhost:18789",
        "http://127.0.0.1:18789/",
        "http://127.0.0.1:18789/v1",
        "http://example.com",
        "http://10.0.0.1",
        "http://user:secret@127.0.0.1",
        "http://127.0.0.1?secret",
        "http://127.0.0.1:0",
    ],
)
def test_invalid_origins_fail_before_transport(wire, monkeypatch, url):
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_URL", url)
    monkeypatch.setenv("TIANJI_LOCAL_MODEL_NAME", "local-test")
    with pytest.raises(am.AnalysisModelError, match="configuration is invalid"):
        asyncio.run(am.LocalAnalysisModel.from_env().complete("planner", "answer", {}, Output))
    assert not wire["requests"]
    assert not wire["transports"]


def test_disabled(wire, monkeypatch):
    monkeypatch.delenv("TIANJI_LOCAL_MODEL_URL", raising=False)
    monkeypatch.delenv("TIANJI_LOCAL_MODEL_NAME", raising=False)
    with pytest.raises(am.AnalysisModelError) as caught:
        asyncio.run(am.LocalAnalysisModel.from_env().complete("planner", "answer", {}, Output))
    assert caught.value.code == "analysis_disabled"
    assert not wire["requests"]


@pytest.mark.parametrize("max_tokens", [0, -1, True, 1.5, 4097])
def test_token_bound(wire, max_tokens):
    with pytest.raises(am.AnalysisModelError) as caught:
        run(max_tokens=max_tokens)
    assert caught.value.code == "analysis_invalid_request"
    assert not wire["requests"]


def test_prompt_utf8_bound_before_network(wire):
    with pytest.raises(am.AnalysisModelError) as caught:
        asyncio.run(
            am.LocalAnalysisModel("http://127.0.0.1", "local-test").complete(
                "planner", "answer", {"secret": "界" * 9000}, Output
            )
        )
    assert caught.value.code == "analysis_prompt_too_large"
    assert not wire["requests"]


def test_wire_prompt_limit_includes_schema(wire, monkeypatch):
    monkeypatch.setattr(am, "MAX_PROMPT_BYTES", 150)
    with pytest.raises(am.AnalysisModelError) as caught:
        run()
    assert caught.value.code == "analysis_prompt_too_large"
    assert not wire["requests"]
    assert all(t.closed for t in wire["transports"])


def test_no_sdk_logs_even_debug(wire, caplog):
    caplog.set_level(logging.DEBUG)
    run()
    assert not [
        r
        for r in caplog.records
        if r.name.startswith(("openai", "httpx", "httpcore", "pydantic_ai", "pydantic_graph"))
    ]


def test_no_pricing_network_or_instrumentation(wire, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected pricing update or independent network client")

    monkeypatch.setattr(UpdatePrices, "start", forbidden)
    monkeypatch.setattr(UpdatePrices, "fetch", forbidden)
    monkeypatch.setattr(httpx2.AsyncClient, "send", forbidden)
    monkeypatch.setattr(httpx2.Client, "send", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    original = am._LocalChatModel.request

    async def request(self, *args, **kwargs):
        assert otel_context.get_value(otel_context._SUPPRESS_INSTRUMENTATION_KEY) is True
        assert otel_context.get_value(otel_context._SUPPRESS_HTTP_INSTRUMENTATION_KEY) is True
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(am._LocalChatModel, "request", request)
    assert run().output.count == 1
    assert len(wire["requests"]) == 1
    assert otel_context.get_value(otel_context._SUPPRESS_INSTRUMENTATION_KEY) is not True


def test_sdk_timeout_is_sanitized(wire):
    wire["exception"] = httpx.ReadTimeout("secret timed out")
    assert_failure(wire, "analysis_timeout")


@pytest.mark.parametrize(
    "encoding,body",
    [
        ("br", b"unsupported"),
        ("gzip", gzip.compress(b"{}")[:-2]),
        ("gzip", gzip.compress(b"{}") + gzip.compress(b"{}")),
        ("deflate", b"broken"),
        ("identity", b"\xff"),
        ("identity", b'{"choices": NaN}'),
    ],
)
def test_malformed_encoding_rejected(wire, encoding, body):
    wire["body"] = body
    wire["headers"] = {"Content-Encoding": encoding}
    assert_failure(wire)


def test_exact_response_limit_allowed(wire):
    wire["body"] += b" " * (am.MAX_RESPONSE_BYTES - len(wire["body"]))
    assert run().output.count == 1


def test_transport_rejects_second_send_and_different_origin(wire):
    async def check():
        transport = am._BoundedTransport("http://127.0.0.1:18789", Output)
        try:
            with pytest.raises(am.AnalysisModelError):
                await transport.handle_async_request(
                    httpx.Request(
                        "POST", "http://remote.invalid/v1/chat/completions", content=b"{}"
                    )
                )
            request = httpx.Request("POST", transport.endpoint, content=b"{}")
            await transport.handle_async_request(request)
            with pytest.raises(am.AnalysisModelError):
                await transport.handle_async_request(request)
        finally:
            await transport.aclose()

    asyncio.run(check())
    assert len(wire["requests"]) == 1


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": True, "completion_tokens": 1},
        {"prompt_tokens": -1, "completion_tokens": 1},
        {"prompt_tokens": "17", "completion_tokens": 1},
    ],
)
def test_usage_is_actual_valid_integer(wire, usage):
    payload = completion()
    payload["usage"] = usage
    wire["body"] = json.dumps(payload).encode()
    assert_failure(wire)
