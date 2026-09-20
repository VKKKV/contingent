import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
// QueryObserver disables browser polling during SSR. Exercise its browser path
// without adding a DOM dependency to this controller-only test suite.
vi.hoisted(() => vi.stubGlobal("window", {}));
import { focusManager, onlineManager } from "@tanstack/query-core";
import { ApiError, type Api, type Capability } from "./api";
import {
  ANALYSIS_POLL_MS,
  ANALYSIS_SELECTION_KEY,
  AnalysisSession,
  emptyAnalysisRequest,
} from "./analysisSession";
import type { AnalysisRun } from "./analysisTypes";

const names = ["analysis_start", "analysis_get", "analysis_list", "job_cancel"];
const capabilities = (allowed = names): Capability[] =>
  allowed.map((name) => ({
    name,
    description: "",
    input_schema: {},
    mutating: name === "analysis_start" || name === "job_cancel",
  }));
function run(
  id = "run-1",
  status: AnalysisRun["status"] = "running",
): AnalysisRun {
  return {
    id,
    status,
    schema_version: "tianji.analysis.v1",
    request: emptyAnalysisRequest(),
    budget: {
      max_calls: 8,
      max_seconds: 60,
      max_output_tokens: 1000,
      max_tasks: 8,
      max_revision_depth: 1,
    },
    created_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    tasks: [],
    nodes: [],
    edges: [],
    candidates: [],
    summary: "",
    unresolved: [],
    calls: 0,
    reserved_output_tokens: 0,
    duration_ms: 0,
    error: null,
    architecture: "bounded_same_model_agents",
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
let session: AnalysisSession;
let op: ReturnType<typeof vi.fn>;
let catalog: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("window", {});
  const storage = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
  catalog = vi.fn().mockResolvedValue(capabilities());
  op = vi
    .fn()
    .mockImplementation(async (name: string, args: { id?: string }) => {
      if (name === "analysis_list") return { items: [] };
      if (name === "analysis_start")
        return {
          id: "run-1",
          kind: "analysis_start",
          status: "queued",
          result: null,
          error: null,
        };
      return run(args.id);
    });
  session = new AnalysisSession(
    () => ({ catalog, op }) as unknown as Pick<Api, "catalog" | "op">,
  );
  session.start();
});
afterEach(() => {
  session.stop();
  focusManager.setFocused(undefined);
  onlineManager.setOnline(true);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function ready() {
  await session.connect("test-token");
  session.edit({ vision: "  test intent  " });
}

describe("AnalysisSession", () => {
  it("connects through the catalog, restores selection and polls only active canonical runs", async () => {
    sessionStorage.setItem(ANALYSIS_SELECTION_KEY, "saved");
    session.start();
    await session.connect("test-token");
    expect(catalog).toHaveBeenCalledWith(expect.any(AbortSignal));
    expect(session.getSnapshot()).toMatchObject({
      connected: true,
      selectedId: "saved",
      run: { id: "saved", status: "running" },
    });
    op.mockResolvedValueOnce(run("saved", "succeeded"));
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS);
    expect(session.getSnapshot().run?.status).toBe("succeeded");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("creates with a UUID, reads the canonical run, refreshes the list and polls", async () => {
    await ready();
    await session.create();
    expect(op.mock.calls.map((call) => call[0])).toEqual([
      "analysis_list",
      "analysis_start",
      "analysis_get",
      "analysis_list",
    ]);
    const start = op.mock.calls[1];
    expect(start[1].request.vision).toBe("test intent");
    expect(start[3]).toMatch(/^[0-9a-f-]{36}$/);
    expect(session.getSnapshot()).toMatchObject({
      pendingStart: false,
      selectedId: "run-1",
      run: { status: "running" },
      busy: null,
    });
    expect(sessionStorage.getItem("tianji-analysis-create")).toBeNull();
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS);
    expect(
      op.mock.calls.filter((call) => call[0] === "analysis_get"),
    ).toHaveLength(2);
  });

  it.each([
    new ApiError("analysis_disabled", "Analysis disabled", 503),
    new ApiError("validation_error", "Invalid input", 422),
    new ApiError("unauthorized", "Authentication required", 401),
  ])("unlocks editing after definite rejection ($code)", async (error) => {
    await ready();
    op.mockRejectedValueOnce(error);
    await session.create();
    expect(session.getSnapshot()).toMatchObject({
      busy: null,
      pendingStart: false,
    });
    expect(sessionStorage.getItem("tianji-analysis-create")).toBeNull();
    expect(session.getSnapshot().error).not.toContain("创建可能已提交");
    session.edit({ vision: "corrected intent" });
    expect(session.getSnapshot().request.vision).toBe("corrected intent");
    const firstId = op.mock.calls[1][3];
    await session.create();
    expect(op.mock.calls[2][3]).not.toBe(firstId);
  });

  it.each([
    new TypeError("Failed to fetch"),
    new ApiError("HTTP_ERROR", "Server failure", 500),
    new ApiError("HTTP_ERROR", "Gateway unavailable", 503),
    new ApiError("INVALID_RESPONSE", "Malformed response", 200),
    new ApiError("HTTP_ERROR", "Request timed out", 408),
  ])(
    "preserves pending intent and UUID on ambiguous outcome ($message)",
    async (error) => {
      await ready();
      op.mockRejectedValueOnce(error);
      await session.create();
      const first = op.mock.calls[1];
      expect(session.getSnapshot()).toMatchObject({
        pendingStart: true,
        busy: null,
      });
      session.edit({ vision: "must not replace pending intent" });
      expect(session.getSnapshot().request.vision).toBe("  test intent  ");
      expect(
        JSON.parse(sessionStorage.getItem("tianji-analysis-create")!).requestId,
      ).toBe(first[3]);
      await session.create();
      expect(op.mock.calls[2][3]).toBe(first[3]);
      expect(op.mock.calls[2][1]).toEqual(first[1]);
      expect(session.getSnapshot().pendingStart).toBe(false);
    },
  );

  it.each([undefined, null, "", "   ", 42])(
    "preserves the creation UUID when a job response has an invalid id (%s)",
    async (id) => {
      await ready();
      op.mockResolvedValueOnce({ id, kind: "analysis_start" });
      await session.create();
      const original = op.mock.calls.find(
        (call) => call[0] === "analysis_start",
      )!;
      expect(session.getSnapshot()).toMatchObject({
        pendingStart: true,
        busy: null,
        selectedId: "",
        run: null,
      });
      expect(session.getSnapshot().error).toContain("创建可能已提交");
      expect(
        op.mock.calls.filter((call) => call[0] === "analysis_get"),
      ).toHaveLength(0);
      expect(
        JSON.parse(sessionStorage.getItem("tianji-analysis-create")!).requestId,
      ).toBe(original[3]);
      await session.create();
      const starts = op.mock.calls.filter(
        (call) => call[0] === "analysis_start",
      );
      expect(starts[1][3]).toBe(original[3]);
      expect(starts[1][1]).toEqual(original[1]);
      expect(session.getSnapshot().run?.id).toBe("run-1");
    },
  );

  it("supersedes a pre-cancellation list read so a terminal project cannot regress to running", async () => {
    await ready();
    await session.load("run-1");
    const stale = deferred<{ items: AnalysisRun[] }>();
    op.mockReturnValueOnce(stale.promise);
    const listing = session.reload();
    const signal = op.mock.calls.at(-1)![2] as AbortSignal;
    op.mockImplementation(async (name: string) =>
      name === "analysis_list"
        ? { items: [run("run-1", "cancelled")] }
        : run("run-1", "cancelled"),
    );
    await session.cancel();
    stale.resolve({ items: [run("run-1", "running")] });
    await listing;
    expect(session.getSnapshot().run?.status).toBe("cancelled");
    expect(session.getSnapshot().items[0]?.status).toBe("cancelled");
    expect(signal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels through job_cancel then confirms with analysis_get, not the mutation response", async () => {
    await ready();
    await session.load("run-1");
    op.mockClear();
    op.mockResolvedValueOnce({ id: "run-1", status: "cancelled" });
    const readback = deferred<AnalysisRun>();
    op.mockReturnValueOnce(readback.promise);
    const cancelling = session.cancel();
    await Promise.resolve();
    expect(op.mock.calls.map((call) => call[0])).toEqual([
      "job_cancel",
      "analysis_get",
    ]);
    expect(op.mock.calls[0]).toEqual([
      "job_cancel",
      { id: "run-1" },
      expect.any(AbortSignal),
      "analysis-cancel-run-1",
    ]);
    expect(session.getSnapshot().run?.status).toBe("running");
    expect(session.getSnapshot().notice).toBe("");
    readback.resolve(run("run-1", "cancelled"));
    await cancelling;
    expect(session.getSnapshot().run?.status).toBe("cancelled");
    expect(session.getSnapshot().notice).toContain("确认取消");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("ignores stale selection results even when the transport ignores abort", async () => {
    await ready();
    const old = deferred<AnalysisRun>();
    op.mockReturnValueOnce(old.promise);
    const loading = session.load("old");
    const signal = op.mock.calls.at(-1)![2] as AbortSignal;
    await session.load("new");
    expect(signal.aborted).toBe(true);
    old.resolve(run("old"));
    await loading;
    expect(session.getSnapshot().run?.id).toBe("new");
    expect(vi.getTimerCount()).toBe(1);
  });

  it("aborts outstanding reads and ignores late results after unmount", async () => {
    await ready();
    const pending = deferred<AnalysisRun>();
    op.mockReturnValueOnce(pending.promise);
    const loading = session.load("old");
    const signal = op.mock.calls.at(-1)![2] as AbortSignal;
    session.stop();
    pending.resolve(run("old"));
    await loading;
    expect(signal.aborted).toBe(true);
    expect(session.getSnapshot()).toMatchObject({
      connected: false,
      run: null,
      busy: null,
    });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("restores an ambiguous pending creation across unmount with the same UUID", async () => {
    await ready();
    op.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await session.create();
    const original = op.mock.calls[1];
    session.stop();
    session = new AnalysisSession(
      () => ({ catalog, op }) as unknown as Pick<Api, "catalog" | "op">,
    );
    session.start();
    expect(session.getSnapshot()).toMatchObject({
      pendingStart: true,
      request: { vision: "test intent" },
    });
    await session.connect("test-token");
    await session.create();
    const starts = op.mock.calls.filter((call) => call[0] === "analysis_start");
    expect(starts).toHaveLength(2);
    expect(starts[1][3]).toBe(original[3]);
    expect(starts[1][1]).toEqual(original[1]);
  });

  it.each([
    null,
    [],
    { requestId: "fixture", request: null },
    ...[undefined, null, 42, {}, "", "   ", "x".repeat(129)].map(
      (requestId) => ({
        requestId,
        request: { ...emptyAnalysisRequest(), vision: "intent" },
      }),
    ),
    ...["", " \n\t"].map((vision) => ({
      requestId: "fixture",
      request: { ...emptyAnalysisRequest(), vision },
    })),
    ...["vision", "horizon", "perspective", "constraints"].flatMap((field) =>
      [undefined, null, 42].map((value) => ({
        requestId: "fixture",
        request: {
          ...emptyAnalysisRequest(),
          vision: "intent",
          [field]: value,
        },
      })),
    ),
  ])(
    "discards malformed pending storage without locking editing (%j)",
    async (value) => {
      sessionStorage.setItem("tianji-analysis-create", JSON.stringify(value));
      session.start();
      expect(session.getSnapshot().pendingStart).toBe(false);
      expect(sessionStorage.getItem("tianji-analysis-create")).toBeNull();
      await ready();
      session.edit({ vision: "recovered intent" });
      await session.create();
      expect(
        op.mock.calls.find((call) => call[0] === "analysis_start")?.[1],
      ).toEqual({
        request: { ...emptyAnalysisRequest(), vision: "recovered intent" },
      });
      expect(session.getSnapshot().selectedId).toBe("run-1");
    },
  );

  it("discards invalid JSON pending storage", () => {
    sessionStorage.setItem("tianji-analysis-create", "{");
    session.start();
    expect(session.getSnapshot().pendingStart).toBe(false);
    expect(sessionStorage.getItem("tianji-analysis-create")).toBeNull();
    session.edit({ vision: "editable" });
    expect(session.getSnapshot().request.vision).toBe("editable");
  });

  it("restores complete intent without rewriting its request ID or payload", async () => {
    const pending = {
      requestId: "legacy-request-key",
      request: {
        vision: " original intent ",
        horizon: " custom horizon ",
        perspective: " custom perspective ",
        constraints: " constraints ",
      },
    };
    sessionStorage.setItem("tianji-analysis-create", JSON.stringify(pending));
    session.start();
    session.edit({ vision: "must not overwrite" });
    expect(session.getSnapshot()).toMatchObject({
      pendingStart: true,
      request: pending.request,
    });
    await session.connect("test-token");
    await session.create();
    expect(op).toHaveBeenCalledWith(
      "analysis_start",
      { request: pending.request },
      expect.any(AbortSignal),
      pending.requestId,
    );
  });

  it("preserves live ambiguous intent when tab storage is corrupt or inaccessible", async () => {
    await ready();
    op.mockRejectedValueOnce(new TypeError("lost response"));
    await session.create();
    const original = op.mock.calls.find(
      (call) => call[0] === "analysis_start",
    )!;
    sessionStorage.setItem("tianji-analysis-create", "{}");
    session.stop();
    session.start();
    expect(session.getSnapshot().pendingStart).toBe(true);
    vi.stubGlobal("sessionStorage", {
      getItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
      setItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
      removeItem: () => {
        throw new DOMException("blocked", "SecurityError");
      },
    });
    session.stop();
    session.start();
    await session.connect("test-token");
    session.edit({ vision: "must not overwrite" });
    await session.create();
    const starts = op.mock.calls.filter((call) => call[0] === "analysis_start");
    expect(starts).toHaveLength(2);
    expect(starts[1][1]).toEqual(original[1]);
    expect(starts[1][3]).toBe(original[3]);
  });

  it("ignores a late creation response after unmount without losing the retry UUID", async () => {
    await ready();
    const pending = deferred<unknown>();
    op.mockReturnValueOnce(pending.promise);
    const creating = session.create();
    const saved = sessionStorage.getItem("tianji-analysis-create");
    session.stop();
    pending.resolve({ id: "late", kind: "analysis_start" });
    await creating;
    expect(session.getSnapshot()).toMatchObject({
      connected: false,
      run: null,
      selectedId: "",
      pendingStart: true,
    });
    expect(sessionStorage.getItem("tianji-analysis-create")).toBe(saved);
    expect(op.mock.calls.map((call) => call[0])).toEqual([
      "analysis_list",
      "analysis_start",
    ]);
  });

  it("does not reconnect from a late catalog after unmount", async () => {
    const pending = deferred<Capability[]>();
    catalog.mockReturnValueOnce(pending.promise);
    const connecting = session.connect("test-token");
    session.stop();
    pending.resolve(capabilities());
    await connecting;
    expect(session.getSnapshot().connected).toBe(false);
    expect(op).not.toHaveBeenCalled();
  });

  it.each(["analysis_start", "analysis_get", "analysis_list"])(
    "does not create without required capability %s",
    async (missing) => {
      catalog.mockResolvedValue(
        capabilities(names.filter((name) => name !== missing)),
      );
      await ready();
      op.mockClear();
      await session.create();
      expect(op).not.toHaveBeenCalled();
      expect(session.getSnapshot().pendingStart).toBe(false);
    },
  );

  it("deduplicates concurrent list and selected-run reads", async () => {
    await ready();
    op.mockClear();
    const list = deferred<{ items: AnalysisRun[] }>();
    op.mockReturnValueOnce(list.promise);
    const firstList = session.reload();
    const secondList = session.reload();
    expect(op).toHaveBeenCalledTimes(1);
    list.resolve({ items: [run("saved")] });
    await Promise.all([firstList, secondList]);
    expect(session.getSnapshot().items[0].id).toBe("saved");
    const pending = deferred<AnalysisRun>();
    op.mockReturnValueOnce(pending.promise);
    const first = session.load("same");
    const second = session.load("same");
    expect(op).toHaveBeenCalledTimes(2);
    pending.resolve(run("same", "succeeded"));
    await Promise.all([first, second]);
    expect(session.getSnapshot()).toMatchObject({
      busy: null,
      run: { id: "same" },
    });
  });

  it("clears connection cache and ignores late list/run reads after a token change", async () => {
    await ready();
    await session.load("same");
    const oldList = deferred<{ items: AnalysisRun[] }>();
    const oldRun = deferred<AnalysisRun>();
    op.mockReturnValueOnce(oldList.promise).mockReturnValueOnce(oldRun.promise);
    const listing = session.reload();
    const loading = session.load("same");
    const signals = op.mock.calls
      .slice(-2)
      .map((call) => call[2] as AbortSignal);
    const reconnecting = session.connect("other-token");
    expect(session.getSnapshot()).toMatchObject({
      run: null,
      items: [],
      connected: false,
    });
    expect(signals.every((signal) => signal.aborted)).toBe(true);
    await reconnecting;
    oldList.resolve({ items: [run("private-old")] });
    oldRun.resolve({ ...run("same"), summary: "private-old" });
    await Promise.all([listing, loading]);
    expect(catalog).toHaveBeenCalledTimes(2);
    expect(session.getSnapshot()).toMatchObject({
      connected: true,
      items: [],
      run: { id: "same", summary: "" },
    });
    // Cache identity is local to this controller, and never includes bearer secrets.
    const queries = session["queries"].getQueryCache().getAll();
    expect(queries.map((query) => query.queryKey)).toEqual([
      ["catalog"],
      ["list"],
      ["run", "same"],
    ]);
    session.disconnect();
    expect(session["queries"].getQueryCache().getAll()).toEqual([]);
  });

  it("does not share cache between simultaneous session instances", async () => {
    await ready();
    await session.load("same");
    const otherOp = vi.fn(async (name: string) =>
      name === "analysis_list"
        ? { items: [] }
        : { ...run("same", "succeeded"), summary: "other" },
    );
    const other = new AnalysisSession(
      () =>
        ({ catalog, op: otherOp }) as unknown as Pick<Api, "catalog" | "op">,
    );
    other.start();
    try {
      await other.connect("other-token");
      expect(other.getSnapshot().run?.summary).toBe("other");
      expect(session.getSnapshot().run?.summary).toBe("");
      other.disconnect();
      expect(session.getSnapshot().run?.id).toBe("same");
    } finally {
      other.stop();
    }
  });

  it("ignores a stale catalog when a replacement connection succeeds", async () => {
    const stale = deferred<Capability[]>();
    catalog.mockReturnValueOnce(stale.promise);
    const connecting = session.connect("old-token");
    const signal = catalog.mock.calls[0][0] as AbortSignal;
    await session.connect("new-token");
    stale.resolve([]);
    await connecting;
    expect(signal.aborted).toBe(true);
    expect(session.getSnapshot()).toMatchObject({
      connected: true,
      catalog: capabilities(),
    });
    expect(sessionStorage.getItem("tianji-token")).toBe("new-token");
  });

  it("never retries creation or refetches on focus/reconnect", async () => {
    await ready();
    op.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await session.create();
    const intent = sessionStorage.getItem("tianji-analysis-create");
    const calls = op.mock.calls.length;
    focusManager.setFocused(false);
    onlineManager.setOnline(false);
    focusManager.setFocused(true);
    onlineManager.setOnline(true);
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS * 10);
    expect(op).toHaveBeenCalledTimes(calls);
    expect(catalog).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("tianji-analysis-create")).toBe(intent);
    await session.load("terminal");
    op.mockResolvedValueOnce(run("terminal", "succeeded"));
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS);
    const settledCalls = op.mock.calls.length;
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    onlineManager.setOnline(false);
    onlineManager.setOnline(true);
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS * 10);
    expect(op).toHaveBeenCalledTimes(settledCalls);
  });

  it("reports offline read errors without hanging and resumes polling only after explicit recovery", async () => {
    await ready();
    await session.load("run-1");
    onlineManager.setOnline(false);
    op.mockRejectedValueOnce(new TypeError("offline test-token"));
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS);
    expect(session.getSnapshot()).toMatchObject({
      busy: null,
      run: { id: "run-1" },
    });
    expect(session.getSnapshot().error).toContain("已暂停读取");
    expect(session.getSnapshot().error).not.toContain("test-token");
    const calls = op.mock.calls.length;
    onlineManager.setOnline(true);
    focusManager.setFocused(true);
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS * 10);
    expect(op).toHaveBeenCalledTimes(calls);
    await session.load("run-1");
    expect(session.getSnapshot()).toMatchObject({
      busy: null,
      error: "",
      run: { status: "running" },
    });
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS);
    expect(op).toHaveBeenCalledTimes(calls + 2);
  });

  it("allows explicit catalog/list recovery while the browser reports offline", async () => {
    onlineManager.setOnline(false);
    catalog.mockRejectedValueOnce(new TypeError("offline"));
    await session.connect("test-token");
    expect(session.getSnapshot()).toMatchObject({
      connected: false,
      busy: null,
      error: "offline",
    });
    await session.connect("test-token");
    op.mockRejectedValueOnce(new TypeError("offline"));
    await session.reload();
    expect(session.getSnapshot()).toMatchObject({
      listBusy: false,
      listError: "offline",
    });
    await session.reload();
    expect(session.getSnapshot()).toMatchObject({
      listBusy: false,
      listError: "",
      connected: true,
    });
  });

  it("rejects mismatched canonical identities and stops polling", async () => {
    await ready();
    op.mockResolvedValueOnce(run("wrong"));
    await session.load("expected");
    expect(session.getSnapshot()).toMatchObject({ run: null, busy: null });
    expect(session.getSnapshot().error).toContain("标识或版本不一致");
    const calls = op.mock.calls.length;
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS * 10);
    expect(op).toHaveBeenCalledTimes(calls);
  });

  it("supersedes a pre-creation list read when refreshing committed work", async () => {
    await ready();
    const stale = deferred<{ items: AnalysisRun[] }>();
    op.mockReturnValueOnce(stale.promise);
    const listing = session.reload();
    const signal = op.mock.calls.at(-1)![2] as AbortSignal;
    op.mockImplementation(async (name: string, args: { id?: string }) => {
      if (name === "analysis_start")
        return { id: "created", kind: "analysis_start" };
      if (name === "analysis_list") return { items: [run("created")] };
      return run(args.id);
    });
    await session.create();
    expect(signal.aborted).toBe(true);
    stale.resolve({ items: [] });
    await listing;
    expect(session.getSnapshot().items.map((item) => item.id)).toEqual([
      "created",
    ]);
  });

  it("refreshes after creation even if the first list fetch has not completed", async () => {
    const stale = deferred<{ items: AnalysisRun[] }>();
    op.mockReturnValueOnce(stale.promise);
    const connecting = session.connect("test-token");
    await vi.advanceTimersByTimeAsync(0);
    expect(session.getSnapshot().connected).toBe(true);
    const signal = op.mock.calls[0][2] as AbortSignal;
    session.edit({ vision: "new intent" });
    op.mockImplementation(async (name: string, args: { id?: string }) => {
      if (name === "analysis_start")
        return { id: "created", kind: "analysis_start" };
      if (name === "analysis_list") return { items: [run("created")] };
      return run(args.id);
    });
    await session.create();
    expect(signal.aborted).toBe(true);
    stale.resolve({ items: [] });
    await connecting;
    expect(session.getSnapshot().items.map((item) => item.id)).toEqual([
      "created",
    ]);
  });

  it("never retries a failed cancellation or resumes reads implicitly", async () => {
    await ready();
    await session.load("run-1");
    op.mockRejectedValueOnce(new TypeError("cancel response lost"));
    await session.cancel();
    expect(session.getSnapshot().error).toContain("取消状态未确认");
    const calls = op.mock.calls.length;
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    onlineManager.setOnline(false);
    onlineManager.setOnline(true);
    await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_MS * 10);
    expect(op).toHaveBeenCalledTimes(calls);
    expect(session.getSnapshot().run?.status).toBe("running");
  });

  it("does not cancel when job_cancel is absent", async () => {
    catalog.mockResolvedValue(
      capabilities(names.filter((name) => name !== "job_cancel")),
    );
    await ready();
    await session.load("run-1");
    op.mockClear();
    await session.cancel();
    expect(op).not.toHaveBeenCalled();
  });
});
