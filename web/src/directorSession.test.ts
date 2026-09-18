import { describe, expect, it, vi } from "vitest";
import type {
  ActionProposal,
  Api,
  Capability,
  Operations,
  SavedAdjudication,
  SavedObservation,
  State,
} from "./api";
import { DirectorSession } from "./directorSession";
import type { DirectorContext } from "./directorSession";

// Isolated transport fixtures, never used by the product or browser smoke tests.
const catalog: Capability[] = [
  "observation_create",
  "observation_get",
  "actor_propose",
  "adjudication_create",
  "adjudication_get",
  "adjudication_list",
].map((name) => ({
  name,
  description: "",
  input_schema: {},
  mutating: name.endsWith("create"),
}));
const state: State = {
  tick: 1,
  inventory: 3,
  cash: 20,
  supplier_stock: 15,
  delivered: 2,
  shortage: 0,
  spent: 0,
  lost: 0,
  shipments: [],
};
const observation: SavedObservation = {
  id: "observation-a",
  observation: {
    actor_id: "retailer-a",
    role: "retailer",
    tick: 1,
    context: {
      branch_id: "branch-a",
      scenario_revision: 1,
      spec_hash: "spec-hash",
    },
    projection: {
      tick: 1,
      inventory: 3,
      cash: 20,
      delivered: 2,
      shortage: 0,
      spent: 0,
      shipments: [],
    },
    projection_hash: "projection-hash",
    observation_hash: "observation-hash",
  },
};
const proposal: ActionProposal = {
  actor_id: observation.observation.actor_id,
  role: observation.observation.role,
  action: "order_express",
  observation_hash: observation.observation.observation_hash,
  policy_id: "local.model.test.v1",
};
const receipt: SavedAdjudication = {
  id: "receipt-a",
  observation_id: observation.id,
  record: {
    record_id: "record-a",
    adjudicator_id: "referee-a",
    proposal_actor_id: "retailer-a",
    role: "retailer",
    policy_id: "manual.director.v1",
    pre_state_hash: "pre-hash",
    observation_hash: "observation-hash",
    action: "wait",
    status: "accepted",
    reason: "accepted by authoritative kernel",
    post_state_hash: "post-hash",
    record_hash: "record-hash",
    context: observation.observation.context,
  },
  next_state: { ...state, tick: 2 },
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function setup(overrides: Partial<DirectorContext> = {}) {
  const transport = vi.fn(
    async (
      name: keyof Operations,
      _args?: Operations[keyof Operations][0],
    ): Promise<unknown> => {
      if (name === "adjudication_list") return { items: [] };
      if (name === "actor_propose") return proposal;
      if (name.startsWith("observation_")) return observation;
      return receipt;
    },
  );
  // A typed operation facade over test-only controllable deferred responses.
  const api: Pick<Api, "op"> = {
    op: <K extends keyof Operations>(name: K, args: Operations[K][0]) =>
      transport(name, ...[args]) as Promise<Operations[K][1]>,
  };
  const context: DirectorContext = {
    api,
    catalog,
    branchId: "branch-a",
    tick: 1,
    actorId: "retailer-a",
    role: "retailer",
    ...overrides,
  };
  const session = new DirectorSession(context);
  session.start();
  return { session, context, transport };
}

// A session is the panel's immutable branch/tick/identity scope. React's layout
// cleanup stops it before starting the replacement. These tests exercise the
// actual async implementation with deferred operations using Vitest's Node setup.
describe("director observation and adjudication", () => {
  it("reads observation back and binds the manual proposal to its server identity/hash", async () => {
    const { session, transport } = setup();
    await session.observe();
    expect(transport).toHaveBeenCalledWith("observation_create", {
      branch_id: "branch-a",
      tick: 1,
      actor_id: "retailer-a",
      role: "retailer",
    });
    expect(transport).toHaveBeenCalledWith("observation_get", {
      id: observation.id,
    });
    expect(session.getSnapshot().observation).toEqual(observation);
    await session.adjudicate("wait", "referee-a");
    expect(transport).toHaveBeenCalledWith("adjudication_create", {
      observation_id: observation.id,
      adjudicator_id: "referee-a",
      proposal: {
        actor_id: "retailer-a",
        role: "retailer",
        action: "wait",
        observation_hash: "observation-hash",
        policy_id: "manual.director.v1",
      },
    });
    expect(transport).toHaveBeenCalledWith("adjudication_get", {
      id: receipt.id,
    });
    expect(session.getSnapshot().result).toEqual(receipt);
    expect(transport.mock.calls.at(-1)?.[0]).toBe("adjudication_list");
    expect(transport.mock.calls.map(([name]) => name)).not.toContain(
      "branch_fork",
    );
    session.stop();
  });
  it("renders only readback results, and reloads history rather than appending write responses", async () => {
    const { session, transport } = setup();
    await session.observe();
    const readback = deferred<SavedAdjudication>();
    const oldImplementation = transport.getMockImplementation()!;
    transport.mockImplementation((name) =>
      name === "adjudication_get" ? readback.promise : oldImplementation(name),
    );
    const pending = session.adjudicate("wait", "referee-a");
    await Promise.resolve();
    expect(session.getSnapshot().result).toBeNull();
    expect(session.getSnapshot().busy).toBe(true);
    readback.resolve(receipt);
    await pending;
    expect(session.getSnapshot().result).toEqual(receipt);
    expect(session.getSnapshot().history).toEqual([]);
    session.stop();
  });
  it("shows actual rejection reason and unchanged state without a fallback action", async () => {
    const { session, transport } = setup();
    await session.observe();
    const rejected: SavedAdjudication = {
      ...receipt,
      record: {
        ...receipt.record,
        action: "order_express",
        status: "rejected",
        reason: "kernel rejected proposal: insufficient cash",
        post_state_hash: receipt.record.pre_state_hash,
      },
      next_state: state,
    };
    transport
      .mockResolvedValueOnce(rejected)
      .mockResolvedValueOnce(rejected)
      .mockResolvedValueOnce({ items: [rejected] });
    await session.adjudicate("order_express", "referee-a");
    expect(session.getSnapshot().result).toEqual(rejected);
    expect(session.getSnapshot().history).toEqual([rejected]);
    expect(transport).toHaveBeenCalledWith(
      "adjudication_create",
      expect.objectContaining({
        proposal: expect.objectContaining({ action: "order_express" }),
      }),
    );
    session.stop();
  });
  it("blocks duplicate same-context writes synchronously, even before a render", async () => {
    const { session, transport } = setup();
    const held = deferred<SavedObservation>();
    transport.mockReturnValueOnce(held.promise);
    const first = session.observe();
    await session.observe();
    expect(
      transport.mock.calls.filter(([name]) => name === "observation_create"),
    ).toHaveLength(1);
    held.resolve(observation);
    await first;
    const adjudication = deferred<SavedAdjudication>();
    transport.mockReturnValueOnce(adjudication.promise);
    const second = session.adjudicate("wait", "referee-a");
    await session.adjudicate("order_standard", "referee-a");
    await session.observe();
    expect(
      transport.mock.calls.filter(([name]) => name === "adjudication_create"),
    ).toHaveLength(1);
    adjudication.resolve(receipt);
    await second;
    session.stop();
  });
  it.each([
    { branchId: "branch-b" },
    { tick: 2 },
    { actorId: "retailer-b" },
    { role: "supplier" as const },
    { api: null },
  ])(
    "discards a deferred observation after selection/identity/disconnect: %j",
    async (change) => {
      const { session, context, transport } = setup();
      const held = deferred<SavedObservation>();
      transport.mockReturnValueOnce(held.promise);
      const pending = session.observe();
      session.stop();
      const replacement = new DirectorSession({ ...context, ...change });
      replacement.start();
      held.resolve(observation);
      await pending;
      expect(session.getSnapshot().observation).toBeNull();
      expect(replacement.getSnapshot().observation).toBeNull();
      expect(
        transport.mock.calls.filter(([name]) => name === "observation_get"),
      ).toHaveLength(0);
      replacement.stop();
    },
  );
  it("does not resurrect an old response after leaving and returning to the same context", async () => {
    const { session, context, transport } = setup();
    const held = deferred<SavedObservation>();
    transport.mockReturnValueOnce(held.promise);
    const pending = session.observe();
    session.stop();
    const replacement = new DirectorSession(context);
    replacement.start();
    await replacement.observe();
    held.resolve({ ...observation, id: "old-response" });
    await pending;
    expect(replacement.getSnapshot().observation?.id).toBe(observation.id);
    replacement.stop();
  });
  it.each(["adjudication_create", "adjudication_get"] as const)(
    "discards deferred %s and errors after scope changes",
    async (operation) => {
      const { session, context, transport } = setup();
      await session.observe();
      const held = deferred<SavedAdjudication>();
      const oldImplementation = transport.getMockImplementation()!;
      transport.mockImplementation((name) =>
        name === operation ? held.promise : oldImplementation(name),
      );
      const pending = session.adjudicate("wait", "referee-a");
      await Promise.resolve();
      session.stop();
      const replacement = new DirectorSession({ ...context, tick: 2 });
      replacement.start();
      held.reject(new Error("old-scope transport failure"));
      await pending;
      expect(replacement.getSnapshot().result).toBeNull();
      expect(replacement.getSnapshot().error).toBe("");
      expect(session.getSnapshot().result).toBeNull();
      replacement.stop();
    },
  );
  it("rejects readback identity mismatch rather than displaying foreign projection", async () => {
    const { session, transport } = setup();
    transport.mockResolvedValueOnce(observation).mockResolvedValueOnce({
      ...observation,
      observation: { ...observation.observation, tick: 9 },
    });
    await session.observe();
    expect(session.getSnapshot().observation).toBeNull();
    expect(session.getSnapshot().error).toContain("不一致");
    session.stop();
  });
  it("retains server errors and can recover without inventing an accepted result", async () => {
    const { session, transport } = setup();
    transport.mockRejectedValueOnce(new Error("record_limit"));
    await session.observe();
    expect(session.getSnapshot()).toMatchObject({
      busy: false,
      observation: null,
      result: null,
      error: "record_limit",
    });
    await session.observe();
    transport.mockRejectedValueOnce(new Error("read failed"));
    await session.adjudicate("wait", "referee-a");
    expect(session.getSnapshot().result).toBeNull();
    expect(session.getSnapshot().error).toBe("read failed");
    expect(transport.mock.calls.at(-1)?.[0]).toBe("adjudication_list");
    session.stop();
  });
  it("requires nonempty labels, a distinct referee, and published capabilities", async () => {
    const { session, transport } = setup({ catalog: [] });
    await session.observe();
    await session.adjudicate("wait", "referee-a");
    await session.reloadHistory();
    expect(transport).not.toHaveBeenCalled();
    session.stop();
    const empty = setup({ actorId: " " });
    await empty.session.observe();
    expect(empty.transport.mock.calls.map(([name]) => name)).toEqual([
      "adjudication_list",
    ]);
    empty.session.stop();
    const valid = setup();
    await valid.session.observe();
    await valid.session.adjudicate("wait", "retailer-a");
    await valid.session.adjudicate("wait", " ");
    expect(valid.transport.mock.calls.map(([name]) => name)).not.toContain(
      "adjudication_create",
    );
    valid.session.stop();
  });
});

describe("explicit local model proposals", () => {
  it("only proposes on request using the saved observation, without adjudication or a fork", async () => {
    const { session, transport } = setup();
    await session.propose();
    await session.observe();
    expect(transport.mock.calls.map(([name]) => name)).not.toContain(
      "actor_propose",
    );
    transport.mockClear();
    await session.propose();
    expect(transport.mock.calls).toEqual([
      ["actor_propose", { observation_id: observation.id }],
    ]);
    expect(session.getSnapshot()).toMatchObject({
      proposal,
      action: proposal.action,
      result: null,
      busy: false,
    });
    session.clearResult();
    await session.adjudicate(proposal.action, "referee-a");
    expect(transport).toHaveBeenCalledWith("adjudication_create", {
      observation_id: observation.id,
      adjudicator_id: "referee-a",
      proposal,
    });
    session.stop();
  });
  it("keeps model provenance only while the proposed action is unchanged", async () => {
    const { session, transport } = setup();
    await session.observe();
    await session.propose();
    session.setAction(proposal.action);
    expect(session.getSnapshot().proposal).toEqual(proposal);
    session.setAction("wait");
    expect(session.getSnapshot().proposal).toBeNull();
    session.setAction(proposal.action);
    await session.adjudicate(session.getSnapshot().action, "referee-a");
    expect(transport).toHaveBeenCalledWith(
      "adjudication_create",
      expect.objectContaining({
        proposal: { ...proposal, policy_id: "manual.director.v1" },
      }),
    );
    session.stop();
  });
  it("does not attribute a directly submitted different action to the model", async () => {
    const { session, transport } = setup();
    await session.observe();
    await session.propose();
    await session.adjudicate("wait", "referee-a");
    expect(transport).toHaveBeenCalledWith(
      "adjudication_create",
      expect.objectContaining({
        proposal: {
          ...proposal,
          action: "wait",
          policy_id: "manual.director.v1",
        },
      }),
    );
    session.stop();
  });
  it("clears the proposal when creating a new observation", async () => {
    const { session } = setup();
    await session.observe();
    await session.propose();
    const pending = session.observe();
    expect(session.getSnapshot()).toMatchObject({
      observation: null,
      proposal: null,
      action: "wait",
    });
    await pending;
    expect(session.getSnapshot().proposal).toBeNull();
    session.stop();
  });
  it("blocks duplicate requests and edits while the model request is pending", async () => {
    const { session, transport } = setup();
    await session.observe();
    transport.mockClear();
    const held = deferred<ActionProposal>();
    transport.mockReturnValueOnce(held.promise);
    const pending = session.propose();
    await session.propose();
    await session.observe();
    await session.adjudicate("wait", "referee-a");
    session.setAction("order_standard");
    expect(transport).toHaveBeenCalledTimes(1);
    expect(session.getSnapshot()).toMatchObject({
      busy: true,
      action: "wait",
      proposal: null,
    });
    held.resolve(proposal);
    await pending;
    expect(session.getSnapshot().proposal).toEqual(proposal);
    session.stop();
  });
  it.each([
    { branchId: "branch-b" },
    { tick: 2 },
    { actorId: "retailer-b" },
    { role: "supplier" as const },
    { api: null },
    {},
  ])(
    "discards late proposals and errors after leaving the context: %j",
    async (change) => {
      for (const fail of [false, true]) {
        const { session, context, transport } = setup();
        await session.observe();
        const held = deferred<ActionProposal>();
        transport.mockReturnValueOnce(held.promise);
        const pending = session.propose();
        session.stop();
        const replacement = new DirectorSession({ ...context, ...change });
        replacement.start();
        if (fail) held.reject(new Error("stale model error"));
        else held.resolve(proposal);
        await pending;
        for (const scope of [session, replacement]) {
          expect(scope.getSnapshot()).toMatchObject({
            proposal: null,
            action: "wait",
            error: "",
            busy: false,
          });
        }
        replacement.stop();
      }
    },
  );
  it("does not install an old proposal over a newer observation after session restart", async () => {
    const { session, transport } = setup();
    await session.observe();
    const held = deferred<ActionProposal>();
    transport.mockReturnValueOnce(held.promise);
    const pending = session.propose();
    session.stop();
    session.start();
    const newer = { ...observation, id: "observation-new" };
    transport.mockResolvedValueOnce(newer).mockResolvedValueOnce(newer);
    await session.observe();
    held.resolve(proposal);
    await pending;
    expect(session.getSnapshot()).toMatchObject({
      observation: newer,
      proposal: null,
      action: "wait",
      busy: false,
    });
    session.stop();
  });
  it.each([
    { actor_id: "other" },
    { role: "supplier" },
    { observation_hash: "other" },
    { policy_id: "" },
    { action: "unknown" },
  ])(
    "rejects mismatched or invalid model output without fallback: %j",
    async (change) => {
      const { session, transport } = setup();
      await session.observe();
      transport.mockResolvedValueOnce({ ...proposal, ...change });
      await session.propose();
      expect(session.getSnapshot()).toMatchObject({
        proposal: null,
        action: "wait",
        result: null,
        busy: false,
      });
      expect(session.getSnapshot().error).toContain("不一致或格式无效");
      session.stop();
    },
  );
  it("surfaces disabled-model errors and leaves manual adjudication independent", async () => {
    const { session, transport } = setup();
    await session.observe();
    transport.mockRejectedValueOnce(new Error("local model actor is disabled"));
    await session.propose();
    expect(session.getSnapshot()).toMatchObject({
      proposal: null,
      busy: false,
      error: "local model actor is disabled",
    });
    await session.adjudicate("wait", "referee-a");
    expect(session.getSnapshot().result).toEqual(receipt);
    session.stop();
  });
  it("does not call missing model capability or block the manual pipeline", async () => {
    const { session, transport } = setup({
      catalog: catalog.filter((c) => c.name !== "actor_propose"),
    });
    await session.observe();
    await session.propose();
    await session.adjudicate("wait", "referee-a");
    expect(transport.mock.calls.map(([name]) => name)).not.toContain(
      "actor_propose",
    );
    expect(session.getSnapshot().result).toEqual(receipt);
    session.stop();
  });
});

describe("persisted history generation guards", () => {
  it("restores history from the server on every new session", async () => {
    const { session, context, transport } = setup();
    session.stop();
    transport.mockResolvedValueOnce({ items: [receipt] });
    const restored = new DirectorSession(context);
    restored.start();
    await Promise.resolve();
    expect(restored.getSnapshot().history).toEqual([receipt]);
    expect(restored.getSnapshot().historyLoaded).toBe(true);
    restored.stop();
  });
  it("keeps the newest same-branch list when reload responses arrive out of order", async () => {
    const { session, transport } = setup();
    await Promise.resolve();
    const old = deferred<{ items: SavedAdjudication[] }>();
    const fresh = deferred<{ items: SavedAdjudication[] }>();
    transport
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise);
    const first = session.reloadHistory();
    const second = session.reloadHistory();
    fresh.resolve({ items: [receipt] });
    await second;
    old.resolve({ items: [] });
    await first;
    expect(session.getSnapshot().history).toEqual([receipt]);
    expect(session.getSnapshot().historyBusy).toBe(false);
    session.stop();
  });
  it("does not install old branch history or an old history error", async () => {
    const { session, context, transport } = setup();
    const held = deferred<{ items: SavedAdjudication[] }>();
    transport.mockReturnValueOnce(held.promise);
    const pending = session.reloadHistory();
    session.stop();
    const replacement = new DirectorSession({
      ...context,
      branchId: "branch-b",
    });
    replacement.start();
    held.reject(new Error("old history failure"));
    await pending;
    expect(replacement.getSnapshot().history).toEqual([]);
    expect(replacement.getSnapshot().historyError).toBe("");
    replacement.stop();
  });
  it("does not present history read failure as an empty successful list", async () => {
    const { session, transport } = setup();
    await Promise.resolve();
    transport.mockRejectedValueOnce(new Error("offline"));
    await session.reloadHistory();
    expect(session.getSnapshot().historyError).toBe("offline");
    expect(session.getSnapshot().historyBusy).toBe(false);
    session.stop();
  });
});
