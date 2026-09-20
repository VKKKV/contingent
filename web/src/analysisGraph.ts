import dagre from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import {
  analysisRoleLabel,
  analysisStatusLabel,
  type AnalysisRun,
  type IssueNode,
} from "./analysisTypes";

export type AnalysisFlowNode = Node<{
  label: string;
  taskId: string;
  status?: string;
}>;
const WIDTH = 236,
  HEIGHT = 100;
/** Dagre owns layout; issue feedback edges remain intact, not treated as task DAG errors. */
export function layoutAnalysis(nodes: AnalysisFlowNode[], edges: Edge[]) {
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setGraph({ rankdir: "LR", ranksep: 90, nodesep: 40 });
  graph.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((node) =>
    graph.setNode(node.id, { width: WIDTH, height: HEIGHT }),
  );
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target, {}, edge.id));
  dagre.layout(graph);
  return {
    nodes: nodes.map((node) => {
      const point = graph.node(node.id);
      return {
        ...node,
        position: { x: point.x - WIDTH / 2, y: point.y - HEIGHT / 2 },
        style: { width: WIDTH, height: HEIGHT },
      };
    }),
    edges,
  };
}
export function taskGraph(run: AnalysisRun, selectedTask: string) {
  const nodes: AnalysisFlowNode[] = run.tasks.map((task) => ({
    id: task.id,
    position: { x: 0, y: 0 },
    selected: task.id === selectedTask,
    data: {
      label: `${task.id} · ${analysisRoleLabel[task.role]}\n${analysisStatusLabel[task.status]} · ${task.duration_ms === null ? "耗时未记录" : `${task.duration_ms} ms`}`,
      taskId: task.id,
      status: task.status,
    },
    className: `analysis-node analysis-node-${task.status}`,
    ariaLabel: `${task.id} ${analysisRoleLabel[task.role]} ${analysisStatusLabel[task.status]}`,
  }));
  const edges: Edge[] = run.tasks.flatMap((task) => [
    ...(task.parent_id
      ? [
          {
            id: `parent:${task.parent_id}:${task.id}`,
            source: task.parent_id,
            target: task.id,
            label: "父子",
            style: { strokeDasharray: "5 5", stroke: "#978c83" },
            data: { relation: "parent" },
          },
        ]
      : []),
    ...task.dependencies.map((dep) => ({
      id: `dependency:${dep}:${task.id}`,
      source: dep,
      target: task.id,
      label: "依赖",
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { relation: "dependency" },
    })),
  ]);
  return layoutAnalysis(nodes, edges);
}
export interface IssueFilters {
  candidate: string;
  objectionsOnly: boolean;
  stakeholder: string;
}
export function filterIssues(
  run: AnalysisRun,
  filters: IssueFilters,
): IssueNode[] {
  let ids = new Set(run.nodes.map((node) => node.id));
  if (filters.candidate) {
    const candidate = run.candidates.find((c) => c.id === filters.candidate);
    ids = new Set(candidate?.node_ids ?? []);
    // A candidate filter must not hide objections challenging its claims.
    run.edges
      .filter((e) => e.kind === "challenges" && ids.has(e.target))
      .forEach((e) => ids.add(e.source));
  }
  if (filters.stakeholder) {
    ids = new Set(
      run.nodes
        .filter(
          (n) => ids.has(n.id) && n.stakeholders.includes(filters.stakeholder),
        )
        .map((n) => n.id),
    );
    // Objections often have no stakeholder tags of their own. Keep challenges
    // to the matched claims, without pulling in unrelated claims or objections.
    const matched = new Set(ids);
    const objections = new Set(
      run.nodes.filter((n) => n.kind === "objection").map((n) => n.id),
    );
    run.edges
      .filter(
        (e) =>
          e.kind === "challenges" &&
          matched.has(e.target) &&
          objections.has(e.source),
      )
      .forEach((e) => ids.add(e.source));
  }
  if (filters.objectionsOnly) {
    const challenged = new Set<string>();
    run.edges
      .filter(
        (e) =>
          e.kind === "challenges" && ids.has(e.source) && ids.has(e.target),
      )
      .forEach((e) => {
        challenged.add(e.source);
        challenged.add(e.target);
      });
    run.nodes
      .filter((n) => n.kind === "objection" && ids.has(n.id))
      .forEach((n) => challenged.add(n.id));
    ids = challenged;
  }
  return run.nodes.filter((node) => ids.has(node.id));
}
export function issueGraph(
  run: AnalysisRun,
  filters: IssueFilters,
  selectedTask: string,
  selectedIssue: string,
) {
  const visible = filterIssues(run, filters),
    ids = new Set(visible.map((node) => node.id));
  const nodes: AnalysisFlowNode[] = visible.map((node) => ({
    id: node.id,
    position: { x: 0, y: 0 },
    selected: node.id === selectedIssue || node.task_id === selectedTask,
    data: {
      label: `${node.id} · ${node.kind}\n${node.title}`,
      taskId: node.task_id,
    },
    className: `analysis-node ${node.kind === "objection" ? "analysis-node-objection" : ""}`,
    ariaLabel: `${node.id} ${node.title}，产出任务 ${node.task_id}`,
  }));
  const edges: Edge[] = run.edges.flatMap((edge, index) =>
    ids.has(edge.source) && ids.has(edge.target)
      ? [
          {
            id: `issue:${index}:${edge.source}:${edge.target}`,
            source: edge.source,
            target: edge.target,
            label: edge.kind,
            markerEnd: { type: MarkerType.ArrowClosed },
            style:
              edge.kind === "challenges" ? { stroke: "#ff805e" } : undefined,
          },
        ]
      : [],
  );
  return layoutAnalysis(nodes, edges);
}
