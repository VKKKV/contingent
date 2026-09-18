import type {
  Action,
  ActionProposal,
  Api,
  Capability,
  ParticipantRole,
  SavedAdjudication,
  SavedObservation,
} from "./api";

export interface DirectorContext {
  api: Pick<Api, "op"> | null;
  branchId: string | null;
  tick: number;
  actorId: string;
  role: ParticipantRole;
  catalog: Capability[];
}
export interface DirectorSnapshot {
  observation: SavedObservation | null;
  proposal: ActionProposal | null;
  action: Action;
  result: SavedAdjudication | null;
  history: SavedAdjudication[];
  busy: boolean;
  historyBusy: boolean;
  historyLoaded: boolean;
  error: string;
  historyError: string;
}
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** One immutable selection/identity scope. No synthetic product results or local history. */
export class DirectorSession {
  private state: DirectorSnapshot = {
    observation: null,
    proposal: null,
    action: "wait",
    result: null,
    history: [],
    busy: false,
    historyBusy: false,
    historyLoaded: false,
    error: "",
    historyError: "",
  };
  private listeners = new Set<() => void>();
  private active = false;
  private generation = 0;
  private historyGeneration = 0;
  constructor(readonly context: DirectorContext) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private update(patch: Partial<DirectorSnapshot>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  supports(...names: string[]) {
    return names.every((name) =>
      this.context.catalog.some((c) => c.name === name),
    );
  }
  start() {
    this.active = true;
    this.generation += 1;
    void this.reloadHistory();
  }
  stop() {
    this.active = false;
    this.generation += 1;
    this.historyGeneration += 1;
    this.update({
      observation: null,
      proposal: null,
      action: "wait",
      result: null,
      busy: false,
      historyBusy: false,
      error: "",
    });
  }
  private current(generation: number) {
    return this.active && this.generation === generation;
  }
  clearResult() {
    if (!this.state.busy) this.update({ result: null, error: "" });
  }
  setAction(action: Action) {
    if (this.state.busy || action === this.state.action) return;
    this.update({ action, proposal: null, result: null, error: "" });
  }
  async reloadHistory() {
    const { api, branchId } = this.context;
    if (
      !this.active ||
      !api ||
      !branchId ||
      !this.supports("adjudication_list")
    )
      return;
    const generation = this.generation;
    const request = ++this.historyGeneration;
    const current = () =>
      this.current(generation) && request === this.historyGeneration;
    this.update({ historyBusy: true, historyError: "" });
    try {
      const result = await api.op("adjudication_list", { branch_id: branchId });
      if (current())
        this.update({ history: result.items, historyLoaded: true });
    } catch (e) {
      if (current()) this.update({ historyError: message(e) });
    } finally {
      if (current()) this.update({ historyBusy: false });
    }
  }
  async observe() {
    const { api, branchId, tick, actorId, role } = this.context;
    if (
      !this.active ||
      !api ||
      !branchId ||
      !actorId.trim() ||
      this.state.busy ||
      !this.supports("observation_create", "observation_get")
    )
      return;
    const generation = this.generation;
    this.update({
      busy: true,
      observation: null,
      proposal: null,
      action: "wait",
      result: null,
      error: "",
    });
    try {
      const created = await api.op("observation_create", {
        branch_id: branchId,
        tick,
        actor_id: actorId,
        role,
      });
      if (!this.current(generation)) return;
      const saved = await api.op("observation_get", { id: created.id });
      if (!this.current(generation)) return;
      if (
        saved.id !== created.id ||
        saved.observation.context.branch_id !== branchId ||
        saved.observation.tick !== tick ||
        saved.observation.actor_id !== actorId ||
        saved.observation.role !== role
      )
        throw new Error("观察读回与当前选择不一致，请重试。");
      this.update({ observation: saved });
    } catch (e) {
      if (this.current(generation)) this.update({ error: message(e) });
    } finally {
      if (this.current(generation)) this.update({ busy: false });
    }
  }
  async propose() {
    const { api } = this.context;
    const observation = this.state.observation;
    if (
      !this.active ||
      !api ||
      !observation ||
      this.state.busy ||
      !this.supports("actor_propose")
    )
      return;
    const generation = this.generation;
    const current = () =>
      this.current(generation) && this.state.observation === observation;
    this.update({ busy: true, proposal: null, result: null, error: "" });
    try {
      const proposal = await api.op("actor_propose", {
        observation_id: observation.id,
      });
      if (!current()) return;
      if (
        proposal.actor_id !== observation.observation.actor_id ||
        proposal.role !== observation.observation.role ||
        proposal.observation_hash !==
          observation.observation.observation_hash ||
        !["wait", "order_standard", "order_express"].includes(
          proposal.action,
        ) ||
        !proposal.policy_id?.trim()
      )
        throw new Error("模型提案与当前观察不一致或格式无效，请重试。");
      this.update({ proposal, action: proposal.action });
    } catch (e) {
      if (current()) this.update({ error: message(e) });
    } finally {
      if (current()) this.update({ busy: false });
    }
  }
  async adjudicate(action: Action, adjudicatorId: string) {
    const { api, actorId } = this.context;
    const observation = this.state.observation;
    if (
      !this.active ||
      !api ||
      !observation ||
      this.state.busy ||
      !adjudicatorId.trim() ||
      adjudicatorId === actorId ||
      !this.supports(
        "adjudication_create",
        "adjudication_get",
        "adjudication_list",
      )
    )
      return;
    const generation = this.generation;
    this.update({ busy: true, result: null, error: "" });
    try {
      const created = await api.op("adjudication_create", {
        observation_id: observation.id,
        proposal: {
          actor_id: observation.observation.actor_id,
          role: observation.observation.role,
          action,
          observation_hash: observation.observation.observation_hash,
          policy_id:
            this.state.proposal?.action === action
              ? this.state.proposal.policy_id
              : "manual.director.v1",
        },
        adjudicator_id: adjudicatorId,
      });
      if (!this.current(generation)) return;
      const saved = await api.op("adjudication_get", { id: created.id });
      if (!this.current(generation)) return;
      if (
        saved.id !== created.id ||
        saved.observation_id !== observation.id ||
        saved.record.context.branch_id !== this.context.branchId
      ) {
        throw new Error("裁决读回与当前观察不一致，请刷新历史。");
      }
      this.update({ result: saved });
    } catch (e) {
      if (this.current(generation)) this.update({ error: message(e) });
    } finally {
      if (this.current(generation)) {
        // Even a lost write/readback response may have persisted a receipt.
        // Supersede any pre-write list response with a fresh server read.
        this.update({ busy: false });
        await this.reloadHistory();
      }
    }
  }
}
