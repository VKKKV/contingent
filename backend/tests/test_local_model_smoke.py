"""Offline validation of the opt-in smoke runner; never starts a model."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "local_model_smoke", Path(__file__).resolve().parents[2] / "scripts/check-local-model.py"
)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.mark.parametrize("url", ["http://127.0.0.1:18789", "http://[::1]:18789/"])
def test_loopback_origin(url):
    assert smoke.local_url(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org",
        "http://192.168.1.2",
        "http://localhost:18789",
        "http://127.0.0.1:18789/v1",
        "http://user:secret@127.0.0.1",
        "http://127.0.0.1?token=secret",
        "http://127.0.0.1#fragment",
    ],
)
def test_remote_or_credentialed_origins_are_rejected(url):
    with pytest.raises(ValueError):
        smoke.local_url(url)


def response(content, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


def test_strict_model_output_no_repair_or_fallback():
    assert smoke.parse_choice(response('{"action":"wait"}')).action == "wait"
    for value in [
        "wait",
        '```json\n{"action":"wait"}\n```',
        '{"action":"buy"}',
        '{"action":"wait","extra":1}',
        '{"action":null}',
    ]:
        with pytest.raises(ValueError):
            smoke.parse_choice(response(value))
    with pytest.raises(ValueError, match="non-truncated"):
        smoke.parse_choice(response('{"action":"wait"}', "length"))
