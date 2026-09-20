import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type Api,
  type VisionDraft,
  type SavedVision,
  type Capability,
} from "./api";
import { layoutVision, validateVision } from "./visionGraph";
import { VisionSession } from "./visionSession";

const draft = (): VisionDraft => ({
  request: {
    vision: "测试目标",
    horizon: "未来十年",
    perspective: "公共利益与可协作的行动者",
    constraints: "",
  },
  model: "test-only",
  generated_at: "2026-01-01",
  grounding: "model_hypothesis",
  plan: {
    title: "测试",
    interpretation: "条件假设",
    assumptions: ["假设"],
    tensions: [],
    nodes: ["a", "b", "c", "d"].map((id, i) => ({
      id,
      stage: ([1, 2, 2, 3] as const)[i],
      title: id,
      actors: ["参与者"],
      action: "行动",
      mechanism: "机制",
      prerequisites: ["前提"],
      risks: ["风险"],
      signals: ["信号"],
    })),
    paths: [
      {
        id: "p1",
        title: "一",
        summary: "一",
        node_ids: ["a", "b", "d"],
        tradeoff: "代价",
      },
      {
        id: "p2",
        title: "二",
        summary: "二",
        node_ids: ["a", "c", "d"],
        tradeoff: "代价",
      },
    ],
  },
});
const catalog = [
  "vision_generate",
  "vision_save",
  "vision_get",
  "vision_list",
].map((name) => ({
  name,
  description: "",
  input_schema: {},
  mutating: name === "vision_save",
})) as Capability[];
function setup() {
  const op = vi.fn(async (name: string) =>
    name === "vision_list" ? { items: [] } : draft(),
  );
  const s = new VisionSession(() => ({
    catalog: async () => catalog,
    op: op as unknown as Api["op"],
  }));
  s.start();
  return { s, op };
}
afterEach(() => vi.unstubAllGlobals());

describe("vision graph", () => {
  it("lays out shared nodes once and highlights shared edges by path membership", () => {
    const d = draft();
    validateVision(d);
    const g = layoutVision(d.plan);
    expect(g.nodes).toHaveLength(5);
    expect(g.nodes.filter((n) => n.data.stage !== null)).toHaveLength(4);
    expect(g.edges.some((e) => e.data!.pathIds.length === 2)).toBe(true);
    expect(
      new Set(g.nodes.map((n) => `${n.position.x},${n.position.y}`)).size,
    ).toBe(5);
    for (const edge of g.edges) {
      const source = g.nodes.find((n) => n.id === edge.source)!;
      const target = g.nodes.find((n) => n.id === edge.target)!;
      expect(target.position.x).toBeGreaterThan(source.position.x);
    }
  });
  it("rejects orphan, subset, invalid references and cyclic stages", () => {
    for (const mutate of [
      (d: VisionDraft) => {
        d.plan.paths[1].node_ids = ["a", "d"];
      },
      (d: VisionDraft) => {
        d.plan.paths[0].node_ids = ["a", "missing"];
      },
      (d: VisionDraft) => {
        d.plan.nodes[1].stage = 1;
      },
      (d: VisionDraft) => {
        d.plan.nodes[0].actors = [];
      },
    ]) {
      const d = draft();
      mutate(d);
      expect(() => validateVision(d)).toThrow();
    }
  });
  it("does not collide with a model node named like the synthetic goal", () => {
    const d = draft();
    d.plan.nodes[0].id = "__vision_goal__";
    d.plan.paths.forEach((p) => (p.node_ids[0] = "__vision_goal__"));
    const g = layoutVision(d.plan);
    expect(g.goalId).not.toBe("__vision_goal__");
    expect(g.edges.every((e) => e.source !== e.target)).toBe(true);
  });
  it("switches path highlights without changing layout or duplicating shared nodes", () => {
    const d = draft();
    const first = layoutVision(d.plan, "p1", "b");
    const second = layoutVision(d.plan, "p2", "c");
    expect(first.nodes.map((n) => n.position)).toEqual(
      second.nodes.map((n) => n.position),
    );
    expect(second.nodes.filter((n) => n.selected).map((n) => n.id)).toEqual([
      "c",
    ]);
    expect(second.nodes.filter((n) => n.data.active).map((n) => n.id)).toEqual([
      "a",
      "c",
      "d",
    ]);
    expect(second.nodes.find((n) => n.id === "d")?.data.shared).toBe(true);
    expect(
      second.edges.filter((e) => e.className.includes("is-active")),
    ).toHaveLength(3);
    expect(
      second.nodes.find((n) => n.id === second.goalId)?.data.stage,
    ).toBeNull();
    expect(second.nodes.find((n) => n.id === second.goalId)?.selectable).toBe(
      false,
    );
  });
  it("keeps every node in bounds and non-overlapping for the maximum node count", () => {
    const d = draft();
    d.plan.nodes = Array.from({ length: 8 }, (_, i) => ({
      ...d.plan.nodes[0],
      id: `n${i}`,
      stage: (Math.floor(i / 2) + 1) as 1 | 2 | 3 | 4,
    }));
    d.plan.paths[0].node_ids = ["n0", "n2", "n4", "n6"];
    d.plan.paths[1].node_ids = ["n1", "n3", "n5", "n7"];
    validateVision(d);
    const { nodes } = layoutVision(d.plan);
    for (const [i, a] of nodes.entries()) {
      expect(a.position.x).toBeGreaterThanOrEqual(0);
      expect(a.position.y).toBeGreaterThanOrEqual(0);
      for (const b of nodes.slice(i + 1)) {
        expect(
          a.position.x + a.width <= b.position.x ||
            b.position.x + b.width <= a.position.x ||
            a.position.y + a.height <= b.position.y ||
            b.position.y + b.height <= a.position.y,
        ).toBe(true);
      }
    }
  });
});
describe("vision session", () => {
  it("supplies optional defaults and does not automatically save", async () => {
    const { s, op } = setup();
    await s.connect("test");
    s.edit({ vision: "测试目标", horizon: "", perspective: "" });
    await s.generate();
    expect(s.getSnapshot().draft).not.toBeNull();
    expect(op).toHaveBeenCalledWith(
      "vision_generate",
      draft().request,
      expect.any(AbortSignal),
    );
    expect(op.mock.calls.some((c) => c[0] === "vision_save")).toBe(false);
    s.stop();
  });
  it("drops generation after editing or disconnecting", async () => {
    for (const change of [
      (s: VisionSession) => s.edit({ vision: "新目标" }),
      (s: VisionSession) => s.disconnect(),
    ]) {
      const { s, op } = setup();
      await s.connect("test");
      s.edit({ vision: "测试目标" });
      let resolve!: (d: VisionDraft) => void;
      op.mockImplementationOnce(
        () =>
          new Promise((r) => {
            resolve = r as typeof resolve;
          }),
      );
      const pending = s.generate();
      change(s);
      resolve(draft());
      await pending;
      expect(s.getSnapshot().draft).toBeNull();
      s.stop();
    }
  });
  it("rejects a changed echoed perspective", async () => {
    const { s, op } = setup();
    await s.connect("test");
    s.edit({ vision: "测试目标" });
    const wrong = draft();
    wrong.request.perspective = "不同视角";
    op.mockResolvedValueOnce(wrong);
    await s.generate();
    expect(s.getSnapshot().draft).toBeNull();
    expect(s.getSnapshot().error).not.toBe("");
    s.stop();
  });
  it("saves only on request and reads the saved target", async () => {
    const { s, op } = setup();
    await s.connect("test");
    s.edit({ vision: "测试目标" });
    await s.generate();
    const saved = { id: "saved", created_at: "now", draft: draft() };
    op.mockResolvedValueOnce(saved as never)
      .mockResolvedValueOnce(saved as never)
      .mockResolvedValueOnce({ items: [] });
    await s.save();
    expect(s.getSnapshot().saved?.id).toBe("saved");
    expect(op).toHaveBeenCalledWith("vision_get", { id: "saved" });
    s.stop();
  });
  it("reuses the mutation request ID and draft after a committed response is lost", async () => {
    const writes: { request_id: string; arguments: { draft: VisionDraft } }[] =
      [];
    const records = new Map<string, SavedVision>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        if (url === "/api/capabilities")
          return { ok: true, json: async () => catalog };
        const envelope = JSON.parse(options!.body as string);
        let data: unknown;
        switch (url.split("/").at(-1)) {
          case "vision_generate":
            data = draft();
            break;
          case "vision_list":
            data = { items: [] };
            break;
          case "vision_save": {
            writes.push(envelope);
            if (!records.has(envelope.request_id))
              records.set(envelope.request_id, {
                id: "saved-once",
                created_at: "now",
                draft: envelope.arguments.draft,
              });
            if (writes.length === 1)
              throw new TypeError("response lost after commit");
            data = records.get(envelope.request_id);
            break;
          }
          case "vision_get":
            data = [...records.values()].find(
              (saved) => saved.id === envelope.arguments.id,
            );
            break;
          default:
            throw new Error(`Unexpected operation ${url}`);
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ ok: true, data }),
        };
      }),
    );
    const s = new VisionSession();
    s.start();
    try {
      await s.connect("test");
      s.edit(draft().request);
      await s.generate();
      await s.save();
      expect(s.getSnapshot().saved).toBeNull();
      expect(s.getSnapshot().error).toContain("保存可能已提交");
      // A retry uses the captured intent, not mutable references from the editor.
      s.getSnapshot().draft!.plan.title = "changed outside session";
      await s.save();
      expect(writes).toHaveLength(2);
      expect(writes[0].request_id).toMatch(/^[0-9a-f-]{36}$/);
      expect(writes[1]).toEqual(writes[0]);
      expect(records.size).toBe(1);
      expect(s.getSnapshot().saved?.draft).toEqual(draft());
    } finally {
      s.stop();
    }
  });

  it.each(["transport", "mismatch"])(
    "retries only readback when the saved ID is known (%s)",
    async (failure) => {
      const { s, op } = setup();
      try {
        await s.connect("test");
        s.edit(draft().request);
        await s.generate();
        const saved = { id: "saved", created_at: "now", draft: draft() };
        op.mockResolvedValueOnce(saved as never);
        if (failure === "transport")
          op.mockRejectedValueOnce(new TypeError("readback offline"));
        else op.mockResolvedValueOnce({ ...saved, id: "wrong" } as never);
        await s.save();
        expect(s.getSnapshot().saved).toBeNull();
        op.mockResolvedValueOnce(saved as never);
        await s.save();
        expect(
          op.mock.calls.filter((call) => call[0] === "vision_save"),
        ).toHaveLength(1);
        expect(
          op.mock.calls.filter((call) => call[0] === "vision_get"),
        ).toHaveLength(2);
        expect(s.getSnapshot().saved).toEqual(saved);
      } finally {
        s.stop();
      }
    },
  );

  it.each([undefined, null, "", "   ", 42])(
    "retains the save intent when a mutation returns an invalid ID (%s)",
    async (id) => {
      const { s, op } = setup();
      try {
        await s.connect("test");
        s.edit(draft().request);
        await s.generate();
        op.mockResolvedValueOnce({ id } as never);
        await s.save();
        expect(
          op.mock.calls.filter((call) => call[0] === "vision_get"),
        ).toHaveLength(0);
        const saved = { id: "saved", created_at: "now", draft: draft() };
        op.mockResolvedValueOnce(saved as never).mockResolvedValueOnce(
          saved as never,
        );
        await s.save();
        const writes = vi
          .mocked(op as unknown as Api["op"])
          .mock.calls.filter((call) => call[0] === "vision_save");
        expect(writes).toHaveLength(2);
        expect(writes[1][3]).toBe(writes[0][3]);
        expect(writes[1][1]).toEqual(writes[0][1]);
        expect(s.getSnapshot().saved).toEqual(saved);
      } finally {
        s.stop();
      }
    },
  );

  it("assigns a new save intent after editing and regenerating", async () => {
    const { s, op } = setup();
    try {
      await s.connect("test");
      s.edit(draft().request);
      await s.generate();
      op.mockRejectedValueOnce(new TypeError("lost reply"));
      await s.save();
      s.edit(draft().request);
      await s.generate();
      const saved = { id: "new", created_at: "now", draft: draft() };
      op.mockResolvedValueOnce(saved as never).mockResolvedValueOnce(
        saved as never,
      );
      await s.save();
      const writes = vi
        .mocked(op as unknown as Api["op"])
        .mock.calls.filter((call) => call[0] === "vision_save");
      expect(writes).toHaveLength(2);
      expect(writes[1][3]).not.toBe(writes[0][3]);
      expect(s.getSnapshot().saved).toEqual(saved);
    } finally {
      s.stop();
    }
  });

  it("does not restore an obsolete save after editing during readback", async () => {
    const { s, op } = setup();
    try {
      await s.connect("test");
      s.edit(draft().request);
      await s.generate();
      const saved = { id: "saved", created_at: "now", draft: draft() };
      let resolve!: (value: unknown) => void;
      const readback = new Promise((done) => {
        resolve = done;
      });
      op.mockResolvedValueOnce(saved as never).mockReturnValueOnce(
        readback as never,
      );
      const saving = s.save();
      await Promise.resolve();
      s.edit({ vision: "new intent" });
      resolve(saved);
      await saving;
      expect(s.getSnapshot()).toMatchObject({
        request: { vision: "new intent" },
        draft: null,
        saved: null,
        busy: null,
      });
    } finally {
      s.stop();
    }
  });

  it("shows real failures without fabricated result", async () => {
    const { s, op } = setup();
    await s.connect("secret");
    s.edit({ vision: "测试目标" });
    op.mockRejectedValueOnce(new Error("offline secret"));
    await s.generate();
    expect(s.getSnapshot().draft).toBeNull();
    expect(s.getSnapshot().error).not.toContain("secret");
    s.stop();
  });
});
