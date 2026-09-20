import { afterEach, describe, expect, it, vi } from "vitest";
import { Api, ApiError, schemaAt, schemaFields } from "./api";
import type { ActionProposal, Capability, VisionRequest } from "./api";

afterEach(() => vi.unstubAllGlobals());

// Pure unit fixtures; no fake HTTP backend or synthetic product state.
describe("actor proposal transport", () => {
  it("posts only the saved observation ID and returns the actual proposal", async () => {
    const proposal: ActionProposal = {
      actor_id: "retailer-a",
      role: "retailer",
      action: "order_standard",
      observation_hash: "observation-hash",
      policy_id: "local.test.v1",
    };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              name: "actor_propose",
              mutating: false,
              input_schema: {},
              description: "",
            },
          ]),
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true, data: proposal })),
      );
    vi.stubGlobal("fetch", fetch);
    try {
      const api = new Api("test-only");
      await api.catalog();
      expect(
        await api.op("actor_propose", { observation_id: "saved-id" }),
      ).toEqual(proposal);
      expect(fetch).toHaveBeenCalledTimes(2);
      const [url, request] = fetch.mock.calls[1];
      expect(url).toBe("/api/operations/actor_propose");
      expect(request.method).toBe("POST");
      expect(JSON.parse(request.body)).toEqual({
        arguments: { observation_id: "saved-id" },
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

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

describe("nested capability schemas", () => {
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
});

// Transport-only fixtures: never mounted as product data or used by browser checks.
describe("shared analysis API transport", () => {
  const request: VisionRequest = {
    vision: "transport test",
    horizon: "ten years",
    perspective: "public interest",
    constraints: "",
  };
  function setup(name: string, mutating = false) {
    const capability: Capability = {
      name,
      mutating,
      description: "",
      input_schema: {},
    };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([capability])));
    vi.stubGlobal("fetch", fetch);
    return { api: new Api("test-only-token"), fetch, capability };
  }
  it("authenticates catalog and read operations without adding a request ID", async () => {
    const { api, fetch, capability } = setup("analysis_stats");
    const stats = {
      saved_analyses: 0,
      nodes: 0,
      paths: 0,
      scope: "saved_analyses_only",
      architecture: "single_model_single_call",
    };
    fetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, data: stats })),
    );
    expect(await api.catalog()).toEqual([capability]);
    expect(await api.op("analysis_stats", {})).toEqual(stats);
    expect(fetch.mock.calls[0][0]).toBe("/api/capabilities");
    const [url, init] = fetch.mock.calls[1];
    expect(url).toBe("/api/operations/analysis_stats");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ arguments: {} });
    for (const [, init] of fetch.mock.calls) {
      expect(init.headers).toEqual({
        Authorization: "Bearer test-only-token",
        "Content-Type": "application/json",
      });
    }
  });
  it("uses server mutation metadata to assign a fresh request ID to each save", async () => {
    const { api, fetch } = setup("vision_save", true);
    const draft = {
      request,
      plan: {
        title: "transport fixture",
        interpretation: "",
        assumptions: [],
        tensions: [],
        nodes: [],
        paths: [],
      },
      model: "test-only",
      generated_at: "2026-01-01T00:00:00Z",
      grounding: "model_hypothesis" as const,
    };
    fetch.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({ ok: true, data: { id: "saved-test", draft } }),
        ),
    );
    await api.catalog();
    for (let i = 0; i < 2; i++) {
      expect(await api.op("vision_save", { draft })).toEqual({
        id: "saved-test",
        draft,
      });
    }
    const bodies = fetch.mock.calls
      .slice(1)
      .map(([, init]) => JSON.parse(init.body));
    for (const body of bodies) {
      expect(body).toEqual({
        arguments: { draft },
        request_id: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
        ),
      });
    }
    expect(bodies[0].request_id).not.toBe(bodies[1].request_id);
  });
  it("refuses an operation absent from the catalog without sending it", async () => {
    const { api, fetch } = setup("vision_list");
    await api.catalog();
    await expect(api.op("vision_generate", request)).rejects.toMatchObject({
      code: "CAPABILITY_MISSING",
      status: 404,
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("surfaces catalog authentication errors and never enables operations", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: { code: "UNAUTHORIZED", message: "令牌无效" },
        }),
        { status: 401 },
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const api = new Api("test-only");
    await expect(api.catalog()).rejects.toMatchObject({
      code: "UNAUTHORIZED",
      message: "令牌无效",
      status: 401,
    });
    await expect(api.op("vision_list", {})).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each([400, 200])(
    "propagates structured operation errors at HTTP %s",
    async (status) => {
      const { api, fetch } = setup("vision_generate");
      fetch.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: false,
            error: { code: "MODEL_ERROR", message: "模型不可用" },
          }),
          { status },
        ),
      );
      await api.catalog();
      await expect(api.op("vision_generate", request)).rejects.toMatchObject({
        code: "MODEL_ERROR",
        message: "模型不可用",
        status,
      });
    },
  );
  it("does not accept a success envelope with a failed HTTP status", async () => {
    const { api, fetch } = setup("vision_list");
    fetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true, data: { items: [] } }), {
        status: 503,
      }),
    );
    await api.catalog();
    await expect(api.op("vision_list", {})).rejects.toMatchObject({
      code: "HTTP_ERROR",
      status: 503,
    });
  });
  it("reports non-JSON operation responses rather than returning data", async () => {
    const { api, fetch } = setup("vision_generate");
    fetch.mockResolvedValueOnce(
      new Response("upstream unavailable", { status: 502 }),
    );
    await api.catalog();
    await expect(api.op("vision_generate", request)).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      status: 502,
    });
  });
  it("forwards cancellation to fetch and preserves the abort rejection", async () => {
    const { api, fetch } = setup("vision_generate");
    const controller = new AbortController();
    const aborted = new DOMException("test cancellation", "AbortError");
    fetch.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          expect(init.signal).toBe(controller.signal);
          init.signal!.addEventListener("abort", () => reject(aborted), {
            once: true,
          });
        }),
    );
    await api.catalog();
    const pending = api.op("vision_generate", request, controller.signal);
    controller.abort();
    await expect(pending).rejects.toBe(aborted);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      arguments: request,
    });
  });
});
