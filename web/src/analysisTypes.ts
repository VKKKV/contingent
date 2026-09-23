import type { VisionRequest } from "./api";

export type AnalysisStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "partial"
  | "failed"
  | "cancelled"
  | "interrupted";
export interface AnalysisBudget {
  max_calls: number;
  max_seconds: number;
  max_output_tokens: number;
  max_tasks: number;
  max_revision_depth: number;
}
export interface AnalysisFrame {
  objective: string;
  criteria: string[];
  assumptions: string[];
  unknowns: string[];
  perspectives: string[];
  clarification: string;
}
export interface AnalysisClaim {
  id: string;
  kind: "assumption" | "intervention" | "outcome";
  title: string;
  detail: string;
  stakeholders: string[];
  signals: string[];
}
export interface AnalysisStrategy {
  title: string;
  mechanism: string;
  claims: AnalysisClaim[];
  links: {
    source: string;
    target: string;
    kind: "requires" | "supports" | "may-influence";
  }[];
  prerequisites: string[];
  tradeoffs: string[];
}
export interface AnalysisCritique {
  objections: { target_claim_id: string; concern: string; test: string }[];
  revision_task_id: string;
  limitation: string;
}
export interface AnalysisSynthesis {
  summary: string;
  alternatives: string[];
  unresolved: string[];
}
interface TaskBase {
  id: string;
  parent_id: string | null;
  dependencies: string[];
  brief: string;
  status: AnalysisStatus;
  model: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  output_tokens: number | null;
  error: string | null;
}
export type AnalysisTask = TaskBase &
  (
    | { role: "framing"; result: AnalysisFrame | null }
    | { role: "strategy" | "revision"; result: AnalysisStrategy | null }
    | { role: "critic"; result: AnalysisCritique | null }
    | { role: "synthesis"; result: AnalysisSynthesis | null }
  );
export interface IssueNode {
  id: string;
  kind:
    | "question"
    | "assumption"
    | "claim"
    | "intervention"
    | "outcome"
    | "objection";
  title: string;
  detail: string;
  task_id: string;
  grounding: "model_hypothesis" | "model_objection";
  stakeholders: string[];
  signals: string[];
}
export interface IssueEdge {
  source: string;
  target: string;
  kind: "requires" | "supports" | "challenges" | "may-influence";
}
export interface AnalysisCandidate {
  id: string;
  task_id: string;
  title: string;
  mechanism: string;
  node_ids: string[];
  prerequisites: string[];
  tradeoffs: string[];
  supersedes: string | null;
}
interface AnalysisRunBase {
  id: string;
  request: VisionRequest;
  budget: AnalysisBudget;
  status: AnalysisStatus;
  created_at: string;
  finished_at: string | null;
  tasks: AnalysisTask[];
  nodes: IssueNode[];
  edges: IssueEdge[];
  candidates: AnalysisCandidate[];
  summary: string;
  unresolved: string[];
  calls: number;
  reserved_output_tokens: number;
  duration_ms: number;
  error: string | null;
  architecture: "bounded_same_model_agents";
}
export interface ResearchBudget {
  max_queries: number;
  max_pages: number;
  max_seconds: number;
  max_response_bytes: number;
  max_total_bytes: number;
}
export interface ResearchOptions {
  mode: "online" | "offline";
  budget: ResearchBudget;
}
export const defaultResearchOptions = (): ResearchOptions => ({
  mode: "online",
  budget: {
    max_queries: 2,
    max_pages: 3,
    max_seconds: 90,
    max_response_bytes: 524288,
    max_total_bytes: 2097152,
  },
});
export interface ResearchSource {
  id: string;
  title: string;
  url: string;
  resolved_url: string;
  retrieved_at: string;
  published_at: string | null;
  publisher: string;
  text: string;
  text_sha256: string;
  extractor: string;
  origin: "public_web";
}
export interface ResearchPassage {
  id: string;
  source_id: string;
  start: number;
  end: number;
  quote: string;
}
export interface ResearchState {
  status:
    | "not_started"
    | "running"
    | "succeeded"
    | "partial"
    | "failed"
    | "cancelled"
    | "interrupted"
    | "skipped";
  queries: string[];
  hits: { title: string; url: string; snippet: string }[];
  sources: ResearchSource[];
  passages: ResearchPassage[];
  errors: string[];
  queries_used: number;
  pages_used: number;
  fetched_bytes: number;
  started_at: string | null;
  finished_at: string | null;
}
export interface EvidenceCitation {
  task_id: string;
  target: string;
  passage_id: string;
  relation: "support" | "challenge" | "context";
  epistemic: "source_statement" | "inference" | "assumption";
}
export interface ResearchFrontierItem {
  id: string;
  question: string;
  parent_question: string | null;
  goal_facet: string;
  query: string;
  priority: number;
  state: "proposed" | "attempted" | "skipped" | "cancelled" | "interrupted";
  attempts: number;
  evidence_refs: string[];
  stop_reason: string | null;
  created_at: string;
  updated_at: string;
}
export interface AnalysisRunV1 extends AnalysisRunBase {
  schema_version: "tianji.analysis.v1";
}
export interface AnalysisRunV2 extends AnalysisRunBase {
  schema_version: "tianji.analysis.v2";
  research_options: ResearchOptions;
  research: ResearchState;
  citations: EvidenceCitation[];
  task_passages: Record<string, string[]>;
}
export type AnalysisRun = AnalysisRunV1 | AnalysisRunV2;
export type AnalysisSummary = Pick<
  AnalysisRun,
  "id" | "status" | "created_at" | "request"
> & { schema_version?: AnalysisRun["schema_version"] };
export const analysisActive = (status: AnalysisStatus) =>
  status === "queued" || status === "running";
export const analysisStatusLabel: Record<AnalysisStatus, string> = {
  queued: "排队",
  running: "运行中",
  succeeded: "已完成",
  partial: "部分结果",
  failed: "失败",
  cancelled: "已取消",
  interrupted: "已中断",
};
export const analysisRoleLabel: Record<AnalysisTask["role"], string> = {
  framing: "问题界定",
  strategy: "候选策略",
  critic: "质疑审查",
  revision: "定向修订",
  synthesis: "综合",
};
