import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Api } from "./api";
import type { Branch, Capability } from "./api";
import DirectorPanel from "./DirectorPanel";

const catalog: Capability[] = [
  "observation_create",
  "observation_get",
  "adjudication_create",
  "adjudication_get",
  "adjudication_list",
].map((name) => ({
  name,
  input_schema: {},
  description: "",
  mutating: name.endsWith("create"),
}));
const branch = {
  id: "branch-test",
  name: "冻结分支",
  scenario_revision: 2,
  trajectory: { frames: [{ state: { tick: 3 } }] },
} as Branch;
function tag(html: string, testId: string) {
  return (
    html.match(new RegExp(`<[^>]*data-testid="${testId}"[^>]*>`))?.[0] ?? ""
  );
}
describe("director panel controls", () => {
  it("provides the basic accessible controls and explicit director/preview boundaries", () => {
    const html = renderToStaticMarkup(
      createElement(DirectorPanel, {
        api: new Api("test-only"),
        branch,
        tick: 3,
        catalog,
        disabled: false,
      }),
    );
    for (const id of [
      "director-panel",
      "observation-role",
      "observation-actor",
      "observation-create",
      "adjudication-action",
      "adjudication-referee",
      "adjudication-submit",
      "adjudication-history",
      "adjudication-reload",
    ]) {
      expect(tag(html, id)).not.toBe("");
    }
    expect(html).toContain("仅供导演审计");
    expect(html).toContain("不写入分支、不自动分叉");
    expect(html).toContain("不是已认证身份");
    expect(html).toContain("manual.director.v1");
    expect(html).toContain("branch-test · T3 · 冻结场景 rev 2");
    expect(html).toContain('<option value="supplier">');
    expect(html).toContain('<option value="order_express">');
    expect(tag(html, "observation-role")).not.toContain("disabled");
    expect(tag(html, "observation-actor")).toContain("required");
    expect(tag(html, "observation-create")).toContain("disabled");
    expect(tag(html, "adjudication-submit")).toContain("disabled");
    expect(tag(html, "adjudication-reload")).not.toContain("disabled");
    expect(html).not.toContain('data-testid="adjudication-result"');
    expect(html).not.toContain('data-testid="observation-result"');
  });
  it.each([
    { api: null, branch, tick: 3, disabled: false },
    { api: new Api("test-only"), branch: null, tick: 3, disabled: false },
    { api: new Api("test-only"), branch, tick: 2, disabled: false },
    { api: new Api("test-only"), branch, tick: 3, disabled: true },
  ])(
    "disables controls when disconnected, loading, busy or not at a recorded tick",
    (props) => {
      const html = renderToStaticMarkup(
        createElement(DirectorPanel, { ...props, catalog }),
      );
      for (const id of [
        "observation-role",
        "observation-actor",
        "observation-create",
        "adjudication-action",
        "adjudication-referee",
        "adjudication-submit",
        "adjudication-reload",
      ]) {
        expect(tag(html, id)).toContain("disabled");
      }
      expect(html).not.toContain('data-testid="adjudication-result"');
    },
  );
  it("explains missing capabilities and disables server actions", () => {
    const html = renderToStaticMarkup(
      createElement(DirectorPanel, {
        api: new Api("test-only"),
        branch,
        tick: 3,
        catalog: [],
        disabled: false,
      }),
    );
    expect(html).toContain('data-testid="director-capability-missing"');
    expect(tag(html, "observation-create")).toContain("disabled");
    expect(tag(html, "adjudication-submit")).toContain("disabled");
    expect(tag(html, "adjudication-reload")).toContain("disabled");
  });
  it("never sends HTTP for an operation absent from the runtime catalog", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    try {
      const api = new Api("test-only");
      await expect(
        api.op("observation_create", {
          branch_id: "b",
          tick: 0,
          actor_id: "a",
          role: "retailer",
        }),
      ).rejects.toMatchObject({ code: "CAPABILITY_MISSING" });
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
