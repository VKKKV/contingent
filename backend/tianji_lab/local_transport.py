"""Bounded HTTP exchange for legacy callers; parsing and call slots stay with them."""

import asyncio
import zlib
from collections.abc import Callable
from typing import Any

import httpx


async def post_completion(
    origin: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    max_response_bytes: int,
    error_factory: Callable[[str, str, int], Exception],
    error_prefix: str,
    client_factory: Callable[..., httpx.AsyncClient],
) -> bytes:
    try:
        # httpx bounds each IO phase; this also bounds a trickling response.
        async with asyncio.timeout(timeout):
            async with client_factory(
                trust_env=False, follow_redirects=False, timeout=timeout
            ) as client:
                async with client.stream(
                    "POST",
                    origin + "/v1/chat/completions",
                    json=payload,
                    headers={"Accept-Encoding": "gzip, deflate"},
                ) as response:
                    if response.status_code != 200:
                        raise error_factory(
                            f"{error_prefix}_unavailable", "Local model request failed", 503
                        )
                    body = await _read_body(
                        response, max_response_bytes, error_factory, error_prefix
                    )
    except (httpx.HTTPError, TimeoutError, OSError):
        raise error_factory(
            f"{error_prefix}_unavailable", "Local model is unavailable", 503
        ) from None
    return bytes(body)


async def _read_body(response, limit, error_factory, error_prefix):
    def invalid():
        return error_factory(f"{error_prefix}_invalid_output", "Local model output is invalid", 502)

    # Custom transports may return an already buffered (and decoded) response.
    # Real streaming responses must never pass through httpx's unbounded decoder.
    if response.is_stream_consumed:
        if len(response.content) > limit:
            raise invalid()
        return response.content

    encoding = response.headers.get("content-encoding", "identity").lower().strip()
    if encoding not in {"identity", "gzip", "deflate"}:
        raise invalid()
    decoder = zlib.decompressobj(31) if encoding == "gzip" else None
    prefix = b""
    body = bytearray()
    wire_bytes = 0
    try:
        async for chunk in response.aiter_raw():
            wire_bytes += len(chunk)
            if wire_bytes > limit:
                raise invalid()
            if encoding == "deflate" and decoder is None:
                # HTTP deflate servers use both zlib-wrapped and raw streams.
                # Inspect two header bytes even when split across network chunks.
                chunk = prefix + chunk
                if len(chunk) < 2:
                    prefix = chunk
                    continue
                wrapped = (
                    chunk[0] & 15 == 8
                    and chunk[0] >> 4 <= 7
                    and int.from_bytes(chunk[:2], "big") % 31 == 0
                )
                decoder = zlib.decompressobj(zlib.MAX_WBITS if wrapped else -zlib.MAX_WBITS)
            if decoder is not None:
                # The extra byte detects overflow without allocating an entire
                # decoded compression bomb. Never call an unbounded flush().
                chunk = decoder.decompress(chunk, limit - len(body) + 1)
            if len(body) + len(chunk) > limit:
                raise invalid()
            body.extend(chunk)
        if encoding != "identity" and (decoder is None or not decoder.eof or decoder.unused_data):
            raise httpx.DecodingError("Invalid compressed response")
    except zlib.error:
        # Match the existing httpx decoding-error -> unavailable contract.
        raise httpx.DecodingError("Invalid compressed response") from None
    return body
