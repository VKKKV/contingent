"""Real Chromium + HTTP + MCP acceptance against an isolated temporary laboratory.

Run from the root: uv run --project backend --group browser python scripts/check-lab-browser.py
No mock responses, provider calls, production data or fixed port required.
"""

import asyncio
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright, expect
from tianji_lab import kernel
from tianji_lab.models import Scenario, State
from tianji_lab.offline_adjudication import AdjudicationRecord, ObservationEnvelope

ROOT = Path(__file__).resolve().parents[1]


async def acceptance(url, token, out):
    checks = []
    async with httpx.AsyncClient(
        base_url=url,
        trust_env=False,
        timeout=15,
        headers={"Authorization": f"Bearer {token}"},
    ) as http:

        async def op(name, **arguments):
            response = await http.post(
                f"/api/operations/{name}",
                json={
                    "arguments": arguments,
                    "request_id": str(uuid.uuid4()),
                },
            )
            assert response.is_success, (name, response.status_code, response.text)
            return response.json()["data"]

        async def finish(job):
            deadline = time.monotonic() + 40
            while job["status"] in ("queued", "running"):
                assert time.monotonic() < deadline, job
                await asyncio.sleep(0.04)
                job = await op("job_get", id=job["id"])
            assert job["status"] == "succeeded", job
            return job["result"]

        async with async_playwright() as browser_api:
            browser = await browser_api.chromium.launch()
            page = await browser.new_page(viewport={"width": 1440, "height": 1050})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.set_default_timeout(15000)
            try:
                await page.goto(url)
                await expect(page.get_by_test_id("run-forward")).to_be_disabled()
                await page.get_by_test_id("token-input").fill(token)
                await page.get_by_test_id("connect-button").click()
                await expect(page.get_by_test_id("scenario-name")).to_be_visible()
                assert (
                    await page.get_by_test_id("initial-inventory").get_attribute("max")
                    == "100"
                )
                checks.append("connect and capability-generated scenario constraints")

                async def click_operation(testid, operation):
                    async with page.expect_response(
                        lambda r: (
                            r.url.endswith(f"/api/operations/{operation}")
                            and r.request.method == "POST"
                        )
                    ) as event:
                        await page.get_by_test_id(testid).click()
                    response = await event.value
                    assert response.ok, (operation, await response.text())
                    return (await response.json())["data"]

                async def run(testid, operation, branch_key="branch"):
                    result = await finish(await click_operation(testid, operation))
                    branch = (
                        result[branch_key]
                        if branch_key == "branch"
                        else result[branch_key][0]
                    )
                    await expect(
                        page.get_by_test_id(f"branch-{branch['id']}")
                    ).to_have_attribute("aria-pressed", "true", timeout=30000)
                    return result, branch

                original_id = await page.get_by_test_id("scenario-select").input_value()
                await page.get_by_test_id("scenario-name").fill("Browser acceptance")
                created = await click_operation("new-scenario", "scenario_create")
                await expect(page.get_by_test_id("scenario-select")).to_have_value(
                    created["id"]
                )
                await page.get_by_test_id("scenario-name").fill(
                    "Browser acceptance saved"
                )
                saved = await click_operation("save-scenario", "scenario_update")
                assert saved["revision"] == 2 and saved["id"] != original_id
                await expect(page.get_by_test_id("save-scenario")).to_be_disabled()
                checks.append("browser creates, edits and reads back scenario")

                await page.get_by_test_id("run-name").fill("Wait baseline")
                _, baseline = await run("run-forward", "run_forward")
                assert baseline["trajectory"]["final_state"]["shortage"] == 12
                await expect(page.get_by_test_id("timeline-slider")).to_have_value("0")
                await page.get_by_test_id("timeline-slider").fill("6")
                await expect(page.get_by_test_id("state-shortage")).to_have_text("12")
                checks.append(
                    "browser forward trajectory, actual time cursor and shortage display"
                )

                await page.get_by_test_id("run-name").fill("Goal plan")
                search, plan = await run("run-backward", "run_backward", "branches")
                assert (
                    search["search"]["status"] == "found"
                    and plan["trajectory"]["goal_met"]
                )
                await expect(page.get_by_test_id("job-status")).to_contain_text(
                    "找到可行候选"
                )
                # Delay a real response, not the request: the browser must apply a newer
                # workspace AND load its branch before the stale body is delivered.
                workspace_id = await page.get_by_test_id("workspace-id").inner_text()
                await page.get_by_test_id(f"branch-{baseline['id']}").click()
                await expect(
                    page.get_by_test_id(f"branch-{baseline['id']}")
                ).to_have_attribute("aria-pressed", "true")
                await expect(page.get_by_test_id("connection-status")).to_have_text(
                    "API 已连接"
                )
                branch_response_held = asyncio.Event()
                release_branch_get = asyncio.Event()
                branch_route_finished = asyncio.Event()
                held_request = None

                async def delay_selected_branch(route):
                    nonlocal held_request
                    body = route.request.post_data_json
                    if (
                        held_request is None
                        and body
                        and body.get("arguments", {}).get("id") == plan["id"]
                    ):
                        held_request = route.request
                        response = await route.fetch()
                        assert response.ok, await response.text()
                        assert (await response.json())["data"] == plan
                        branch_response_held.set()
                        await release_branch_get.wait()
                        try:
                            await route.fulfill(response=response)
                        finally:
                            branch_route_finished.set()
                    else:
                        await route.continue_()

                baseline_frame = baseline["trajectory"]["frames"][-2]["state"]
                baseline_tick = baseline_frame["tick"]
                assert baseline_frame != plan["trajectory"]["frames"][-2]["state"]

                async def expect_baseline():
                    await expect(page.locator(".sync-info")).to_contain_text(
                        re.compile(rf"rev {newer_workspace['revision']}\b")
                    )
                    await expect(
                        page.get_by_test_id(f"branch-{baseline['id']}")
                    ).to_have_attribute("aria-pressed", "true")
                    await expect(
                        page.get_by_test_id(f"branch-{plan['id']}")
                    ).to_have_attribute("aria-pressed", "false")
                    await expect(page.get_by_test_id("timeline-slider")).to_have_value(
                        str(baseline_tick)
                    )
                    await expect(page.get_by_test_id("current-tick")).to_have_text(
                        f"T{baseline_tick}"
                    )
                    await expect(
                        page.get_by_role("button", name="时间线", exact=True)
                    ).to_have_attribute("aria-pressed", "true")
                    for key in ("inventory", "cash", "shortage", "spent"):
                        await expect(page.get_by_test_id(f"state-{key}")).to_have_text(
                            str(baseline_frame[key])
                        )
                    await expect(page.get_by_test_id("fork-branch")).to_contain_text(
                        f"从 T{baseline_tick} 创建分支"
                    )
                    await expect(
                        page.get_by_test_id(f"fork-action-{baseline_tick}")
                    ).to_have_value("wait")
                    await expect(
                        page.get_by_test_id("compare-select").locator(
                            f"option[value='{baseline['id']}']"
                        )
                    ).to_have_count(0)
                    await expect(
                        page.get_by_test_id("compare-select").locator(
                            f"option[value='{plan['id']}']"
                        )
                    ).to_have_count(1)

                await page.route("**/api/operations/branch_get", delay_selected_branch)
                try:
                    await page.get_by_test_id(f"branch-{plan['id']}").click()
                    await asyncio.wait_for(branch_response_held.wait(), timeout=15)
                    await expect(page.get_by_test_id("export-branch")).to_be_disabled()
                    current_workspace = await op("workspace_get", id=workspace_id)
                    assert current_workspace["branch_id"] == plan["id"]
                    newer_workspace = await op(
                        "workspace_update",
                        id=workspace_id,
                        revision=current_workspace["revision"],
                        branch_id=baseline["id"],
                        tick=baseline_tick,
                        panel="timeline",
                    )
                    assert newer_workspace["revision"] > current_workspace["revision"]
                    assert await op("workspace_get", id=workspace_id) == newer_workspace
                    await expect_baseline()
                    # This must be the still-pending click, not a completed click followed by
                    # an unrelated poll; busy is our UI-side consumption barrier after release.
                    await expect(page.get_by_test_id("connection-status")).to_have_text(
                        "正在操作"
                    )
                    assert not release_branch_get.is_set()
                    # Arm the exact request's completion before release. A matching DOM alone
                    # can pass before an old response arrives and is not a regression oracle.
                    async with page.expect_event(
                        "requestfinished",
                        predicate=lambda request: request == held_request,
                    ) as finished:
                        release_branch_get.set()
                    response = await (await finished.value).response()
                    assert response is not None and response.ok
                    assert (await response.json())["data"] == plan
                    # The click's act() finally clears busy only after acceptWorkspace returns.
                    await expect(page.get_by_test_id("connection-status")).to_have_text(
                        "API 已连接"
                    )
                    await expect_baseline()
                    for testid in (
                        "timeline-slider",
                        "export-branch",
                        "fork-branch",
                        "compare-select",
                    ):
                        await expect(page.get_by_test_id(testid)).to_be_enabled()
                    assert await op("workspace_get", id=workspace_id) == newer_workspace
                    await expect(page.get_by_test_id("error-banner")).to_be_hidden()
                finally:
                    release_branch_get.set()
                    if branch_response_held.is_set():
                        await asyncio.wait_for(branch_route_finished.wait(), timeout=15)
                    await page.unroute(
                        "**/api/operations/branch_get", delay_selected_branch
                    )
                # Restore the goal branch as the primary for the existing comparison workflow.
                await page.get_by_test_id(f"branch-{plan['id']}").click()
                await expect(
                    page.get_by_test_id(f"branch-{plan['id']}")
                ).to_have_attribute("aria-pressed", "true", timeout=30000)
                await expect(page.get_by_test_id("connection-status")).to_have_text(
                    "API 已连接"
                )
                checks.append(
                    "delayed branch_get finishes after newer workspace; "
                    "baseline state and controls survive"
                )
                await page.get_by_test_id("compare-select").select_option(
                    baseline["id"]
                )
                compared = await click_operation("compare-branches", "branch_compare")
                assert compared["delta"]["shortage"] == 12
                await expect(page.get_by_test_id("comparison-result")).to_be_visible()
                checks.append(
                    "browser goal search, same-model verified candidates and comparison"
                )

                await page.get_by_test_id(f"branch-{baseline['id']}").click()
                await expect(page.get_by_test_id("timeline-slider")).to_have_value("0")
                await page.get_by_test_id("timeline-slider").fill("2")
                await expect(page.get_by_test_id("current-tick")).to_have_text("T2")
                await page.get_by_test_id("fork-action-2").select_option(
                    "order_express"
                )
                await page.get_by_test_id("run-name").fill("Counterfactual")
                _, fork = await run("fork-branch", "branch_fork")
                assert fork["fork_tick"] == 2 and fork["parent_id"] == baseline["id"]
                assert (
                    fork["trajectory"]["frames"][0]["state"]
                    == baseline["trajectory"]["frames"][2]["state"]
                )
                assert await op("branch_get", id=baseline["id"]) == baseline
                checks.append(
                    "browser recorded-tick fork, changed action, unchanged parent"
                )

                async with page.expect_download() as download_event:
                    await page.get_by_test_id("export-branch").click()
                download = await download_event.value
                bundle_path = out / "browser-export.json"
                await download.save_as(bundle_path)
                bundle = json.loads(bundle_path.read_text())
                assert bundle["branch"]["id"] == fork["id"]
                async with page.expect_response(
                    lambda r: r.url.endswith("/api/operations/branch_import")
                ) as event:
                    await page.get_by_test_id("import-bundle").set_input_files(
                        bundle_path
                    )
                imported_response = await event.value
                assert imported_response.ok, await imported_response.text()
                imported = (await imported_response.json())["data"]
                assert imported["trajectory"] == fork["trajectory"]
                await expect(
                    page.get_by_test_id(f"branch-{imported['id']}")
                ).to_have_attribute("aria-pressed", "true")
                checks.append(
                    "browser real JSON download, upload and semantic replay import"
                )

                # Use an actual continuation frame, never tick zero on an imported fork.
                await expect(page.get_by_test_id("connection-status")).to_have_text(
                    "API 已连接"
                )
                source_frame = imported["trajectory"]["frames"][0]
                source_state = source_frame["state"]
                director_tick = source_state["tick"]
                assert director_tick >= fork["fork_tick"]
                await page.get_by_test_id("timeline-slider").fill(str(director_tick))
                await expect(page.get_by_test_id("current-tick")).to_have_text(
                    f"T{director_tick}"
                )
                await expect(page.get_by_test_id("observation-empty")).to_be_visible()
                await expect(page.get_by_test_id("observation-create")).to_be_disabled()
                await expect(
                    page.get_by_test_id("adjudication-submit")
                ).to_be_disabled()
                await expect(page.get_by_test_id("director-warning")).to_contain_text(
                    "角色投影不是多用户权限"
                )
                branches_before = await op(
                    "branch_list", scenario_id=imported["scenario_id"]
                )

                async def observe_role(role, actor, state):
                    await page.get_by_test_id("observation-role").select_option(role)
                    await page.get_by_test_id("observation-actor").fill(actor)
                    created_observation = await click_operation(
                        "observation-create", "observation_create"
                    )
                    # The create response precedes observation_get and React consumption.
                    await expect(
                        page.get_by_test_id("observation-projection")
                    ).to_be_visible()
                    await expect(page.get_by_test_id("director-busy")).to_be_hidden()
                    await expect(page.get_by_test_id("director-error")).to_be_hidden()
                    assert await op(
                        "observation_get", id=created_observation["id"]
                    ) == (created_observation)
                    assert (
                        json.loads(
                            await page.get_by_test_id(
                                "observation-envelope"
                            ).text_content()
                        )
                        == created_observation
                    )
                    envelope = created_observation["observation"]
                    ObservationEnvelope.model_validate(envelope).verify_integrity()
                    assert envelope["actor_id"] == actor and envelope["role"] == role
                    assert envelope["tick"] == state["tick"]
                    assert envelope["context"]["branch_id"] == imported["id"]
                    assert (
                        envelope["context"]["scenario_revision"]
                        == imported["scenario_revision"]
                    )
                    fields = (
                        {
                            "tick",
                            "inventory",
                            "cash",
                            "delivered",
                            "shortage",
                            "spent",
                            "shipments",
                        }
                        if role == "retailer"
                        else {"tick", "supplier_stock", "shipments"}
                    )
                    projection = envelope["projection"]
                    assert set(projection) == fields, projection
                    assert projection == {key: state[key] for key in fields}
                    assert (
                        json.loads(
                            await page.get_by_test_id(
                                "observation-projection"
                            ).inner_text()
                        )
                        == projection
                    )
                    assert (
                        "pre_state_hash" not in envelope
                        and "state_hash" not in envelope
                    )
                    return created_observation

                async def propose(observation, status):
                    await page.get_by_test_id("adjudication-action").select_option(
                        "order_express"
                    )
                    # Self-refereeing must remain disabled; an independent audit label enables it.
                    await page.get_by_test_id("adjudication-referee").fill(
                        observation["observation"]["actor_id"]
                    )
                    await expect(
                        page.get_by_test_id("adjudication-submit")
                    ).to_be_disabled()
                    await page.get_by_test_id("adjudication-referee").fill(
                        "browser-referee"
                    )
                    preview = await click_operation(
                        "adjudication-submit", "adjudication_create"
                    )
                    await expect(
                        page.get_by_test_id("adjudication-status")
                    ).to_contain_text(status)
                    await expect(page.get_by_test_id("director-busy")).to_be_hidden()
                    await expect(page.get_by_test_id("director-error")).to_be_hidden()
                    await expect(
                        page.get_by_test_id("adjudication-history")
                    ).to_have_attribute("aria-busy", "false")
                    await expect(
                        page.get_by_test_id(f"adjudication-history-{preview['id']}")
                    ).to_be_visible()
                    assert await op("adjudication_get", id=preview["id"]) == preview
                    assert (
                        json.loads(
                            await page.get_by_test_id(
                                "adjudication-next-state"
                            ).inner_text()
                        )
                        == preview["next_state"]
                    )
                    assert (
                        json.loads(
                            await page.get_by_test_id(
                                "adjudication-record"
                            ).text_content()
                        )
                        == preview["record"]
                    )
                    record = preview["record"]
                    AdjudicationRecord.model_validate(
                        record
                    )  # Also validates the record hash.
                    assert preview["observation_id"] == observation["id"]
                    assert record["context"] == observation["observation"]["context"]
                    assert (
                        record["observation_hash"]
                        == observation["observation"]["observation_hash"]
                    )
                    assert (
                        record["proposal_actor_id"]
                        == observation["observation"]["actor_id"]
                    )
                    assert record["role"] == observation["observation"]["role"]
                    assert record["adjudicator_id"] == "browser-referee"
                    assert record["policy_id"] == "manual.director.v1"
                    assert (
                        record["action"] == "order_express"
                        and record["status"] == status
                    )
                    assert record["pre_state_hash"] == source_frame["state_hash"]
                    assert record["post_state_hash"] == kernel.state_hash(
                        State.model_validate(preview["next_state"])
                    )
                    assert await op("branch_get", id=imported["id"]) == imported
                    assert await op(
                        "branch_list", scenario_id=imported["scenario_id"]
                    ) == (branches_before)
                    return preview

                retailer = await observe_role(
                    "retailer", "browser-retailer", source_state
                )
                accepted = await propose(retailer, "accepted")
                direct = kernel.step(
                    Scenario.model_validate(imported["spec"]),
                    State.model_validate(source_state),
                    "order_express",
                )
                assert accepted["next_state"] == direct.state.model_dump(mode="json")
                assert accepted["record"]["post_state_hash"] == direct.state_hash
                assert (
                    accepted["record"]["post_state_hash"]
                    != accepted["record"]["pre_state_hash"]
                )
                assert accepted["next_state"]["cash"] < source_state["cash"]
                assert (
                    accepted["next_state"]["supplier_stock"]
                    < source_state["supplier_stock"]
                )
                checks.append(
                    "retailer exact projection and persisted accepted preview "
                    "equal direct kernel step; "
                    "source branch and branch list unchanged"
                )
                await page.get_by_test_id("observation-role").select_option("supplier")
                await expect(page.get_by_test_id("observation-empty")).to_be_visible()
                await expect(page.get_by_test_id("adjudication-result")).to_be_hidden()
                await expect(page.get_by_test_id("adjudication-action")).to_have_value(
                    "wait"
                )
                await expect(page.get_by_test_id("adjudication-referee")).to_have_value(
                    ""
                )
                await expect(
                    page.get_by_test_id("adjudication-submit")
                ).to_be_disabled()
                supplier = await observe_role(
                    "supplier", "browser-supplier", source_state
                )
                rejected = await propose(supplier, "rejected")
                assert "supplier may only wait" in rejected["record"]["reason"]
                assert rejected["next_state"] == source_state
                assert (
                    rejected["record"]["post_state_hash"]
                    == rejected["record"]["pre_state_hash"]
                )
                checks.append(
                    "supplier stock/tick/shipments-only projection and persisted "
                    "order_express rejection; "
                    "equal pre/post hashes and unchanged source state"
                )

                history = [accepted, rejected]

                async def expect_history():
                    await expect(
                        page.get_by_test_id("adjudication-history")
                    ).to_have_attribute("aria-busy", "false")
                    await expect(
                        page.get_by_test_id("adjudication-history-error")
                    ).to_be_hidden()
                    await expect(
                        page.get_by_test_id("adjudication-history").locator("article")
                    ).to_have_count(len(history))
                    for preview in history:
                        item = page.get_by_test_id(
                            f"adjudication-history-{preview['id']}"
                        )
                        await expect(item).to_be_visible()
                        assert [
                            json.loads(text)
                            for text in await item.locator("pre").all_text_contents()
                        ] == [preview["next_state"], preview["record"]]
                    assert (await op("adjudication_list", branch_id=imported["id"]))[
                        "items"
                    ] == history

                refreshed = await click_operation(
                    "adjudication-reload", "adjudication_list"
                )
                assert refreshed["items"] == history
                await expect_history()
                # Capture the populated projection, rejection and persisted receipts at all widths.
                for width in (1440, 768, 390):
                    await page.set_viewport_size({"width": width, "height": 1050})
                    await expect(
                        page.get_by_test_id("observation-projection")
                    ).to_be_visible()
                    await expect(
                        page.get_by_test_id("adjudication-next-state")
                    ).to_be_visible()
                    assert await page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth + 1"
                    ), width
                    panel = page.get_by_test_id("director-panel")
                    assert await panel.evaluate("""el => {
                        const box = el.getBoundingClientRect();
                        return box.left >= 0 && box.right <= innerWidth + 1;
                    }"""), width
                    await page.screenshot(
                        path=str(out / f"director-{width}.png"), full_page=True
                    )
                    await panel.screenshot(
                        path=str(out / f"director-panel-{width}.png")
                    )
                checks.append(
                    "populated director projection/preview/history at "
                    "desktop/768px/390px without overflow"
                )
                await page.set_viewport_size({"width": 1440, "height": 1050})
                await page.reload()
                await page.get_by_test_id("connect-button").click()
                await expect(
                    page.get_by_test_id(f"branch-{imported['id']}")
                ).to_have_attribute("aria-pressed", "true")
                await expect(page.get_by_test_id("timeline-slider")).to_have_value(
                    str(director_tick)
                )
                await expect_history()
                await expect(page.get_by_test_id("observation-empty")).to_be_visible()
                await expect(page.get_by_test_id("adjudication-result")).to_be_hidden()
                await expect(
                    page.get_by_test_id("adjudication-submit")
                ).to_be_disabled()
                for observation in (retailer, supplier):
                    assert (
                        await op("observation_get", id=observation["id"]) == observation
                    )
                checks.append(
                    "history refresh and page reload/reconnect preserve real receipts "
                    "but clear observation"
                )

                # Hold the real observation_get body after persistence. Switching tick and role
                # must retire that session even after its actual readback has been consumed.
                observation_held = asyncio.Event()
                release_observation = asyncio.Event()
                observation_route_finished = asyncio.Event()
                stale_request = None
                stale_observation = None

                async def delay_observation(route):
                    nonlocal stale_request, stale_observation
                    if stale_request is not None:
                        await route.continue_()
                        return
                    stale_request = route.request
                    response = await route.fetch()
                    assert response.ok, await response.text()
                    stale_observation = (await response.json())["data"]
                    observation_held.set()
                    await release_observation.wait()
                    try:
                        await route.fulfill(response=response)
                    finally:
                        observation_route_finished.set()

                # Instrument only consumption, not response content. The timer runs after the
                # original json() promise and DirectorSession's awaiting continuation microtask.
                await page.evaluate("""() => {
                    window.__originalDirectorJson = Response.prototype.json;
                    window.__directorConsumed = null;
                    Response.prototype.json = async function (...args) {
                        const body = await window.__originalDirectorJson.apply(this, args);
                        if (this.url.endsWith('/api/operations/observation_get')) {
                            setTimeout(() => { window.__directorConsumed = body.data.id; }, 0);
                        }
                        return body;
                    };
                }""")
                await page.route("**/api/operations/observation_get", delay_observation)
                try:
                    await page.get_by_test_id("observation-actor").fill(
                        "browser-held-retailer"
                    )
                    pending_observation = await click_operation(
                        "observation-create", "observation_create"
                    )
                    await asyncio.wait_for(observation_held.wait(), timeout=15)
                    assert stale_observation == pending_observation
                    assert (
                        await op("observation_get", id=pending_observation["id"])
                        == pending_observation
                    )
                    await expect(page.get_by_test_id("director-busy")).to_be_visible()
                    next_state = imported["trajectory"]["frames"][1]["state"]
                    await page.get_by_test_id("timeline-slider").fill(
                        str(next_state["tick"])
                    )
                    await expect(page.get_by_test_id("current-tick")).to_have_text(
                        f"T{next_state['tick']}"
                    )
                    await page.get_by_test_id("observation-role").select_option(
                        "supplier"
                    )
                    await expect(
                        page.get_by_test_id("observation-empty")
                    ).to_be_visible()
                    await expect(
                        page.get_by_test_id("adjudication-referee")
                    ).to_have_value("")
                    await expect(
                        page.get_by_test_id("adjudication-action")
                    ).to_have_value("wait")
                    assert not release_observation.is_set()
                    async with page.expect_event(
                        "requestfinished",
                        predicate=lambda request: request == stale_request,
                    ) as finished:
                        release_observation.set()
                    response = await (await finished.value).response()
                    assert response is not None and response.ok
                    assert (await response.json())["data"] == pending_observation
                    await page.wait_for_function(
                        "id => window.__directorConsumed === id",
                        arg=pending_observation["id"],
                    )
                    await expect(
                        page.get_by_test_id("observation-empty")
                    ).to_be_visible()
                    await expect(
                        page.get_by_test_id("observation-projection")
                    ).to_be_hidden()
                    await expect(
                        page.get_by_test_id("adjudication-submit")
                    ).to_be_disabled()
                    await expect(page.get_by_test_id("director-busy")).to_be_hidden()
                    await expect(page.get_by_test_id("director-error")).to_be_hidden()
                    await expect(page.get_by_test_id("observation-role")).to_have_value(
                        "supplier"
                    )
                    await expect(page.get_by_test_id("timeline-slider")).to_have_value(
                        str(next_state["tick"])
                    )
                finally:
                    release_observation.set()
                    if observation_held.is_set():
                        await asyncio.wait_for(
                            observation_route_finished.wait(), timeout=15
                        )
                    await page.unroute(
                        "**/api/operations/observation_get", delay_observation
                    )
                    await page.evaluate("""() => {
                        Response.prototype.json = window.__originalDirectorJson;
                        delete window.__originalDirectorJson;
                        delete window.__directorConsumed;
                    }""")
                await observe_role("supplier", "browser-current-supplier", next_state)
                await expect_history()
                assert await op("branch_get", id=imported["id"]) == imported
                checks.append(
                    "held real observation readback consumed after tick/role switch "
                    "cannot install; "
                    "fresh current supplier observation succeeds"
                )

                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "tianji_lab", "mcp", "--url", url],
                    cwd=str(ROOT / "backend"),
                    env={**os.environ, "TIANJI_TOKEN": token},
                )
                async with (
                    stdio_client(params) as streams,
                    ClientSession(*streams) as session,
                ):
                    await session.initialize()
                    names = {t.name for t in (await session.list_tools()).tools}
                    catalog = (await http.get("/api/capabilities")).json()
                    assert names == {c["name"] for c in catalog}
                    ws = await op("workspace_get", id=workspace_id)
                    result = await session.call_tool(
                        "workspace_update",
                        {
                            "id": workspace_id,
                            "revision": ws["revision"],
                            "branch_id": plan["id"],
                            "tick": 3,
                            "panel": "goal",
                        },
                    )
                    assert not result.isError, result
                    await expect(
                        page.get_by_test_id(f"branch-{plan['id']}")
                    ).to_have_attribute("aria-pressed", "true")
                    await expect(page.get_by_test_id("timeline-slider")).to_have_value(
                        "3"
                    )
                    checks.append(
                        "official MCP selects a comparison target rendered by the browser"
                    )
                    ws = await op("workspace_get", id=workspace_id)
                    compared = await session.call_tool(
                        "workspace_update",
                        {
                            "id": workspace_id,
                            "revision": ws["revision"],
                            "compare_branch_id": baseline["id"],
                            "panel": "compare",
                        },
                    )
                    assert not compared.isError
                    await expect(
                        page.get_by_test_id("comparison-result")
                    ).to_be_visible()
                    await expect(page.get_by_test_id("compare-select")).to_have_value(
                        baseline["id"]
                    )
                    ws = await op("workspace_get", id=workspace_id)
                    empty_selection = await session.call_tool(
                        "workspace_update",
                        {
                            "id": workspace_id,
                            "revision": ws["revision"],
                            "scenario_id": original_id,
                        },
                    )
                    assert not empty_selection.isError
                    await expect(page.get_by_test_id("scenario-select")).to_have_value(
                        original_id
                    )
                    await expect(page.get_by_test_id("branch-list")).to_contain_text(
                        "尚无推演分支"
                    )
                    checks.append(
                        "official MCP selects an empty scenario without inventing a branch"
                    )
                    ws = await op("workspace_get", id=workspace_id)
                    result = await session.call_tool(
                        "workspace_update",
                        {
                            "id": workspace_id,
                            "revision": ws["revision"],
                            "branch_id": plan["id"],
                            "tick": 3,
                            "panel": "goal",
                        },
                    )
                    assert not result.isError
                    await expect(
                        page.get_by_role("button", name="目标", exact=True)
                    ).to_have_attribute("aria-pressed", "true")
                checks.append(
                    "MCP registry matches API; external branch/tick/panel visibly applied"
                )

                await page.reload()
                await page.get_by_test_id("connect-button").click()
                await expect(page.get_by_test_id("timeline-slider")).to_have_value("3")
                # Wait for actual subsequent polling, not a blind sleep: terminal job history must
                # not replay its old auto-selection and override the MCP-selected workspace.
                for _ in range(3):
                    await page.wait_for_event(
                        "response",
                        predicate=lambda r: r.url.endswith(
                            "/api/operations/workspace_get"
                        ),
                    )
                await expect(
                    page.get_by_test_id(f"branch-{plan['id']}")
                ).to_have_attribute("aria-pressed", "true")
                await expect(page.get_by_test_id("timeline-slider")).to_have_value("3")
                checks.append(
                    "reconnect preserves MCP workspace instead of replaying old job selections"
                )

                await page.get_by_test_id("scenario-name").fill("Unsaved human draft")
                current = next(
                    s
                    for s in (await op("scenario_list"))["items"]
                    if s["id"] == saved["id"]
                )
                await op(
                    "scenario_update",
                    id=saved["id"],
                    revision=current["revision"],
                    spec={**current["spec"], "name": "External revision"},
                )
                async with page.expect_response(
                    lambda r: r.url.endswith("/api/operations/scenario_update")
                ) as event:
                    await page.get_by_test_id("save-scenario").click()
                assert (await event.value).status == 409
                await expect(page.get_by_test_id("error-banner")).to_contain_text(
                    "版本冲突"
                )
                await expect(page.get_by_test_id("scenario-name")).to_have_value(
                    "Unsaved human draft"
                )
                await page.get_by_role("button", name="放弃修改，读取最新版本").click()
                await expect(page.get_by_test_id("scenario-name")).to_have_value(
                    "External revision"
                )
                checks.append(
                    "concurrent scenario edit returns 409 and preserves unsaved human draft"
                )

                await page.get_by_test_id("max-nodes").fill("1")
                incomplete = await finish(
                    await click_operation("run-backward", "run_backward")
                )
                assert incomplete["search"]["status"] == "budget_exhausted"
                await expect(page.get_by_test_id("job-status")).to_contain_text(
                    "预算耗尽，尚不能判定无解"
                )
                await page.get_by_test_id("max-nodes").fill("5000")
                await page.get_by_test_id("min-inventory").fill("100")
                impossible = await finish(
                    await click_operation("run-backward", "run_backward")
                )
                assert impossible["search"]["status"] == "no_solution"
                await expect(page.get_by_test_id("job-status")).to_contain_text(
                    "已穷尽搜索，目标无解"
                )
                checks.append(
                    "browser distinguishes incomplete budget from finite-model no solution"
                )

                await page.get_by_test_id("import-bundle").set_input_files(
                    {
                        "name": "invalid.json",
                        "mimeType": "application/json",
                        "buffer": b"not-json",
                    }
                )
                await expect(page.get_by_test_id("error-banner")).to_contain_text(
                    "有效 JSON"
                )
                checks.append("malformed browser import visibly rejected")
                await page.get_by_role("button", name="关闭错误").click()
                await page.get_by_test_id("scenario-name").fill("Cancellation model")
                await page.get_by_test_id("horizon").fill("10")
                await click_operation("save-scenario", "scenario_update")
                await page.get_by_test_id("max-nodes").fill("50000")
                await page.get_by_test_id("min-inventory").fill("0")
                queued = await click_operation("run-backward", "run_backward")
                cancel = page.get_by_test_id(f"cancel-job-{queued['id']}")
                await cancel.click()
                await expect(page.get_by_test_id("job-status")).to_contain_text(
                    "已取消"
                )
                assert (await op("job_get", id=queued["id"]))["status"] == "cancelled"
                checks.append("browser cancels actual queued/running work")

                # Capture director view with the real goal branch selected.
                await page.get_by_test_id(f"branch-{plan['id']}").click()
                await page.get_by_test_id("timeline-slider").fill("6")
                await expect(page.get_by_test_id("state-shortage")).to_have_text("0")
                await page.screenshot(path=str(out / "desktop.png"), full_page=True)
                for width in (768, 390):
                    await page.set_viewport_size({"width": width, "height": 1000})
                    assert await page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth + 1"
                    ), width
                    await page.screenshot(
                        path=str(out / f"viewport-{width}.png"), full_page=True
                    )
                checks.append(
                    "desktop/768px/390px layout without horizontal page overflow"
                )

                # Exogenous disturbances: declare a real schedule in the browser editor, then
                # prove the kernel applies it, conserves the destroyed goods and round-trips it.
                await page.set_viewport_size({"width": 1440, "height": 1050})
                await page.get_by_test_id("scenario-name").fill(
                    "Disturbance acceptance"
                )
                await page.get_by_test_id("horizon").fill("3")
                scheduled = await click_operation("new-scenario", "scenario_create")
                assert (
                    scheduled["revision"] == 1
                    and scheduled["spec"]["disturbances"] == []
                )
                # Wait for the create's own refresh to settle; a later edit must not be
                # overwritten by the post-response reload of the form.
                await expect(page.get_by_test_id("save-scenario")).to_be_disabled()
                await expect(page.get_by_test_id("disturbance-count")).to_have_text("0")
                await expect(page.get_by_test_id("disturbance-empty")).to_be_visible()
                await page.get_by_test_id("disturbance-add").click()
                await page.get_by_test_id("disturbance-tick-0").fill("2")
                await page.get_by_test_id("disturbance-kind-0").select_option(
                    "demand_spike"
                )
                await page.get_by_test_id("disturbance-amount-0").fill("3")
                await page.get_by_test_id("disturbance-add").click()
                await page.get_by_test_id("disturbance-tick-1").fill("3")
                await page.get_by_test_id("disturbance-kind-1").select_option(
                    "supplier_loss"
                )
                await page.get_by_test_id("disturbance-amount-1").fill("40")
                await expect(page.get_by_test_id("disturbance-count")).to_have_text("2")
                schedule = [
                    {"tick": 2, "kind": "demand_spike", "amount": 3},
                    {"tick": 3, "kind": "supplier_loss", "amount": 40},
                ]
                stored = await click_operation("save-scenario", "scenario_update")
                await expect(page.get_by_test_id("save-scenario")).to_be_disabled()
                assert stored["revision"] == 2, stored
                assert stored["spec"]["disturbances"] == schedule, stored["spec"]
                # The editor converges on the saved revision (its own refresh or the next poll).
                # Wait for that before editing again, otherwise the convergence overwrites the edit.
                await expect(page.get_by_test_id("disturbance-count")).to_have_text("2")
                await expect(page.get_by_test_id("disturbance-tick-1")).to_have_value(
                    "3"
                )
                # A row that falls outside the horizon is refused visibly and never sent.
                await page.get_by_test_id("horizon").fill("2")
                await expect(page.get_by_test_id("disturbance-errors")).to_contain_text(
                    "周期须为"
                )
                await page.get_by_test_id("save-scenario").click()
                await expect(page.get_by_test_id("error-banner")).to_contain_text(
                    "外生扰动未通过校验"
                )
                await page.get_by_role("button", name="关闭错误").click()
                await page.get_by_test_id("horizon").fill("3")
                await expect(page.get_by_test_id("disturbance-errors")).to_be_hidden()
                # Discard the local edits the way an operator would: the saved schedule must
                # reload into the editor and the forward run only uses the saved revision.
                await page.get_by_role("button", name="放弃修改，读取最新版本").click()
                await expect(page.get_by_test_id("save-scenario")).to_be_disabled()
                await expect(page.get_by_test_id("disturbance-count")).to_have_text("2")
                await expect(page.get_by_test_id("disturbance-tick-1")).to_have_value(
                    "3"
                )
                assert (await op("scenario_list"))["items"]
                await page.get_by_test_id("run-name").fill("Disturbance run")
                _, disturbed = await run("run-forward", "run_forward")
                assert disturbed["trajectory"]["rule_version"] == "supply-chain.v2"
                assert disturbed["provenance"]["rule_version"] == "supply-chain.v2"
                final = disturbed["trajectory"]["final_state"]
                assert final["lost"] == 40, final
                assert final["shortage"] == 3, final
                assert final["delivered"] + final["shortage"] == 3 * 4 + 3
                events = [
                    event
                    for frame in disturbed["trajectory"]["frames"]
                    for event in frame["events"]
                ]
                assert any(
                    "disturbance demand_spike at tick 2: demand 4 -> 7" in e
                    for e in events
                )
                assert any("declared 40, lost 40, stock 40 -> 0" in e for e in events)
                await expect(page.get_by_test_id("disturbance-legend")).to_be_visible()
                await expect(page.get_by_test_id("disturbance-marker-2")).to_have_count(
                    1
                )
                await expect(page.get_by_test_id("disturbance-marker-3")).to_have_count(
                    1
                )
                await page.get_by_test_id("timeline-slider").fill("3")
                await expect(page.get_by_test_id("state-lost")).to_have_text("40")
                exported = await op("branch_export", id=disturbed["id"])
                assert exported["branch"]["spec"]["disturbances"] == schedule
                reimported = await op("branch_import", bundle=exported)
                assert reimported["spec"]["disturbances"] == schedule
                assert reimported["trajectory"] == disturbed["trajectory"]
                # The schedule editor is the widest new control; it must not break narrow layouts.
                for width in (768, 390):
                    await page.set_viewport_size({"width": width, "height": 1000})
                    assert await page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth + 1"
                    ), width
                checks.append(
                    "browser declares a real disturbance schedule, runs it and round-trips it"
                )
                assert not errors, errors
                checks.append("no uncaught browser JavaScript errors")
                return {
                    "checks": checks,
                    "api_mcp_operation_count": len(names),
                    "search_expanded": search["search"]["expanded"],
                    "goal_final_state": plan["trajectory"]["final_state"],
                    "browser": browser.version,
                    "artifacts": str(out),
                }
            except Exception:
                await page.screenshot(path=str(out / "failure.png"), full_page=True)
                (out / "failure.txt").write_text(
                    await page.locator("body").inner_text()
                )
                raise
            finally:
                await browser.close()


def main():
    if not (ROOT / "web/dist/index.html").is_file():
        raise SystemExit("Build the real web assets first: npm --prefix web run build")
    out = Path(tempfile.mkdtemp(prefix="tianji-browser-"))
    token = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    print(f"Browser artifacts: {out}", flush=True)
    with (out / "server.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tianji_lab",
                "serve",
                "--port",
                str(port),
                "--data-dir",
                str(out / "data"),
            ],
            cwd=ROOT / "backend",
            env={**os.environ, "TIANJI_TOKEN": token},
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 15
            with httpx.Client(timeout=1, trust_env=False) as client:
                while True:
                    assert server.poll() is None, (
                        f"Service exited; inspect {out / 'server.log'}"
                    )
                    try:
                        if client.get(url + "/health").is_success:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "Service did not become healthy"
                    time.sleep(0.05)
            report = asyncio.run(acceptance(url, token, out))
            (out / "report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False)
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
