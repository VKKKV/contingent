"""Opt-in local model smoke test; never used by the product or default test suite.

Uses an already running loopback llama.cpp OpenAI-compatible endpoint. No model
installation, credentials, remote endpoint, retries or fallback proposals.
"""

import argparse
import hashlib
import ipaddress
import json
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tianji_lab import kernel
from tianji_lab.models import Action, Scenario, State
from tianji_lab.service import Service


class ModelChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Action


def local_url(value):
    parsed = urlsplit(value)
    try:
        local = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = False
    if (
        parsed.scheme != "http"
        or not local
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError(
            "Use an explicit loopback http://IP:port origin; no credentials or paths"
        )
    return value.rstrip("/")


def parse_choice(response):
    choices = response.get("choices", [])
    if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise ValueError("Expected one complete, non-truncated model response")
    return ModelChoice.model_validate_json(choices[0]["message"]["content"])


def run(base_url, model, report):
    def call(name, **arguments):
        return service.execute(name, arguments, str(uuid.uuid4()))

    with tempfile.TemporaryDirectory(prefix="tianji-model-smoke-") as directory:
        service = Service(Path(directory))
        try:
            with httpx.Client(
                base_url=local_url(base_url),
                timeout=60,
                trust_env=False,
                follow_redirects=False,
            ) as http:
                health = http.get("/health")
                health.raise_for_status()
                models = http.get("/v1/models")
                models.raise_for_status()
                report["server_models"] = models.json()
                if model not in {item["id"] for item in models.json()["data"]}:
                    raise ValueError(
                        "Requested model is not listed by the local server"
                    )
                for label, role, cash in (
                    ("retailer-funded", "retailer", 160),
                    ("retailer-no-cash", "retailer", 0),
                    ("supplier", "supplier", 160),
                ):
                    scenario = call(
                        "scenario_create",
                        spec={
                            "name": label,
                            "initial_inventory": 0,
                            "initial_cash": cash,
                        },
                    )
                    job = call("run_forward", scenario_id=scenario["id"], actions=[])
                    deadline = time.monotonic() + 15
                    while job["status"] in ("queued", "running"):
                        if time.monotonic() > deadline:
                            raise TimeoutError("Source branch generation timed out")
                        time.sleep(0.02)
                        job = call("job_get", id=job["id"])
                    if job["status"] != "succeeded":
                        raise RuntimeError(
                            f"Source branch generation failed: {job['status']}"
                        )
                    branch = job["result"]["branch"]
                    saved = call(
                        "observation_create",
                        branch_id=branch["id"],
                        tick=0,
                        actor_id=label,
                        role=role,
                    )
                    observation = saved["observation"]
                    # Only role-scoped projection and public action rules go to the model.
                    # No authoritative spec, hidden stock/loss, full state, token or state hash.
                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You propose one action for a fictional supply-chain simulation. "
                                "Return only a JSON object with an action field. Available actions: "
                                "wait, order_standard, order_express. Retailers can order 8 units: "
                                "standard costs 16 and arrives after 2 ticks; express costs 32 and "
                                "arrives after 1 tick before demand. Demand is 4 per tick. "
                                "Minimize immediate shortage, never spend more than observed cash. "
                                "Supplier role has no purchasing permission and can only wait. "
                                "Unknown private values must remain unknown. A separate kernel "
                                "will check your action; you cannot update state."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"role": role, "projection": observation["projection"]},
                                sort_keys=True,
                            ),
                        },
                    ]
                    request = {
                        "model": model,
                        "messages": messages,
                        "temperature": 0,
                        "seed": 42,
                        "max_tokens": 96,
                        "stream": False,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "action_choice",
                                "strict": True,
                                "schema": ModelChoice.model_json_schema(),
                            },
                        },
                    }
                    case = {"case": label, "request": request}
                    report["cases"].append(case)
                    started = time.monotonic()
                    response = http.post("/v1/chat/completions", json=request)
                    case["elapsed_seconds"] = round(time.monotonic() - started, 4)
                    case["http_status"] = response.status_code
                    response.raise_for_status()
                    case["response"] = response.json()
                    choice = parse_choice(case["response"])
                    proposal = {
                        "actor_id": label,
                        "role": role,
                        "action": choice.action,
                        "observation_hash": observation["observation_hash"],
                        "policy_id": "local.llamacpp.smoke.v1",
                    }
                    result = call(
                        "adjudication_create",
                        observation_id=saved["id"],
                        proposal=proposal,
                        adjudicator_id="independent-kernel-smoke",
                    )
                    assert call("adjudication_get", id=result["id"]) == result
                    assert call("adjudication_list", branch_id=branch["id"])[
                        "items"
                    ] == [result]
                    assert call("branch_get", id=branch["id"]) == branch
                    before = State.model_validate(
                        branch["trajectory"]["frames"][0]["state"]
                    )
                    if result["record"]["status"] == "accepted":
                        direct = kernel.step(
                            Scenario.model_validate(branch["spec"]),
                            before,
                            choice.action,
                        )
                        assert result["next_state"] == direct.state.model_dump(
                            mode="json"
                        )
                    else:
                        assert result["next_state"] == before.model_dump(mode="json")
                    case.update(
                        {
                            "observation": saved,
                            "proposal": proposal,
                            "adjudication": result,
                            "readback_verified": True,
                            "source_branch_unchanged": True,
                        }
                    )
                report["passed"] = True
        finally:
            service.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18789")
    parser.add_argument("--model", default="tianji-local-smoke")
    parser.add_argument(
        "--model-file",
        type=Path,
        required=True,
        help="GGUF provenance (hashed locally)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    local_url(args.url)
    with args.model_file.open("rb") as file:
        model_hash = hashlib.file_digest(file, "sha256").hexdigest()
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "passed": False,
        "scope": "three-call opt-in local smoke; not a quality benchmark or product agent loop",
        "url": args.url,
        "model": args.model,
        "model_file": args.model_file.name,
        "model_sha256": model_hash,
        "model_bytes": args.model_file.stat().st_size,
        "cases": [],
    }
    try:
        run(args.url, args.model, report)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(
            json.dumps(
                {
                    "passed": report["passed"],
                    "output": str(args.output),
                    "cases": [
                        {
                            "case": c["case"],
                            "seconds": c.get("elapsed_seconds"),
                            "action": c.get("proposal", {}).get("action"),
                            "status": c.get("adjudication", {})
                            .get("record", {})
                            .get("status"),
                        }
                        for c in report["cases"]
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
