import type {
  AnalysisBudget,
  AnalysisRun,
  AnalysisStatus,
  AnalysisSummary,
} from "./analysisTypes";

export type Action = "wait" | "order_standard" | "order_express";
export type DisturbanceKind = "demand_spike" | "supplier_loss";
export interface Disturbance {
  tick: number;
  kind: DisturbanceKind;
  amount: number;
}
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
  disturbances: Disturbance[];
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
  lost: number;
  shipments: { due_tick: number; quantity: number }[];
}
export type ParticipantRole = "retailer" | "supplier";
export interface ObservationContext {
  branch_id: string;
  scenario_revision: number;
  spec_hash: string;
}
export type RetailerProjection = Omit<State, "supplier_stock" | "lost">;
export type SupplierProjection = Pick<
  State,
  "tick" | "supplier_stock" | "shipments"
>;
export type ObservationEnvelope = {
  actor_id: string;
  tick: number;
  context: ObservationContext;
  projection_hash: string;
  observation_hash: string;
} & (
  | { role: "retailer"; projection: RetailerProjection }
  | { role: "supplier"; projection: SupplierProjection }
);
export interface SavedObservation {
  id: string;
  observation: ObservationEnvelope;
}
export interface ActionProposal {
  actor_id: string;
  role: ParticipantRole;
  action: Action;
  observation_hash: string;
  policy_id: string;
}
export interface AdjudicationRecord {
  record_id: string;
  adjudicator_id: string;
  proposal_actor_id: string;
  role: ParticipantRole;
  policy_id: string;
  pre_state_hash: string;
  observation_hash: string;
  action: Action;
  status: "accepted" | "rejected";
  reason: string;
  post_state_hash: string;
  record_hash: string;
  context: ObservationContext;
}
export interface SavedAdjudication {
  id: string;
  observation_id: string;
  record: AdjudicationRecord;
  next_state: State;
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
interface JobBase {
  id: string;
  status: AnalysisStatus;
  error: string | null;
}
export interface AnalysisJob extends JobBase {
  kind: "analysis_start";
  result: null | { analysis_id: string };
}
export interface BranchJob extends JobBase {
  kind: "run_forward" | "run_backward" | "branch_fork";
  result: null | {
    branch?: Branch;
    branches?: Branch[];
    search?: SearchResult;
  };
}
export type Job = AnalysisJob | BranchJob;
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
  minItems?: number;
  maxItems?: number;
  default?: unknown;
  enum?: unknown[];
  anyOf?: JsonSchema[];
  items?: JsonSchema;
}
export interface Capability {
  name: string;
  description: string;
  input_schema: JsonSchema;
  mutating: boolean;
}
export interface VisionRequest {
  vision: string;
  horizon: string;
  perspective: string;
  constraints: string;
}
export interface VisionNode {
  id: string;
  title: string;
  stage: 1 | 2 | 3 | 4;
  actors: string[];
  action: string;
  mechanism: string;
  prerequisites: string[];
  risks: string[];
  signals: string[];
}
export interface VisionPath {
  id: string;
  title: string;
  summary: string;
  node_ids: string[];
  tradeoff: string;
}
export interface VisionPlan {
  title: string;
  interpretation: string;
  assumptions: string[];
  tensions: string[];
  nodes: VisionNode[];
  paths: VisionPath[];
}
export interface VisionDraft {
  request: VisionRequest;
  plan: VisionPlan;
  model: string;
  generated_at: string;
  grounding: "model_hypothesis";
}
export interface SavedVision {
  id: string;
  created_at: string;
  draft: VisionDraft;
}
export interface VisionSummary {
  id: string;
  created_at: string;
  title: string;
  vision: string;
}
export interface AnalysisStats {
  saved_analyses: number;
  nodes: number;
  paths: number;
  scope: "saved_analyses_only";
  architecture: "single_model_single_call";
}
export interface Operations {
  analysis_start: [
    { request: VisionRequest; budget?: Partial<AnalysisBudget> },
    AnalysisJob,
  ];
  analysis_get: [{ id: string }, AnalysisRun];
  analysis_list: [{}, { items: AnalysisSummary[] }];
  analysis_stats: [{}, AnalysisStats];
  vision_generate: [VisionRequest, VisionDraft];
  vision_save: [{ draft: VisionDraft }, SavedVision];
  vision_list: [{}, { items: VisionSummary[] }];
  vision_get: [{ id: string }, SavedVision];
  observation_create: [
    {
      branch_id: string;
      tick: number;
      actor_id: string;
      role: ParticipantRole;
    },
    SavedObservation,
  ];
  observation_get: [{ id: string }, SavedObservation];
  actor_propose: [{ observation_id: string }, ActionProposal];
  adjudication_create: [
    {
      observation_id: string;
      proposal: ActionProposal;
      adjudicator_id: string;
    },
    SavedAdjudication,
  ];
  adjudication_get: [{ id: string }, SavedAdjudication];
  adjudication_list: [{ branch_id: string }, { items: SavedAdjudication[] }];
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
  async catalog(signal?: AbortSignal): Promise<Capability[]> {
    const response = await fetch("/api/capabilities", {
      signal,
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
    signal?: AbortSignal,
    requestId?: string,
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
      signal,
      headers: this.headers(),
      body: JSON.stringify({
        arguments: args,
        ...(capability.mutating
          ? { request_id: requestId ?? crypto.randomUUID() }
          : {}),
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
function deref(
  root: JsonSchema | undefined,
  schema: JsonSchema | undefined,
): JsonSchema | undefined {
  if (schema?.$ref) return root?.$defs?.[schema.$ref.split("/").pop() ?? ""];
  return schema;
}
/** Walk a capability input schema by property names; "[]" descends into items. */
export function schemaAt(
  catalog: Capability[],
  operation: string,
  path: readonly string[],
): JsonSchema | undefined {
  const root = catalog.find((c) => c.name === operation)?.input_schema;
  if (!root) return undefined;
  let schema: JsonSchema | undefined = root;
  for (const step of path) {
    schema = deref(root, schema);
    if (!schema) return undefined;
    schema = step === "[]" ? schema.items : schema.properties?.[step];
  }
  return deref(root, schema);
}
export function schemaFields(
  catalog: Capability[],
  operation: string,
  field?: string,
): Record<string, JsonSchema> {
  return schemaAt(catalog, operation, field ? [field] : [])?.properties ?? {};
}
