"""Real Chromium + HTTP + MCP acceptance against an isolated temporary laboratory.

Run from the root: uv run --project backend --group browser python scripts/check-lab-browser.py
No mock responses, provider calls, production data or fixed port required.
"""

import asyncio
import json
import os
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

ROOT = Path(__file__).resolve().parents[1]


async def acceptance(url, token, out):
    checks = []
    async with httpx.AsyncClient(
        base_url=url, trust_env=False, timeout=15, headers={"Authorization": f"Bearer {token}"}
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
                assert await page.get_by_test_id("initial-inventory").get_attribute("max") == "100"
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
                    branch = result[branch_key] if branch_key == "branch" else result[branch_key][0]
                    await expect(page.get_by_test_id(f"branch-{branch['id']}")).to_have_attribute(
                        "aria-pressed", "true", timeout=30000
                    )
                    return result, branch

                original_id = await page.get_by_test_id("scenario-select").input_value()
                await page.get_by_test_id("scenario-name").fill("Browser acceptance")
                created = await click_operation("new-scenario", "scenario_create")
                await expect(page.get_by_test_id("scenario-select")).to_have_value(created["id"])
                await page.get_by_test_id("scenario-name").fill("Browser acceptance saved")
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
                checks.append("browser forward trajectory, actual time cursor and shortage display")

                await page.get_by_test_id("run-name").fill("Goal plan")
                search, plan = await run("run-backward", "run_backward", "branches")
                assert search["search"]["status"] == "found" and plan["trajectory"]["goal_met"]
                await expect(page.get_by_test_id("job-status")).to_contain_text("找到可行候选")
                await page.get_by_test_id("compare-select").select_option(baseline["id"])
                compared = await click_operation("compare-branches", "branch_compare")
                assert compared["delta"]["shortage"] == 12
                await expect(page.get_by_test_id("comparison-result")).to_be_visible()
                checks.append("browser goal search, same-model verified candidates and comparison")

                await page.get_by_test_id(f"branch-{baseline['id']}").click()
                await expect(page.get_by_test_id("timeline-slider")).to_have_value("0")
                await page.get_by_test_id("timeline-slider").fill("2")
                await expect(page.get_by_test_id("current-tick")).to_have_text("T2")
                await page.get_by_test_id("fork-action-2").select_option("order_express")
                await page.get_by_test_id("run-name").fill("Counterfactual")
                _, fork = await run("fork-branch", "branch_fork")
                assert fork["fork_tick"] == 2 and fork["parent_id"] == baseline["id"]
                assert (
                    fork["trajectory"]["frames"][0]["state"]
                    == baseline["trajectory"]["frames"][2]["state"]
                )
                assert await op("branch_get", id=baseline["id"]) == baseline
                checks.append("browser recorded-tick fork, changed action, unchanged parent")

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
                    await page.get_by_test_id("import-bundle").set_input_files(bundle_path)
                imported_response = await event.value
                assert imported_response.ok, await imported_response.text()
                imported = (await imported_response.json())["data"]
                assert imported["trajectory"] == fork["trajectory"]
                await expect(page.get_by_test_id(f"branch-{imported['id']}")).to_have_attribute(
                    "aria-pressed", "true"
                )
                checks.append("browser real JSON download, upload and semantic replay import")

                workspace_id = await page.get_by_test_id("workspace-id").inner_text()
                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "tianji_lab", "mcp", "--url", url],
                    cwd=str(ROOT / "backend"),
                    env={**os.environ, "TIANJI_TOKEN": token},
                )
                async with stdio_client(params) as streams:
                    async with ClientSession(*streams) as session:
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
                        await expect(page.get_by_test_id(f"branch-{plan['id']}")).to_have_attribute(
                            "aria-pressed", "true"
                        )
                        await expect(page.get_by_test_id("timeline-slider")).to_have_value("3")
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
                        await expect(page.get_by_test_id("comparison-result")).to_be_visible()
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
                        predicate=lambda r: r.url.endswith("/api/operations/workspace_get"),
                    )
                await expect(page.get_by_test_id(f"branch-{plan['id']}")).to_have_attribute(
                    "aria-pressed", "true"
                )
                await expect(page.get_by_test_id("timeline-slider")).to_have_value("3")
                checks.append(
                    "reconnect preserves MCP workspace instead of replaying old job selections"
                )

                await page.get_by_test_id("scenario-name").fill("Unsaved human draft")
                current = next(
                    s for s in (await op("scenario_list"))["items"] if s["id"] == saved["id"]
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
                await expect(page.get_by_test_id("error-banner")).to_contain_text("版本冲突")
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
                incomplete = await finish(await click_operation("run-backward", "run_backward"))
                assert incomplete["search"]["status"] == "budget_exhausted"
                await expect(page.get_by_test_id("job-status")).to_contain_text(
                    "预算耗尽，尚不能判定无解"
                )
                await page.get_by_test_id("max-nodes").fill("5000")
                await page.get_by_test_id("min-inventory").fill("100")
                impossible = await finish(await click_operation("run-backward", "run_backward"))
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
                await expect(page.get_by_test_id("error-banner")).to_contain_text("有效 JSON")
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
                await expect(page.get_by_test_id("job-status")).to_contain_text("已取消")
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
                    await page.screenshot(path=str(out / f"viewport-{width}.png"), full_page=True)
                checks.append("desktop/768px/390px layout without horizontal page overflow")

                # Exogenous disturbances: declare a real schedule in the browser editor, then
                # prove the kernel applies it, conserves the destroyed goods and round-trips it.
                await page.set_viewport_size({"width": 1440, "height": 1050})
                await page.get_by_test_id("scenario-name").fill("Disturbance acceptance")
                await page.get_by_test_id("horizon").fill("3")
                scheduled = await click_operation("new-scenario", "scenario_create")
                assert scheduled["revision"] == 1 and scheduled["spec"]["disturbances"] == []
                # Wait for the create's own refresh to settle; a later edit must not be
                # overwritten by the post-response reload of the form.
                await expect(page.get_by_test_id("save-scenario")).to_be_disabled()
                await expect(page.get_by_test_id("disturbance-count")).to_have_text("0")
                await expect(page.get_by_test_id("disturbance-empty")).to_be_visible()
                await page.get_by_test_id("disturbance-add").click()
                await page.get_by_test_id("disturbance-tick-0").fill("2")
                await page.get_by_test_id("disturbance-kind-0").select_option("demand_spike")
                await page.get_by_test_id("disturbance-amount-0").fill("3")
                await page.get_by_test_id("disturbance-add").click()
                await page.get_by_test_id("disturbance-tick-1").fill("3")
                await page.get_by_test_id("disturbance-kind-1").select_option("supplier_loss")
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
                # A row that falls outside the horizon is refused visibly and never sent.
                await page.get_by_test_id("horizon").fill("2")
                await expect(page.get_by_test_id("disturbance-errors")).to_contain_text("周期须为")
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
                await expect(page.get_by_test_id("disturbance-tick-1")).to_have_value("3")
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
                    event for frame in disturbed["trajectory"]["frames"] for event in frame["events"]
                ]
                assert any("disturbance demand_spike at tick 2: demand 4 -> 7" in e for e in events)
                assert any("declared 40, lost 40, stock 40 -> 0" in e for e in events)
                await expect(page.get_by_test_id("disturbance-legend")).to_be_visible()
                await expect(page.get_by_test_id("disturbance-marker-2")).to_have_count(1)
                await expect(page.get_by_test_id("disturbance-marker-3")).to_have_count(1)
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
                (out / "failure.txt").write_text(await page.locator("body").inner_text())
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
                    assert server.poll() is None, f"Service exited; inspect {out / 'server.log'}"
                    try:
                        if client.get(url + "/health").is_success:
                            break
                    except httpx.HTTPError:
                        pass
                    assert time.monotonic() < deadline, "Service did not become healthy"
                    time.sleep(0.05)
            report = asyncio.run(acceptance(url, token, out))
            (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
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
