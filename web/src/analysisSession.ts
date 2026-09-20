import { QueryClient, QueryObserver } from "@tanstack/query-core";
import { Api, ApiError, type Capability, type VisionRequest } from "./api";
import {
  analysisActive,
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
type Pending = { request: VisionRequest; requestId: string };
function isPending(value: unknown): value is Pending {
  if (!value || typeof value !== "object") return false;
  const { requestId, request } = value as Partial<Pending>;
  return (
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
        if (isPending(value)) this.pending = value;
        else tabWrite(PENDING_KEY, "");
      } catch {
        tabWrite(PENDING_KEY, "");
      }
    }
    this.update({
      selectedId: tabRead(ANALYSIS_SELECTION_KEY) || this.state.selectedId,
      pendingStart: !!this.pending,
      ...(this.pending ? { request: this.pending.request } : {}),
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
    if (!this.active || !this.client || !this.supports("analysis_list")) return;
    if (!this.listObserver) {
      const client = this.client;
      this.listObserver = new QueryObserver<{ items: AnalysisSummary[] }>(
        this.queries,
        {
          queryKey: ["list"],
          queryFn: ({ signal }) => client.op("analysis_list", {}, signal),
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
          if (run.id !== id || run.schema_version !== "tianji.analysis.v1")
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
      !this.supports("analysis_start", "analysis_get", "analysis_list") ||
      !this.state.request.vision.trim()
    )
      return;
    this.invalidateRun();
    const epoch = this.epoch,
      selection = this.selection,
      controller = new AbortController();
    this.mutationController = controller;
    this.pending ??= {
      request: {
        ...this.state.request,
        vision: this.state.request.vision.trim(),
        horizon: this.state.request.horizon.trim() || "未来十年",
        perspective:
          this.state.request.perspective.trim() || "公共利益与可协作的行动者",
      },
      requestId: crypto.randomUUID(),
    };
    tabWrite(PENDING_KEY, JSON.stringify(this.pending));
    this.update({
      busy: "creating",
      pendingStart: true,
      error: "",
      notice: "",
    });
    try {
      const job = await this.client.op(
        "analysis_start",
        { request: this.pending.request },
        controller.signal,
        this.pending.requestId,
      );
      if (!this.current(epoch, selection)) return;
      // A successful envelope can still contain a malformed job. Do not discard
      // the retry intent until it identifies the durable project we can read back.
      if (
        job?.kind !== "analysis_start" ||
        typeof job.id !== "string" ||
        !job.id.trim()
      )
        throw new Error("服务返回的分析任务标识或类型无效。");
      this.pending = null;
      tabWrite(PENDING_KEY, "");
      tabWrite(ANALYSIS_SELECTION_KEY, job.id);
      this.update({
        pendingStart: false,
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
