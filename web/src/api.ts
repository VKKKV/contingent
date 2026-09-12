export type Action = "wait" | "order_standard" | "order_express";
export interface Scenario {
  name: string;
  description: string | null;
  horizon: number;
  initial_inventory: number;
  initial_cash: number;
  demand_per_tick: number;
  supplier_stock: number;
  shipment_size: number;
  standard_cost: number;
  express_cost: number;
  standard_lead: number;
  express_lead: number;
}
export interface Goal {
  max_shortage: number;
  min_cash: number;
  max_spend: number;
  min_inventory: number;
}
export interface State {
  tick: number;
  inventory: number;
  cash: number;
  supplier_stock: number;
  delivered: number;
  shortage: number;
  spent: number;
  shipments: { due_tick: number; quantity: number }[];
}
export interface Frame {
  state: State;
  action: string;
  events: string[];
  state_hash: string;
}
export interface Trajectory {
  frames: Frame[];
  actions: Action[];
  final_state: State;
  state_hash: string;
  goal_met: boolean | null;
  rule_version?: string;
}
export interface Branch {
  id: string;
  name: string;
  scenario_id: string;
  scenario_revision: number;
  spec: Scenario;
  parent_id: string | null;
  fork_tick: number | null;
  trajectory: Trajectory;
  mode: "forward" | "backward" | "fork" | "import";
  created_at: string;
  provenance: {
    goal: Goal | null;
    prefix_actions: Action[];
    imported_parent_id: string | null;
  };
}
export interface SearchResult {
  plans: Trajectory[];
  expanded: number;
  exhausted: boolean;
  status: "found" | "no_solution" | "budget_exhausted";
  rule_version: string;
}
export interface Job {
  id: string;
  kind: string;
  status:
    "queued" | "running" | "succeeded" | "failed" | "cancelled" | "interrupted";
  result: null | {
    branch?: Branch;
    branches?: Branch[];
    search?: SearchResult;
  };
  error: string | null;
}
export interface Workspace {
  id: string;
  revision: number;
  branch_id: string | null;
  scenario_id: string;
  compare_branch_id: string | null;
  tick: number;
  panel: string;
}
export interface ScenarioRecord {
  id: string;
  revision: number;
  spec: Scenario;
}
export interface Bundle {
  schema_version: string;
  branch: Branch;
  digest: string;
}
export type Delta = Pick<
  State,
  "inventory" | "cash" | "shortage" | "spent" | "delivered"
>;
export interface Comparison {
  left: Branch;
  right: Branch;
  delta: Delta;
}
export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  default?: unknown;
  enum?: unknown[];
  anyOf?: JsonSchema[];
}
export interface Capability {
  name: string;
  description: string;
  input_schema: JsonSchema;
  mutating: boolean;
}
export interface Operations {
  scenario_list: [{}, { items: ScenarioRecord[] }];
  scenario_create: [{ spec: Scenario }, ScenarioRecord];
  scenario_update: [
    { id: string; revision: number; spec: Scenario },
    ScenarioRecord,
  ];
  branch_list: [{ scenario_id: string }, { items: Branch[] }];
  branch_get: [{ id: string }, Branch];
  run_forward: [{ scenario_id: string; actions: Action[]; name?: string }, Job];
  run_backward: [
    { scenario_id: string; goal: Goal; max_nodes: number; name?: string },
    Job,
  ];
  branch_fork: [
    { id: string; tick: number; actions: Action[]; name?: string },
    Job,
  ];
  branch_compare: [{ left_id: string; right_id: string }, Comparison];
  branch_export: [{ id: string }, Bundle];
  branch_import: [{ bundle: object }, Branch];
  job_get: [{ id: string }, Job];
  job_cancel: [{ id: string }, Job];
  workspace_attach: [{ id?: string }, Workspace];
  workspace_get: [{ id: string }, Workspace];
  workspace_update: [
    {
      id: string;
      revision: number;
      branch_id?: string | null;
      scenario_id?: string;
      compare_branch_id?: string | null;
      tick?: number;
      panel?: "timeline" | "compare" | "goal";
    },
    Workspace,
  ];
}
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export class Api {
  private capabilities: Capability[] = [];
  constructor(private token: string) {}
  async catalog(): Promise<Capability[]> {
    const response = await fetch("/api/capabilities", {
      headers: this.headers(),
    });
    const body = await response.json();
    if (!response.ok)
      throw new ApiError(
        body.error?.code ?? "HTTP_ERROR",
        body.error?.message ?? "连接失败，请检查令牌与服务。",
        response.status,
      );
    this.capabilities = body;
    return this.capabilities;
  }
  private headers() {
    return {
      Authorization: `Bearer ${this.token}`,
      "Content-Type": "application/json",
    };
  }
  async op<K extends keyof Operations>(
    name: K,
    args: Operations[K][0],
  ): Promise<Operations[K][1]> {
    const capability = this.capabilities.find((c) => c.name === name);
    if (!capability)
      throw new ApiError(
        "CAPABILITY_MISSING",
        `服务未开放操作 ${name}，请检查版本。`,
        404,
      );
    const response = await fetch(`/api/operations/${name}`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        arguments: args,
        ...(capability.mutating ? { request_id: crypto.randomUUID() } : {}),
      }),
    });
    let body;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        "INVALID_RESPONSE",
        `服务返回非 JSON 响应 (${response.status})。`,
        response.status,
      );
    }
    if (!response.ok || !body.ok)
      throw new ApiError(
        body.error?.code ?? "HTTP_ERROR",
        body.error?.message ?? `操作失败 (${response.status})`,
        response.status,
      );
    return body.data;
  }
}
export function schemaFields(
  catalog: Capability[],
  operation: string,
  field?: string,
): Record<string, JsonSchema> {
  const root = catalog.find((c) => c.name === operation)?.input_schema;
  if (!root) return {};
  let schema = field ? root.properties?.[field] : root;
  if (schema?.$ref) schema = root.$defs?.[schema.$ref.split("/").pop() ?? ""];
  return schema?.properties ?? {};
}
export const isTerminal = (status: Job["status"]) =>
  ["succeeded", "failed", "cancelled", "interrupted"].includes(status);
export function frameAtTick(branch: Branch, tick: number): Frame {
  return (
    branch.trajectory.frames.find((f) => f.state.tick === tick) ??
    branch.trajectory.frames[0]
  );
}
export const actionLabel: Record<string, string> = {
  initial: "初始状态",
  wait: "等待",
  order_standard: "标准订货",
  order_express: "加急订货",
};
export const modeLabel: Record<Branch["mode"], string> = {
  forward: "正向",
  backward: "反推",
  fork: "分叉",
  import: "导入",
};
export const statusLabel: Record<Job["status"], string> = {
  queued: "排队中",
  running: "计算中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "重启中断",
};
