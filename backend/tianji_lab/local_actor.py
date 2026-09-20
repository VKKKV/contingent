"""Opt-in, stateless llama.cpp proposals from public role observations only."""

import asyncio
import ipaddress
import json
import os
import re
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .local_transport import post_completion
from .models import Action, Model, Scenario
from .offline_adjudication import ActionProposal, ObservationEnvelope

POLICY_ID = "local.llamacpp.v1"
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 16_384
_CALL_SLOT = threading.BoundedSemaphore(1)


class LocalActorError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class PublicRules(Model):
    horizon: int
    demand_per_tick: int
    shipment_size: int
    standard_cost: int
    express_cost: int
    standard_lead: int
    express_lead: int

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> "PublicRules":
        # Explicit allowlist: never serialize the scenario, its private initial
        # state, free text, or director-only disturbance schedule into a prompt.
        return cls(**{key: getattr(scenario, key) for key in cls.model_fields})


class ActionOutput(Model):
    action: Action


def validate_origin(url: str) -> str:
    """Accept only literal loopback HTTP origins, without even a trailing slash."""
    try:
        if not re.fullmatch(r"http://(?:[0-9.]+|\[[0-9a-fA-F:]+\])(?::[0-9]+)?", url):
            raise ValueError
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "http"
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "?" in url
            or "#" in url
            or parsed.username is not None
            or parsed.password is not None
            or "%" in host
            or not ipaddress.ip_address(host).is_loopback
            or any(char.isspace() or ord(char) < 32 for char in url)
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
            or parsed.netloc.endswith(":")
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Local model URL must be a literal loopback HTTP origin") from None
    return url


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class LocalActor:
    url: str | None
    model: str | None

    @classmethod
    def from_env(cls) -> "LocalActor":
        return cls(
            os.environ.get("TIANJI_LOCAL_MODEL_URL"), os.environ.get("TIANJI_LOCAL_MODEL_NAME")
        )

    def propose(self, observation: ObservationEnvelope, rules: PublicRules) -> ActionProposal:
        if not self.url or not self.model:
            raise LocalActorError("actor_disabled", "Local actor is not configured", 503)
        try:
            origin = validate_origin(self.url)
            if not self.model.strip() or len(self.model) > 200:
                raise ValueError
        except ValueError:
            raise LocalActorError(
                "actor_unavailable", "Local actor configuration is invalid", 503
            ) from None
        if not _CALL_SLOT.acquire(blocking=False):
            raise LocalActorError("actor_busy", "Local actor is already processing a proposal", 409)
        try:
            action = asyncio.run(self._complete(origin, observation, rules))
            return ActionProposal(
                actor_id=observation.actor_id,
                role=observation.role,
                action=action,
                observation_hash=observation.observation_hash,
                policy_id=POLICY_ID,
            )
        finally:
            _CALL_SLOT.release()

    async def _complete(
        self, origin: str, observation: ObservationEnvelope, rules: PublicRules
    ) -> Action:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Propose one action for a fictional supply-chain participant. "
                        "Return only a JSON object with the action key, no explanation. "
                        "Retailer may wait, order_standard or order_express; "
                        "supplier may only wait. Minimize shortage while conserving cash. "
                        "Costs are per shipment; an order requires enough cash and supplier stock. "
                        "Order now, advance one tick, receive shipments due by that tick, "
                        "apply any exogenous events, then serve demand. "
                        "Arrival is current tick plus the selected lead. Shortage is lost "
                        "demand, not backlog. No action is valid at the horizon. Unobserved state "
                        "and future disturbances are unknown; do not invent them. This is only a "
                        "proposal; an independent adjudicator checks permissions and legality."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "role": observation.role,
                            "projection": observation.projection.model_dump(mode="json"),
                            "public_rules": rules.model_dump(mode="json"),
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "action",
                    "strict": True,
                    "schema": ActionOutput.model_json_schema(),
                },
            },
            "max_tokens": 96,
            "temperature": 0,
            "stream": False,
            "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        body = await post_completion(
            origin,
            payload,
            timeout=TIMEOUT_SECONDS,
            max_response_bytes=MAX_RESPONSE_BYTES,
            error_factory=LocalActorError,
            error_prefix="actor",
            client_factory=httpx.AsyncClient,
        )
        try:
            result = json.loads(body, object_pairs_hook=_unique_object)
            choices = result["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            message = choice["message"]
            if (
                choice["finish_reason"] != "stop"
                or message.get("role") != "assistant"
                or message.get("tool_calls")
                or message.get("refusal")
                or message.get("reasoning_content")
            ):
                raise ValueError
            content = message["content"]
            if not isinstance(content, str) or len(content) > 512:
                raise ValueError
            return ActionOutput.model_validate(
                json.loads(content, object_pairs_hook=_unique_object)
            ).action
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
            raise LocalActorError(
                "actor_invalid_output", "Local model output is invalid", 502
            ) from None
