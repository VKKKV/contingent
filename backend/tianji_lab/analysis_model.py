"""Stateless, typed, single-request local analysis inference.

The coordinator MUST own ``local_actor._CALL_SLOT`` for its entire analysis run.
This adapter never acquires it (doing so would deadlock a multi-step coordinator).
Only validated output and measured metadata escape; no histories are retained.
"""

import asyncio
import json
import logging
import os
import time
import zlib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx
import pydantic_ai
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from opentelemetry import context as otel_context
from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage, UsageLimits

from . import local_actor

# The application owns terminal/CLI output; observability stays explicitly off.
pydantic_ai.BANNER_ENABLED = False

TIMEOUT_SECONDS = 180
MAX_RESPONSE_BYTES = 65_536
MAX_PROMPT_BYTES = 24_576
MAX_TOKENS = 4096
_QUIET = ContextVar("tianji_analysis_quiet", default=False)


class AnalysisModelError(Exception):
    """Safe public error: code/message never contain provider or prompt text."""

    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def _invalid() -> AnalysisModelError:
    return AnalysisModelError("analysis_invalid_output", "Local model output is invalid")


@dataclass(frozen=True)
class CallResult[T: BaseModel]:
    output: T
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    model: str


class _QuietFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _QUIET.get()


_QUIET_FILTER = _QuietFilter()


@contextmanager
def _private_call():
    # SDK DEBUG logging includes full request bodies. Filter only this task, not
    # other application requests, and do not change global logging levels.
    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger) and name.split(".")[0] in {
            "openai",
            "httpx",
            "httpcore",
            "pydantic_ai",
            "pydantic_graph",
        }:
            logger.addFilter(_QUIET_FILTER)
    quiet_token = _QUIET.set(True)
    context = otel_context.set_value(otel_context._SUPPRESS_INSTRUMENTATION_KEY, True)
    context = otel_context.set_value(otel_context._SUPPRESS_HTTP_INSTRUMENTATION_KEY, True, context)
    trace_token = otel_context.attach(context)
    try:
        yield
    finally:
        otel_context.detach(trace_token)
        _QUIET.reset(quiet_token)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def _no_constant(value):
    raise ValueError("Non-finite JSON number")


def _json(data: str | bytes | bytearray):
    if not isinstance(data, str):
        data = data.decode("utf-8", errors="strict")
    return json.loads(data, object_pairs_hook=_unique_object, parse_constant=_no_constant)


class _LocalChatModel(OpenAIChatModel):
    def _map_usage(self, response) -> RequestUsage:
        # Do not consult genai-prices snapshots, price updates or remote metadata.
        usage = response.usage
        return RequestUsage(
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )


class _BoundedTransport(httpx.AsyncBaseTransport):
    """Check raw protocol before the SDK can coerce or discard response fields."""

    def __init__(self, origin: str, output_type: type[BaseModel]):
        self.inner = httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self.endpoint = httpx.URL(origin + "/v1/chat/completions")
        self.output_type = output_type
        self.sent = False
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.error: AnalysisModelError | None = None

    async def aclose(self):
        await self.inner.aclose()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return await self._request(request)
        except AnalysisModelError as exc:
            # OpenAI wraps transport exceptions. Retain only a safe error, not
            # its traceback (which could otherwise retain a response body).
            self.error = AnalysisModelError(exc.code, exc.message)
            raise

    async def _request(self, request: httpx.Request) -> httpx.Response:
        if self.sent or request.method != "POST" or request.url != self.endpoint:
            raise AnalysisModelError("analysis_unavailable", "Local model request is not allowed")
        self.sent = True
        body = await request.aread()
        # Bound the entire wire JSON, including instructions/schema/context.
        if len(body) > MAX_PROMPT_BYTES:
            raise AnalysisModelError("analysis_prompt_too_large", "Local model prompt is too large")
        # Strip ambient SDK headers (OPENAI_CUSTOM_HEADERS, org/project, etc.).
        # No credentials or caller-provided headers belong on this local call.
        request.headers = httpx.Headers(
            {
                "Host": request.url.netloc.decode("ascii"),
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            }
        )
        response = await self.inner.handle_async_request(request)
        try:
            if response.status_code != 200:
                raise AnalysisModelError("analysis_unavailable", "Local model request failed")
            body = await self._read_body(response)
            self._validate_body(body)
            return httpx.Response(
                200,
                content=bytes(body),
                headers={"Content-Type": "application/json"},
                request=request,
            )
        finally:
            await response.aclose()

    async def _read_body(self, response: httpx.Response) -> bytearray:
        encoding = response.headers.get("content-encoding", "identity").lower().strip()
        if encoding not in {"identity", "gzip", "deflate"}:
            raise _invalid()
        decoder = None
        if encoding != "identity":
            decoder = zlib.decompressobj(31 if encoding == "gzip" else zlib.MAX_WBITS)
        body = bytearray()
        wire_bytes = 0
        try:
            async for chunk in response.aiter_raw():
                wire_bytes += len(chunk)
                if wire_bytes > MAX_RESPONSE_BYTES:
                    raise _invalid()
                if decoder is not None:
                    # httpx.aiter_bytes() decompresses before yielding and can
                    # allocate an unbounded compression bomb. Bound zlib itself.
                    chunk = decoder.decompress(chunk, MAX_RESPONSE_BYTES - len(body) + 1)
                if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise _invalid()
                body.extend(chunk)
            if decoder is not None and (not decoder.eof or decoder.unused_data):
                raise _invalid()
        except zlib.error:
            raise _invalid() from None
        return body

    def _validate_body(self, body: bytearray):
        try:
            payload = _json(body)
            choices = payload["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            message = choice["message"]
            if choice["finish_reason"] != "stop" or message["role"] != "assistant":
                raise ValueError
            for field in (
                "tool_calls",
                "function_call",
                "refusal",
                "reasoning",
                "reasoning_content",
                "reasoning_details",
                "thinking",
            ):
                if message.get(field) not in (None, "", []):
                    raise ValueError
            content = message["content"]
            if not isinstance(content, str) or not isinstance(_json(content), dict):
                raise ValueError
            # JSON strict mode preserves JSON-native dates/enums, but forbids
            # coercions (including bool/int). Domain validators enforce references.
            self.output_type.model_validate_json(content, strict=True, extra="forbid")
            usage = payload.get("usage")
            if usage is not None:
                counts = [usage["prompt_tokens"], usage["completion_tokens"]]
                if any(type(value) is not int or value < 0 for value in counts):
                    raise ValueError
                self.input_tokens, self.output_tokens = counts
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
            raise _invalid() from None


@dataclass(frozen=True)
class LocalAnalysisModel:
    url: str | None
    model: str | None

    @classmethod
    def from_env(cls) -> "LocalAnalysisModel":
        return cls(
            os.environ.get("TIANJI_LOCAL_MODEL_URL"), os.environ.get("TIANJI_LOCAL_MODEL_NAME")
        )

    async def complete[T: BaseModel](
        self,
        role: str,
        instructions: str,
        context: dict[str, Any],
        output_type: type[T],
        max_tokens: int = 1800,
    ) -> CallResult[T]:
        """One fresh NativeOutput agent; caller owns the shared global call slot.

        Cancellation propagates after closing this call's HTTP client. Errors are
        sanitized; absent provider usage is None, never an estimated token count.
        max_tokens must be an integer in 1..4096; duration_ms is wall duration.
        """
        if not self.url or not self.model:
            raise AnalysisModelError("analysis_disabled", "Local model is not configured")
        try:
            origin = local_actor.validate_origin(self.url)
            if (
                not self.model.strip()
                or len(self.model) > 200
                or any(ord(char) < 32 for char in self.model)
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise AnalysisModelError(
                "analysis_unavailable", "Local model configuration is invalid"
            ) from None
        try:
            if (
                not isinstance(role, str)
                or not role.strip()
                or not isinstance(instructions, str)
                or not isinstance(context, dict)
                or not isinstance(output_type, type)
                or not issubclass(output_type, BaseModel)
                or type(max_tokens) is not int
                or not 1 <= max_tokens <= MAX_TOKENS
            ):
                raise ValueError
            prompt = json.dumps(
                {"role": role, "context": context}, ensure_ascii=False, allow_nan=False
            )
            prompt_size = len(prompt.encode("utf-8")) + len(instructions.encode("utf-8"))
        except (ValueError, TypeError, RecursionError):
            raise AnalysisModelError(
                "analysis_invalid_request", "Local model request is invalid"
            ) from None
        if prompt_size > MAX_PROMPT_BYTES:
            raise AnalysisModelError("analysis_prompt_too_large", "Local model prompt is too large")

        started = time.monotonic()
        transport = _BoundedTransport(origin, output_type)
        error = None
        try:
            with _private_call():
                async with asyncio.timeout(TIMEOUT_SECONDS):
                    async with httpx.AsyncClient(
                        transport=transport,
                        trust_env=False,
                        follow_redirects=False,
                        timeout=TIMEOUT_SECONDS,
                    ) as client:
                        sdk = AsyncOpenAI(
                            base_url=origin + "/v1",
                            api_key="local-only",
                            organization="",
                            project="",
                            admin_api_key="",
                            webhook_secret="",
                            http_client=client,
                            max_retries=0,
                            timeout=TIMEOUT_SECONDS,
                        )
                        model = _LocalChatModel(
                            self.model,
                            provider=OpenAIProvider(openai_client=sdk),
                            profile={
                                "supports_json_schema_output": True,
                                "supports_tools": False,
                                "openai_chat_supports_max_completion_tokens": False,
                            },
                        )
                        agent = Agent(
                            model,
                            name="local_analysis",
                            output_type=NativeOutput(output_type, strict=True, template=False),
                            instructions=instructions,
                            retries=0,
                            model_settings={
                                "temperature": 0,
                                "max_tokens": max_tokens,
                                "extra_body": {
                                    "cache_prompt": False,
                                    "chat_template_kwargs": {"enable_thinking": False},
                                },
                            },
                        )
                        # PydanticAI 2.46 removed the constructor instrument kwarg.
                        agent.instrument = False
                        result = await agent.run(
                            prompt, usage_limits=UsageLimits(request_limit=1), infer_name=False
                        )
                        return CallResult(
                            output=result.output,
                            input_tokens=transport.input_tokens,
                            output_tokens=transport.output_tokens,
                            duration_ms=int((time.monotonic() - started) * 1000),
                            model=self.model,
                        )
        except asyncio.CancelledError:
            raise
        except (TimeoutError, APITimeoutError):
            error = AnalysisModelError("analysis_timeout", "Local model request timed out")
        except (httpx.HTTPError, APIConnectionError, APIStatusError, ModelAPIError, OSError) as exc:
            if isinstance(exc, (httpx.TimeoutException, APITimeoutError)) or isinstance(
                exc.__cause__, APITimeoutError
            ):
                error = AnalysisModelError("analysis_timeout", "Local model request timed out")
            else:
                error = transport.error or AnalysisModelError(
                    "analysis_unavailable", "Local model is unavailable"
                )
        except AnalysisModelError as exc:
            error = AnalysisModelError(exc.code, exc.message)
        except Exception:
            error = _invalid()
        # Raise outside handlers: no chained provider exception/raw completion.
        raise error
