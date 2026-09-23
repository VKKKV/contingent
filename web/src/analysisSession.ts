import { QueryClient, QueryObserver } from "@tanstack/query-core";
import { Api, ApiError, type Capability, type VisionRequest } from "./api";
import {
  analysisActive,
  defaultResearchOptions,
  type ResearchOptions,
  type ResearchBudget,
  type AnalysisRun,
  type AnalysisSummary,
} from "./analysisTypes";

export const ANALYSIS_SELECTION_KEY = "tianji-analysis-id";
const PENDING_KEY = "tianji-analysis-create";
export const ANALYSIS_POLL_MS = 1500;
export const emptyAnalysisRequest = (): VisionRequest => ({
  vision: "",
  horizon: "未来十年",
  perspective: "公共利益与可协作的行动者",
  constraints: "",
});
export function tabRead(key: string) {
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
export function tabWrite(key: string, value: string) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    /* Storage may be disabled. */
  }
}
type Client = Pick<Api, "catalog" | "op">;
type StartOperation = "analysis_start" | "analysis_start_v2";
type Pending = { request: VisionRequest; requestId: string } & (
  | { operation?: "analysis_start"; research?: never }
  | { operation: "analysis_start_v2"; research: ResearchOptions }
);
const researchBounds: Record<keyof ResearchBudget, [number, number]> = {
  max_queries: [1, 3],
  max_pages: [1, 5],
  max_seconds: [5, 180],
  max_response_bytes: [1024, 1048576],
  max_total_bytes: [1024, 5242880],
};
function isResearch(value: unknown): value is ResearchOptions {
  if (!value || typeof value !== "object") return false;
  const { mode, budget } = value as Partial<ResearchOptions>;
  return (
    (mode === "online" || mode === "offline") &&
    !!budget &&
    Object.keys(value).every((key) => key === "mode" || key === "budget") &&
    Object.keys(budget).length === Object.keys(researchBounds).length &&
    Object.entries(researchBounds).every(([key, [min, max]]) => {
      const n = budget[key as keyof ResearchBudget];
      return Number.isInteger(n) && n >= min && n <= max;
    })
  );
}
function frozenResearch(value: ResearchOptions): ResearchOptions {
  return Object.freeze({
    mode: value.mode,
    budget: Object.freeze({ ...value.budget }),
  });
}
function freezePending(value: Pending): Pending {
  return Object.freeze({
    ...value,
    request: Object.freeze({ ...value.request }),
    ...(value.operation === "analysis_start_v2"
      ? { research: frozenResearch(value.research) }
      : {}),
  }) as Pending;
}
function isPending(value: unknown): value is Pending {
  if (!value || typeof value !== "object") return false;
  const { requestId, request, operation, research } = value as Partial<Pending>;
  return (
    (operation === undefined || operation === "analysis_start"
      ? research === undefined
      : operation === "analysis_start_v2" && isResearch(research)) &&
    typeof requestId === "string" &&
    !!requestId.trim() &&
    requestId.length <= 128 &&
    !!request &&
    typeof request === "object" &&
    ["vision", "horizon", "perspective", "constraints"].every(
      (key) => typeof request[key as keyof VisionRequest] === "string",
    ) &&
    !!request.vision.trim()
  );
}
interface Snapshot {
  request: VisionRequest;
  research: ResearchOptions;
  pendingOperation: StartOperation | null;
  connected: boolean;
  catalog: Capability[];
  selectedId: string;
  run: AnalysisRun | null;
  items: AnalysisSummary[];
  busy: "connecting" | "creating" | "loading" | "cancelling" | null;
  listBusy: boolean;
  listError: string;
  error: string;
  notice: string;
  pendingStart: boolean;
}
/** Only canonical server runs enter this store. Leaving the view stops reads, not server work. */
export class AnalysisSession {
  private state: Snapshot = {
    request: emptyAnalysisRequest(),
    research: frozenResearch(defaultResearchOptions()),
    pendingOperation: null,
    connected: false,
    catalog: [],
    selectedId: "",
    run: null,
    items: [],
    busy: null,
    listBusy: false,
    listError: "",
    error: "",
    notice: "",
    pendingStart: false,
  };
  private listeners = new Set<() => void>();
  private active = false;
  private epoch = 0;
  private selection = 0;
  private client: Client | null = null;
  private token = "";
  // A private cache is a connection boundary; credentials never enter query keys.
  private queries = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // Local API reads must report failure, not pause behind navigator.onLine.
        networkMode: "always",
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        // Only catalog/list/selected run are retained; disconnect clears all three.
        gcTime: Infinity,
      },
      mutations: { retry: false },
    },
  });
  private catalogObserver: QueryObserver<Capability[]> | null = null;
  private listObserver: QueryObserver<{ items: AnalysisSummary[] }> | null =
    null;
  private runObserver: QueryObserver<AnalysisRun> | null = null;
  private mutationController: AbortController | null = null;
  private pending: Pending | null = null;
  constructor(
    private factory: (token: string) => Client = (token) => new Api(token),
  ) {}
  getSnapshot = () => this.state;
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  private update(patch: Partial<Snapshot>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }
  start() {
    if (!this.active) this.queries.mount();
    this.active = true;
    // Tab storage contains only an input intent and IDs, never model transcripts.
    // Never replace an in-memory ambiguous intent with stale or corrupt storage.
    if (!this.pending) {
      try {
        const value: unknown = JSON.parse(tabRead(PENDING_KEY) || "null");
        if (isPending(value)) this.pending = freezePending(value);
        else tabWrite(PENDING_KEY, "");
      } catch {
        tabWrite(PENDING_KEY, "");
      }
    }
    this.update({
      selectedId: tabRead(ANALYSIS_SELECTION_KEY) || this.state.selectedId,
      pendingStart: !!this.pending,
      pendingOperation: this.pending
        ? (this.pending.operation ?? "analysis_start")
        : null,
      ...(this.pending
        ? {
            request: this.pending.request,
            ...(this.pending.operation === "analysis_start_v2"
              ? { research: this.pending.research }
              : {}),
          }
        : {}),
    });
  }
  stop() {
    this.disconnect();
    if (this.active) this.queries.unmount();
    this.active = false;
  }
  private invalidateRun() {
    this.selection++;
    this.runObserver?.destroy();
    this.runObserver = null;
    this.queries.removeQueries({ queryKey: ["run"] });
    this.mutationController?.abort();
    this.mutationController = null;
  }
  disconnect() {
    this.epoch++;
    this.invalidateRun();
    this.catalogObserver?.destroy();
    this.catalogObserver = null;
    this.listObserver?.destroy();
    this.listObserver = null;
    this.queries.clear();
    this.client = null;
    this.token = "";
    this.update({
      connected: false,
      catalog: [],
      run: null,
      items: [],
      busy: null,
      listBusy: false,
      error: "",
      listError: "",
      notice: "",
    });
  }
  supports(...names: string[]) {
    return (
      this.state.connected &&
      names.every((name) => this.state.catalog.some((c) => c.name === name))
    );
  }
  private current(epoch: number, selection?: number) {
    return (
      this.active &&
      epoch === this.epoch &&
      (selection === undefined || selection === this.selection)
    );
  }
  private message(error: unknown) {
    const text = error instanceof Error ? error.message : "操作失败，请重试。";
    return this.token ? text.split(this.token).join("[令牌已隐藏]") : text;
  }
  edit(patch: Partial<VisionRequest>) {
    if (!this.pending && this.state.busy !== "creating")
      this.update({ request: { ...this.state.request, ...patch } });
  }
  editResearch(patch: {
    mode?: ResearchOptions["mode"];
    budget?: Partial<ResearchBudget>;
  }) {
    if (this.pending || this.state.busy === "creating") return;
    const research = {
      ...this.state.research,
      ...patch,
      budget: { ...this.state.research.budget, ...patch.budget },
    };
    if (isResearch(research))
      this.update({ research: frozenResearch(research) });
  }
  startOperation(): StartOperation {
    return (
      this.pending?.operation ??
      (this.pending
        ? "analysis_start"
        : this.supports("analysis_start_v2")
          ? "analysis_start_v2"
          : "analysis_start")
    );
  }
  listOperation() {
    return this.supports("analysis_list_v2")
      ? "analysis_list_v2"
      : "analysis_list";
  }
  canCreate() {
    return this.supports(
      this.startOperation(),
      "analysis_get",
      this.listOperation(),
    );
  }
  async connect(token: string) {
    this.disconnect();
    if (!this.active || !token.trim()) return;
    this.token = token.trim();
    const client = this.factory(this.token);
    const observer = new QueryObserver<Capability[]>(this.queries, {
      queryKey: ["catalog"],
      queryFn: ({ signal }) => client.catalog(signal),
      enabled: false,
    });
    this.catalogObserver = observer;
    this.update({ busy: "connecting" });
    observer.subscribe((result) => {
      if (result.isFetching) return;
      if (result.isError) {
        this.update({ busy: null, error: this.message(result.error) });
      } else if (result.isSuccess) {
        this.client = client;
        tabWrite("tianji-token", this.token);
        this.update({ connected: true, catalog: result.data, busy: null });
      }
    });
    await observer.refetch({ cancelRefetch: false });
    if (this.catalogObserver !== observer || !this.client) return;
    await Promise.all([
      this.reload(),
      this.state.selectedId
        ? this.load(this.state.selectedId)
        : Promise.resolve(),
    ]);
  }
  async reload(cancelRefetch = false) {
    if (!this.active || !this.client || !this.supports(this.listOperation()))
      return;
    if (!this.listObserver) {
      const client = this.client;
      this.listObserver = new QueryObserver<{ items: AnalysisSummary[] }>(
        this.queries,
        {
          queryKey: ["list"],
          queryFn: ({ signal }) => client.op(this.listOperation(), {}, signal),
          enabled: false,
        },
      );
      this.listObserver.subscribe((result) => {
        this.update({
          listBusy: result.isFetching,
          listError: result.isFetching
            ? ""
            : result.isError
              ? this.message(result.error)
              : "",
          ...(result.isSuccess && !result.isFetching
            ? { items: result.data.items }
            : {}),
        });
      });
    }
    // refetch(cancelRefetch) alone does not cancel a first fetch with no cached
    // data. A committed creation must supersede even that initial list request.
    if (cancelRefetch)
      void this.queries.cancelQueries({ queryKey: ["list"], exact: true });
    await this.listObserver.refetch({ cancelRefetch: false });
  }
  async load(id: string) {
    if (
      !this.active ||
      !this.client ||
      !this.supports("analysis_get") ||
      this.state.busy === "creating" ||
      this.state.busy === "cancelling"
    )
      return;
    // Repeated reads of the selected run share the observer's in-flight request.
    if (this.state.selectedId !== id) this.invalidateRun();
    tabWrite(ANALYSIS_SELECTION_KEY, id);
    this.update({
      selectedId: id,
      run: null,
      busy: "loading",
      error: "",
      notice: "",
    });
    await this.readRun(id);
  }
  private async readRun(id: string) {
    if (!this.active || !this.client) return;
    if (!this.runObserver) {
      const client = this.client;
      this.runObserver = new QueryObserver<AnalysisRun>(this.queries, {
        queryKey: ["run", id],
        queryFn: async ({ signal }) => {
          const run = await client.op("analysis_get", { id }, signal);
          if (
            run.id !== id ||
            !["tianji.analysis.v1", "tianji.analysis.v2"].includes(
              run.schema_version,
            )
          )
            throw new Error("分析读回标识或版本不一致，请刷新。");
          return run;
        },
        refetchInterval: (query) =>
          query.state.status !== "error" &&
          query.state.data &&
          analysisActive(query.state.data.status)
            ? ANALYSIS_POLL_MS
            : false,
        refetchIntervalInBackground: true,
      });
      this.runObserver.subscribe((result) => {
        if (result.isFetching) return;
        if (result.isError) {
          this.update({
            busy: null,
            error: `${this.message(result.error)} 已暂停读取；可重新读取项目。`,
          });
        } else if (result.isSuccess) {
          const run = result.data;
          this.update({
            run,
            busy: null,
            error: "",
            items: this.state.items.map((item) =>
              item.id === run.id
                ? {
                    id: run.id,
                    schema_version: run.schema_version,
                    request: run.request,
                    status: run.status,
                    created_at: run.created_at,
                  }
                : item,
            ),
          });
        }
      });
    }
    await this.runObserver.refetch({ cancelRefetch: false });
  }
  async create() {
    if (
      !this.active ||
      !this.client ||
      this.state.busy ||
      !this.canCreate() ||
      !this.state.request.vision.trim()
    )
      return;
    this.invalidateRun();
    const epoch = this.epoch,
      selection = this.selection,
      controller = new AbortController();
    this.mutationController = controller;
    const operation = this.startOperation();
    this.pending ??= freezePending({
      request: {
        ...this.state.request,
        vision: this.state.request.vision.trim(),
        horizon: this.state.request.horizon.trim() || "未来十年",
        perspective:
          this.state.request.perspective.trim() || "公共利益与可协作的行动者",
      },
      requestId: crypto.randomUUID(),
      ...(operation === "analysis_start_v2"
        ? { operation, research: this.state.research }
        : { operation }),
    });
    tabWrite(PENDING_KEY, JSON.stringify(this.pending));
    this.update({
      busy: "creating",
      pendingStart: true,
      pendingOperation: operation,
      error: "",
      notice: "",
    });
    try {
      const pending = this.pending;
      const job = await this.client.op(
        operation,
        {
          request: pending.request,
          ...(pending.operation === "analysis_start_v2"
            ? { research: pending.research }
            : {}),
        },
        controller.signal,
        this.pending.requestId,
      );
      if (!this.current(epoch, selection)) return;
      // A successful envelope can still contain a malformed job. Do not discard
      // the retry intent until it identifies the durable project we can read back.
      if (
        job?.kind !== operation ||
        typeof job.id !== "string" ||
        !job.id.trim()
      )
        throw new Error("服务返回的分析任务标识或类型无效。");
      this.pending = null;
      tabWrite(PENDING_KEY, "");
      tabWrite(ANALYSIS_SELECTION_KEY, job.id);
      this.update({
        pendingStart: false,
        pendingOperation: null,
        selectedId: job.id,
        run: null,
        busy: "loading",
      });
      await this.readRun(job.id);
      if (this.current(epoch, selection) && this.state.run)
        this.update({
          notice: "项目已创建；输入与公开结构化任务结果持久保存。",
        });
      // A list read begun before the mutation must not hide the new project.
      if (this.current(epoch, selection)) await this.reload(true);
    } catch (error) {
      if (!this.current(epoch, selection)) return;
      // Explicit rejections did not enqueue work. Timeouts, malformed replies and
      // generic server/transport failures may follow a committed write: keep its UUID.
      const rejected =
        error instanceof ApiError &&
        error.code !== "INVALID_RESPONSE" &&
        (error.code === "analysis_disabled" ||
          (error.status >= 400 && error.status < 500 && error.status !== 408));
      if (rejected) {
        this.pending = null;
        tabWrite(PENDING_KEY, "");
      }
      this.update({
        busy: null,
        pendingStart: !!this.pending,
        pendingOperation: this.pending ? operation : null,
        error: rejected
          ? this.message(error)
          : `${this.message(error)} 创建可能已提交；刷新列表核对，或用同一请求安全重试。`,
      });
    }
  }
  async cancel() {
    const run = this.state.run;
    if (
      !this.active ||
      !this.client ||
      this.state.busy ||
      !run ||
      !analysisActive(run.status) ||
      !this.supports("job_cancel", "analysis_get")
    )
      return;
    this.invalidateRun();
    const epoch = this.epoch,
      selection = this.selection,
      controller = new AbortController();
    this.mutationController = controller;
    this.update({ busy: "cancelling", error: "", notice: "" });
    try {
      // Stable key: retrying cancellation is the same intent; readback is never cached.
      await this.client.op(
        "job_cancel",
        { id: run.id },
        controller.signal,
        `analysis-cancel-${run.id}`,
      );
      if (!this.current(epoch, selection)) return;
      await this.readRun(run.id);
      if (
        this.current(epoch, selection) &&
        this.state.run?.status === "cancelled"
      )
        this.update({ notice: "已从服务端确认取消；模型端停止为尽力而为。" });
      // Supersede list reads started before the mutation, just as creation does.
      // Otherwise a late running snapshot can overwrite the canonical cancellation.
      if (this.current(epoch, selection)) await this.reload(true);
    } catch (error) {
      if (this.current(epoch, selection))
        this.update({
          busy: null,
          error: `${this.message(error)} 取消状态未确认，请重新读取。`,
        });
    }
  }
}
export const analysisSession = new AnalysisSession();
