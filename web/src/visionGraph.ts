import dagre from "@dagrejs/dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type { VisionDraft, VisionPlan } from "./api";

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object";
const text = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(text);
/** Reject malformed model output rather than drawing misleading edges or inventing data. */
export function validateVision(value: unknown): asserts value is VisionDraft {
  const invalid = () => {
    throw new Error("模型返回的路径结构无效，未展示或保存。请重新生成。");
  };
  if (
    !record(value) ||
    value.grounding !== "model_hypothesis" ||
    !text(value.model) ||
    !text(value.generated_at) ||
    !record(value.request) ||
    !text(value.request.vision) ||
    !["horizon", "perspective", "constraints"].every(
      (key) =>
        typeof (value.request as Record<string, unknown>)[key] === "string",
    ) ||
    !record(value.plan)
  )
    return invalid();
  const plan = value.plan;
  if (
    !text(plan.title) ||
    !text(plan.interpretation) ||
    !strings(plan.assumptions) ||
    !strings(plan.tensions) ||
    !Array.isArray(plan.nodes) ||
    plan.nodes.length < 4 ||
    plan.nodes.length > 8 ||
    !Array.isArray(plan.paths) ||
    plan.paths.length < 2 ||
    plan.paths.length > 3
  )
    return invalid();
  const stages = new Map<string, number>();
  for (const node of plan.nodes) {
    if (
      !record(node) ||
      !text(node.id) ||
      stages.has(node.id) ||
      !text(node.title) ||
      !Number.isInteger(node.stage) ||
      Number(node.stage) < 1 ||
      Number(node.stage) > 4 ||
      !text(node.action) ||
      !text(node.mechanism) ||
      !["actors", "prerequisites", "risks", "signals"].every(
        (key) =>
          strings(node[key]) && node[key].length >= 1 && node[key].length <= 3,
      )
    )
      return invalid();
    stages.set(node.id, Number(node.stage));
  }
  const ids = new Set<string>();
  const routes: Set<string>[] = [];
  for (const path of plan.paths) {
    if (
      !record(path) ||
      !text(path.id) ||
      ids.has(path.id) ||
      !text(path.title) ||
      !text(path.summary) ||
      !text(path.tradeoff) ||
      !strings(path.node_ids) ||
      path.node_ids.length < 2
    )
      return invalid();
    ids.add(path.id);
    routes.push(new Set(path.node_ids));
    let previous = 0;
    for (const id of path.node_ids) {
      const stage = stages.get(id);
      if (!stage || stage <= previous) return invalid();
      previous = stage;
    }
  }
  if (new Set(routes.flatMap((r) => [...r])).size !== stages.size)
    return invalid();
  for (let i = 0; i < routes.length; i++) {
    const others = new Set(
      routes.filter((_, j) => j !== i).flatMap((r) => [...r]),
    );
    if (![...routes[i]].some((id) => !others.has(id))) return invalid();
  }
}

export const NODE_WIDTH = 204;
export const NODE_HEIGHT = 126;
export const STAGE_LABELS = [
  "近期介入",
  "能力与协作",
  "制度性转折",
  "长期条件",
];
export type VisionFlowNode = Node<{
  title: string;
  subtitle: string;
  stage: number | null;
  active: boolean;
  shared: boolean;
}>;

/** Dagre places domain nodes; React Flow owns edge routing and viewport behavior. */
export function layoutVision(
  plan: VisionPlan,
  activePath = "",
  selectedNode = "",
) {
  let goalId = "__vision_goal__";
  while (plan.nodes.some((node) => node.id === goalId)) goalId += "_";
  const active = new Set(
    plan.paths.find((p) => p.id === activePath)?.node_ids ?? [],
  );
  const nodes: VisionFlowNode[] = plan.nodes.map((node) => ({
    id: node.id,
    type: "vision",
    position: { x: 0, y: 0 },
    selected: node.id === selectedNode,
    data: {
      title: node.title,
      subtitle: node.actors.join(" · "),
      stage: node.stage,
      active: active.has(node.id),
      shared: plan.paths.filter((p) => p.node_ids.includes(node.id)).length > 1,
    },
  }));
  nodes.push({
    id: goalId,
    type: "vision",
    position: { x: 0, y: 0 },
    selectable: false,
    focusable: false,
    data: {
      title: plan.title,
      subtitle: plan.interpretation,
      stage: null,
      active: false,
      shared: false,
    },
  });
  const edges = new Map<string, Edge<{ pathIds: string[] }>>();
  for (const path of plan.paths) {
    const route = [...path.node_ids, goalId];
    for (let i = 1; i < route.length; i++) {
      const source = route[i - 1],
        target = route[i];
      const id = JSON.stringify([source, target]);
      const existing = edges.get(id);
      if (existing) existing.data!.pathIds.push(path.id);
      else edges.set(id, { id, source, target, data: { pathIds: [path.id] } });
    }
  }
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", ranksep: 64, nodesep: 42 });
  graph.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((node) =>
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }),
  );
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return {
    nodes: nodes.map((node) => {
      const point = graph.node(node.id);
      return {
        ...node,
        position: { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 },
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      };
    }),
    edges: [...edges.values()].map((edge) => {
      const highlighted = edge.data!.pathIds.includes(activePath);
      const color = highlighted ? "var(--accent)" : "var(--graph-muted)";
      return {
        ...edge,
        type: "smoothstep",
        selectable: false,
        focusable: false,
        className: highlighted
          ? "vision-route-edge is-active"
          : "vision-route-edge",
        zIndex: highlighted ? 1 : 0,
        style: { stroke: color, strokeWidth: highlighted ? 2.3 : 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color },
      };
    }),
    goalId,
  };
}
