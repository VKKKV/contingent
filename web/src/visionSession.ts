import {
  Api,
  type Capability,
  type SavedVision,
  type VisionDraft,
  type VisionRequest,
  type VisionSummary,
} from "./api";
import { validateVision } from "./visionGraph";
import { recordTiming } from "./runTiming";

export const VISION_TIMEOUT_MS = 180_000;
export const emptyVisionRequest = (): VisionRequest => ({
  vision: "",
  horizon: "未来十年",
  perspective: "公共利益与可协作的行动者",
  constraints: "",
});
interface VisionSnapshot {
  request: VisionRequest;
  connected: boolean;
  catalog: Capability[];
  draft: VisionDraft | null;
  saved: SavedVision | null;
  busy: "connecting" | "generating" | "saving" | "loading" | null;
  startedAt: number | null;
  error: string;
  notice: string;
  items: VisionSummary[];
  listBusy: boolean;
  listLoaded: boolean;
  listError: string;
}
type Client = Pick<Api, "catalog" | "op">;
/** Ephemeral editor. Only save() writes a draft; every asynchronous result is scoped. */
export class VisionSession {
  private state: VisionSnapshot = {
    request: emptyVisionRequest(),
    connected: false,
    catalog: [],
    draft: null,
    saved: null,
    busy: null,
    startedAt: null,
    error: "",
    notice: "",
    items: [],
    listBusy: false,
    listLoaded: false,
    listError: "",
  };
  private listeners = new Set<() => void>();
  private active = false;
  private revision = 0;
  private connection = 0;
  private listRevision = 0;
  private controller: AbortController | null = null;
  private client: Client | null = null;
  private token = "";
  private pendingSave: {
    draft: VisionDraft;
    requestId: string;
    createdId?: string;
  } | null = null;
  constructor(
    private factory: (token: string) => Client = (token) => new Api(token),
  ) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(patch: Partial<VisionSnapshot>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }
  start() {
    this.active = true;
  }
  stop() {
    this.disconnect();
    this.active = false;
  }
  supports(...names: string[]) {
    return (
      this.state.connected &&
      names.every((name) => this.state.catalog.some((c) => c.name === name))
    );
  }
  private invalidate() {
    this.revision++;
    this.controller?.abort();
    this.controller = null;
  }
  private current(revision: number) {
    return this.active && this.revision === revision;
  }
  private message(error: unknown) {
    const text = error instanceof Error ? error.message : "操作失败，请重试。";
    return this.token ? text.split(this.token).join("[令牌已隐藏]") : text;
  }
  edit(patch: Partial<VisionRequest>) {
    this.invalidate();
    this.pendingSave = null;
    this.update({
      request: { ...this.state.request, ...patch },
      draft: null,
      saved: null,
      busy: null,
      startedAt: null,
      error: "",
      notice: "",
    });
  }
  cancel() {
    this.invalidate();
    this.update({
      busy: null,
      startedAt: null,
      notice: "已停止等待；服务端可能仍在计算，后续响应不会显示。",
    });
  }
  disconnect() {
    this.invalidate();
    this.pendingSave = null;
    this.connection++;
    this.listRevision++;
    this.client = null;
    this.update({
      connected: false,
      catalog: [],
      draft: null,
      saved: null,
      busy: null,
      startedAt: null,
      items: [],
      listBusy: false,
      listLoaded: false,
      listError: "",
      error: "",
      notice: "",
    });
  }
  async connect(token: string) {
    this.disconnect();
    if (!this.active || !token.trim()) return;
    this.token = token.trim();
    const epoch = this.connection;
    const client = this.factory(this.token);
    this.update({ busy: "connecting" });
    try {
      const catalog = await client.catalog();
      if (!this.active || epoch !== this.connection) return;
      this.client = client;
      this.update({ catalog, connected: true, busy: null });
      try {
        sessionStorage.setItem("tianji-token", this.token);
      } catch {
        /* Tab storage can be unavailable. */
      }
      await this.reload();
    } catch (error) {
      if (this.active && epoch === this.connection)
        this.update({ busy: null, error: this.message(error) });
    }
  }
  async reload() {
    if (!this.active || !this.client || !this.supports("vision_list")) return;
    const client = this.client,
      epoch = this.connection,
      request = ++this.listRevision;
    const current = () =>
      this.active && epoch === this.connection && request === this.listRevision;
    this.update({ listBusy: true, listError: "" });
    try {
      const result = await client.op("vision_list", {});
      if (current()) this.update({ items: result.items, listLoaded: true });
    } catch (error) {
      if (current()) this.update({ listError: this.message(error) });
    } finally {
      if (current()) this.update({ listBusy: false });
    }
  }
  async generate() {
    if (
      !this.active ||
      !this.client ||
      !this.supports("vision_generate") ||
      !this.state.request.vision.trim()
    )
      return;
    this.invalidate();
    this.pendingSave = null;
    const revision = this.revision;
    const controller = new AbortController();
    this.controller = controller;
    const request = {
      ...this.state.request,
      vision: this.state.request.vision.trim(),
      horizon: this.state.request.horizon.trim() || "未来十年",
      perspective:
        this.state.request.perspective.trim() || "公共利益与可协作的行动者",
    };
    this.update({
      draft: null,
      saved: null,
      busy: "generating",
      startedAt: Date.now(),
      error: "",
      notice: "",
    });
    const measuredStart = performance.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const deadline = new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          reject(
            new Error(
              "已等待 180 秒，停止接收本次结果。服务端可能仍在计算；请稍后重试。",
            ),
          );
          controller.abort();
        }, VISION_TIMEOUT_MS);
      });
      const draft = await Promise.race([
        this.client.op("vision_generate", request, controller.signal),
        deadline,
      ]);
      if (!this.current(revision)) return;
      validateVision(draft);
      if (
        Object.keys(request).some(
          (key) =>
            draft.request[key as keyof VisionRequest] !==
            request[key as keyof VisionRequest],
        )
      )
        throw new Error("返回的目标与当前输入不一致，请重试。");
      recordTiming(performance.now() - measuredStart);
      this.update({ draft });
    } catch (error) {
      if (this.current(revision)) this.update({ error: this.message(error) });
    } finally {
      clearTimeout(timer);
      if (this.current(revision)) {
        this.controller = null;
        this.update({ busy: null, startedAt: null });
      }
    }
  }
  async load(id: string) {
    if (!this.active || !this.client || !this.supports("vision_get")) return;
    this.invalidate();
    this.pendingSave = null;
    const revision = this.revision;
    this.update({
      draft: null,
      saved: null,
      busy: "loading",
      startedAt: null,
      error: "",
      notice: "",
    });
    try {
      const saved = await this.client.op("vision_get", { id });
      if (!this.current(revision)) return;
      validateVision(saved.draft);
      if (saved.id !== id) throw new Error("项目读回不一致，请刷新列表。");
      this.update({ draft: saved.draft, saved, request: saved.draft.request });
    } catch (error) {
      if (this.current(revision)) this.update({ error: this.message(error) });
    } finally {
      if (this.current(revision)) this.update({ busy: null });
    }
  }
  async save() {
    const draft = this.state.draft,
      client = this.client;
    if (
      !this.active ||
      !client ||
      !draft ||
      this.state.busy ||
      this.state.saved ||
      !this.supports("vision_save", "vision_get", "vision_list")
    )
      return;
    const revision = this.revision,
      epoch = this.connection;
    const pending = (this.pendingSave ??= {
      draft: structuredClone(draft),
      requestId: crypto.randomUUID(),
    });
    this.update({ busy: "saving", error: "", notice: "" });
    try {
      if (!pending.createdId) {
        const created = await client.op(
          "vision_save",
          { draft: pending.draft },
          undefined,
          pending.requestId,
        );
        if (typeof created?.id !== "string" || !created.id.trim())
          throw new Error("服务返回的保存项目标识无效。");
        pending.createdId = created.id;
      }
      // Once the target is known, retry only readback, never another mutation.
      // A write may have completed even after an edit. Verify without restoring obsolete UI.
      const saved = await client.op("vision_get", { id: pending.createdId });
      validateVision(saved.draft);
      if (
        saved.id !== pending.createdId ||
        JSON.stringify(saved.draft) !== JSON.stringify(pending.draft)
      )
        throw new Error("保存已提交，但读回内容不一致。请刷新项目列表核对。");
      if (this.current(revision)) {
        this.pendingSave = null;
        this.update({ saved, notice: "项目已保存，并已从服务端读回确认。" });
      }
    } catch (error) {
      if (this.current(revision))
        this.update({
          error: `${this.message(error)} 保存可能已提交，请刷新项目列表核对后再重试。`,
        });
    } finally {
      if (this.current(revision)) this.update({ busy: null });
      if (this.active && epoch === this.connection) await this.reload();
    }
  }
}
