import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  actionLabel,
  disturbanceLabel,
  frameAtTick,
  isTerminal,
  schemaAt,
  schemaFields,
} from "./api";
import type { Branch, Capability, Frame, Job } from "./api";
import App, { disturbanceErrors } from "./App";

// Pure unit fixtures; no fake HTTP backend or synthetic product state.
describe("capability-driven forms", () => {
  const catalog: Capability[] = [
    {
      name: "scenario_create",
      description: "",
      mutating: true,
      input_schema: {
        properties: { spec: { $ref: "#/$defs/Scenario" } },
        $defs: {
          Scenario: {
            properties: {
              horizon: { type: "integer", minimum: 1, maximum: 10 },
            },
          },
        },
      },
    },
  ];
  it("resolves nested schema references and retains validation limits", () => {
    expect(schemaFields(catalog, "scenario_create", "spec")).toEqual({
      horizon: { type: "integer", minimum: 1, maximum: 10 },
    });
  });
  it("returns no invented fields for an unavailable capability", () => {
    expect(schemaFields(catalog, "missing", "spec")).toEqual({});
  });
  it("supports direct inline field schemas", () => {
    expect(
      schemaFields(
        [
          {
            ...catalog[0],
            input_schema: {
              properties: {
                goal: {
                  properties: { min_cash: { type: "integer", minimum: 0 } },
                },
              },
            },
          },
        ],
        "scenario_create",
        "goal",
      ),
    ).toEqual({ min_cash: { type: "integer", minimum: 0 } });
  });
});

describe("trajectory and job presentation", () => {
  it("uses actual ticks rather than frame indices", () => {
    const first = { state: { tick: 3 }, action: "initial" } as Frame;
    const later = { state: { tick: 7 }, action: "wait" } as Frame;
    const branch = { trajectory: { frames: [first, later] } } as Branch;
    expect(frameAtTick(branch, 7)).toBe(later);
    expect(frameAtTick(branch, 0)).toBe(first);
  });
  it.each([
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
  ] as Job["status"][])("recognizes %s as terminal", (status) => {
    expect(isTerminal(status)).toBe(true);
  });
  it.each(["queued", "running"] as Job["status"][])(
    "does not treat %s as completed",
    (status) => {
      expect(isTerminal(status)).toBe(false);
    },
  );
  it("labels the complete supported action space", () => {
    expect(Object.keys(actionLabel).sort()).toEqual([
      "initial",
      "order_express",
      "order_standard",
      "wait",
    ]);
  });
});

describe("exogenous disturbance schedule", () => {
  it("labels both disturbance kinds in Chinese", () => {
    expect(disturbanceLabel).toEqual({
      demand_spike: "需求激增",
      supplier_loss: "供应损失",
    });
  });
  it("resolves the nested item bounds published by the capability schema", () => {
    const catalog: Capability[] = [
      {
        name: "scenario_create",
        description: "",
        mutating: true,
        input_schema: {
          properties: { spec: { $ref: "#/$defs/Scenario" } },
          $defs: {
            Scenario: {
              properties: {
                disturbances: {
                  type: "array",
                  maxItems: 10,
                  items: { $ref: "#/$defs/Disturbance" },
                },
              },
            },
            Disturbance: {
              properties: {
                tick: { type: "integer", minimum: 1, maximum: 10 },
                amount: { type: "integer", minimum: 1, maximum: 200 },
              },
            },
          },
        },
      },
    ];
    expect(
      schemaAt(catalog, "scenario_create", ["spec", "disturbances"])?.maxItems,
    ).toBe(10);
    expect(
      schemaAt(catalog, "scenario_create", [
        "spec",
        "disturbances",
        "[]",
        "amount",
      ]),
    ).toEqual({ type: "integer", minimum: 1, maximum: 200 });
    expect(
      schemaAt(catalog, "scenario_create", ["spec", "missing", "[]"]),
    ).toBeUndefined();
  });
  it("accepts a bounded, distinct schedule", () => {
    expect(
      disturbanceErrors(
        [
          { tick: 1, kind: "demand_spike", amount: 5 },
          { tick: 3, kind: "supplier_loss", amount: 40 },
        ],
        5,
        200,
      ),
    ).toEqual([]);
  });
  it("blocks a tick beyond the horizon and reports the offending row", () => {
    const errors = disturbanceErrors(
      [{ tick: 6, kind: "supplier_loss", amount: 10 }],
      5,
      200,
    );
    expect(errors).toHaveLength(1);
    expect(errors[0]).toContain("第 1 条");
    expect(errors[0]).toContain("1–5");
  });
  it("caps a demand spike tighter than a supplier loss", () => {
    expect(
      disturbanceErrors(
        [{ tick: 2, kind: "demand_spike", amount: 21 }],
        5,
        200,
      )[0],
    ).toContain("1–20");
    expect(
      disturbanceErrors(
        [{ tick: 2, kind: "supplier_loss", amount: 150 }],
        5,
        200,
      ),
    ).toEqual([]);
    expect(
      disturbanceErrors(
        [{ tick: 2, kind: "supplier_loss", amount: 250 }],
        5,
        200,
      )[0],
    ).toContain("1–200");
  });
  it("rejects a duplicated tick and kind", () => {
    const errors = disturbanceErrors(
      [
        { tick: 2, kind: "demand_spike", amount: 5 },
        { tick: 2, kind: "demand_spike", amount: 6 },
      ],
      5,
      200,
    );
    expect(errors).toHaveLength(1);
    expect(errors[0]).toContain("第 2 条");
  });
});

describe("disconnected application", () => {
  it("renders the real shell and contract controls without fabricated results", () => {
    const html = renderToStaticMarkup(createElement(App));
    for (const id of [
      "token-input",
      "connect-button",
      "run-forward",
      "run-backward",
      "fork-branch",
      "branch-list",
      "export-branch",
      "import-bundle",
      "job-status",
    ]) {
      expect(html).toContain(`data-testid="${id}"`);
    }
    expect(html).toContain("双向世界推演实验室");
    expect(html).toContain("规则模型 · 虚构供应链");
    expect(html).toContain("尚无推演分支");
    expect(html).not.toContain('data-testid="comparison-result"');
  });
});
