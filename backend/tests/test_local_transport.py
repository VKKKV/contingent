"""Legacy exchange boundaries; all model responses here are offline test fixtures."""

import asyncio
import gzip
import json
import zlib
from types import SimpleNamespace

import httpx
import pytest
from test_vision import plan_data

from tianji_lab import local_actor, local_transport, vision
from tianji_lab.models import Scenario


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks, *, block=False):
        self.chunks = chunks
        self.block = block
        self.reads = 0
        self.closed = False
        self.cancelled = False
        self.entered = asyncio.Event()

    async def __aiter__(self):
        try:
            for chunk in self.chunks:
                self.reads += 1
                yield chunk
            if self.block:
                self.entered.set()
                await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        self.closed = True


@pytest.fixture(params=["actor", "vision"])
def caller(request):
    if request.param == "actor":
        module = local_actor
        error = local_actor.LocalActorError
        content = {"action": "wait"}
        model = local_actor.LocalActor("http://127.0.0.1:8080", "test")
        observation = SimpleNamespace(
            role="retailer", projection=SimpleNamespace(model_dump=lambda **_: {"tick": 0})
        )
        args = (observation, local_actor.PublicRules.from_scenario(Scenario(name="test")))
    else:
        module = vision
        error = vision.LocalVisionError
        content = plan_data()
        model = vision.LocalVision("http://127.0.0.1:8080", "test")
        args = (vision.VisionRequest(vision="test"),)
    envelope = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(content)},
            }
        ]
    }
    return SimpleNamespace(
        module=module,
        error=error,
        prefix=request.param,
        envelope=envelope,
        complete=lambda: model._complete(model.url, *args),
    )


def install(monkeypatch, caller, stream, *, status=200, headers=None):
    original = httpx.AsyncClient
    clients, requests = [], []

    def handle(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "http://127.0.0.1:8080/v1/chat/completions"
        return httpx.Response(status, stream=stream, headers=headers)

    def factory(**kwargs):
        assert kwargs == {
            "trust_env": False,
            "follow_redirects": False,
            "timeout": caller.module.TIMEOUT_SECONDS,
        }
        client = original(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(caller.module.httpx, "AsyncClient", factory)
    return clients, requests


def assert_closed(clients, requests, stream):
    assert len(clients) == len(requests) == 1
    assert clients[0].is_closed and stream.closed


def assert_error(error, caller, suffix, message, status):
    assert type(error.value) is caller.error
    assert (error.value.code, error.value.message, error.value.status) == (
        f"{caller.prefix}_{suffix}",
        message,
        status,
    )


def compressed_body(body, encoding):
    if encoding == "gzip":
        return gzip.compress(body)
    return zlib.compress(
        body, wbits=-zlib.MAX_WBITS if encoding == "raw-deflate" else zlib.MAX_WBITS
    )


@pytest.mark.parametrize("extra", [0, 1])
@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate", "raw-deflate"])
def test_decoded_chunk_boundary(monkeypatch, caller, extra, encoding):
    limit = caller.module.MAX_RESPONSE_BYTES
    body = json.dumps(caller.envelope).encode()
    body += b" " * (limit - len(body) + extra)
    if encoding != "identity":
        wire = compressed_body(body, encoding)
        chunks = [wire[:1], wire[1:2], wire[2:10], wire[10:]]
    else:
        chunks = [body[:100], body[100:limit], body[limit:]]
    stream = ChunkStream(chunks)
    clients, requests = install(
        monkeypatch,
        caller,
        stream,
        headers={"content-encoding": "deflate" if encoding == "raw-deflate" else encoding},
    )
    if extra:
        with pytest.raises(caller.error) as error:
            asyncio.run(caller.complete())
        assert_error(error, caller, "invalid_output", "Local model output is invalid", 502)
    else:
        assert asyncio.run(caller.complete()) is not None
    assert_closed(clients, requests, stream)


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "raw-deflate"])
def test_compression_bomb_bounds_decoder_allocation(monkeypatch, caller, encoding):
    limit = caller.module.MAX_RESPONSE_BYTES
    body = json.dumps(caller.envelope).encode() + b" " * (limit * 100)
    wire = compressed_body(body, encoding)
    assert len(wire) < limit
    stream = ChunkStream([wire, b"must not read"])
    clients, requests = install(
        monkeypatch,
        caller,
        stream,
        headers={"content-encoding": "deflate" if encoding == "raw-deflate" else encoding},
    )
    original = zlib.decompressobj
    decoded_sizes = []

    class BoundedDecoder:
        def __init__(self, *args):
            self.inner = original(*args)

        def decompress(self, data, max_length=0):
            assert 0 < max_length <= limit + 1, "Unbounded decompression"
            result = self.inner.decompress(data, max_length)
            decoded_sizes.append(len(result))
            return result

        def __getattr__(self, name):
            return getattr(self.inner, name)

    monkeypatch.setattr(local_transport.zlib, "decompressobj", BoundedDecoder)
    with pytest.raises(caller.error) as error:
        asyncio.run(caller.complete())
    assert_error(error, caller, "invalid_output", "Local model output is invalid", 502)
    assert decoded_sizes == [limit + 1]
    assert stream.reads == 1
    assert_closed(clients, requests, stream)


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
@pytest.mark.parametrize("damage", ["broken", "checksum", "truncated"])
def test_bad_compression_keeps_unavailable_error(monkeypatch, caller, encoding, damage):
    wire = compressed_body(json.dumps(caller.envelope).encode(), encoding)
    if damage == "broken":
        wire = b"private invalid compressed response"
    elif damage == "checksum":
        wire = wire[:-1] + bytes([wire[-1] ^ 255])
    else:
        wire = wire[:-2]
    stream = ChunkStream([wire])
    clients, requests = install(monkeypatch, caller, stream, headers={"content-encoding": encoding})
    with pytest.raises(caller.error) as error:
        asyncio.run(caller.complete())
    assert_error(error, caller, "unavailable", "Local model is unavailable", 503)
    assert_closed(clients, requests, stream)


def test_wire_limit_checked_before_decompression(monkeypatch, caller):
    limit = caller.module.MAX_RESPONSE_BYTES
    body = json.dumps(caller.envelope).encode()
    # A valid gzip stream can have a very large optional filename and a small body.
    wire = gzip.compress(body)
    wire = wire[:3] + bytes([wire[3] | 8]) + wire[4:10] + b"x" * limit + b"\0" + wire[10:]
    stream = ChunkStream([wire[:limit], wire[limit:], b"must not read"])
    clients, requests = install(monkeypatch, caller, stream, headers={"content-encoding": "gzip"})
    with pytest.raises(caller.error) as error:
        asyncio.run(caller.complete())
    assert_error(error, caller, "invalid_output", "Local model output is invalid", 502)
    assert stream.reads == 2
    assert_closed(clients, requests, stream)


def test_oversized_chunk_is_not_appended(monkeypatch, caller):
    class BoundedBuffer(bytearray):
        def extend(self, chunk):
            assert len(self) + len(chunk) <= caller.module.MAX_RESPONSE_BYTES
            super().extend(chunk)

    monkeypatch.setattr(local_transport, "bytearray", BoundedBuffer, raising=False)
    stream = ChunkStream([b"x" * (caller.module.MAX_RESPONSE_BYTES + 1)])
    clients, requests = install(monkeypatch, caller, stream)
    with pytest.raises(caller.error) as error:
        asyncio.run(caller.complete())
    assert_error(error, caller, "invalid_output", "Local model output is invalid", 502)
    assert_closed(clients, requests, stream)


@pytest.mark.parametrize("status", [201, 204, 302, 400, 500])
def test_non_200_body_is_never_read(monkeypatch, caller, status):
    stream = ChunkStream([b"private failure"])
    clients, requests = install(
        monkeypatch, caller, stream, status=status, headers={"location": "https://remote.invalid"}
    )
    with pytest.raises(caller.error) as error:
        asyncio.run(caller.complete())
    assert_error(error, caller, "unavailable", "Local model request failed", 503)
    assert stream.reads == 0
    assert_closed(clients, requests, stream)


@pytest.mark.parametrize("cancel", [False, True])
def test_deadline_and_external_cancellation_close_stream_and_client(monkeypatch, caller, cancel):
    monkeypatch.setattr(caller.module, "TIMEOUT_SECONDS", 10 if cancel else 0.02)
    stream = ChunkStream([b"{"], block=True)
    clients, requests = install(monkeypatch, caller, stream)

    async def run():
        task = asyncio.create_task(caller.complete())
        await asyncio.wait_for(stream.entered.wait(), timeout=1)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(caller.error) as error:
                await task
            assert_error(error, caller, "unavailable", "Local model is unavailable", 503)

    asyncio.run(run())
    assert stream.cancelled
    assert_closed(clients, requests, stream)


@pytest.mark.parametrize("usage", [None, "invalid", {"total_tokens": -1}, [False]])
def test_malformed_usage_and_falsey_forbidden_fields_remain_ignored(monkeypatch, caller, usage):
    caller.envelope["usage"] = usage
    caller.envelope["choices"][0]["message"].update(
        tool_calls=[], refusal="", reasoning_content=None, function_call={}, reasoning=False
    )
    stream = ChunkStream([json.dumps(caller.envelope).encode()])
    clients, requests = install(monkeypatch, caller, stream)
    assert asyncio.run(caller.complete()) is not None
    assert_closed(clients, requests, stream)
