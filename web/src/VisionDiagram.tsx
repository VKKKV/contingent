import { createContext, useContext, useMemo } from "react";
import { ArrowRight, Crosshair, Minus, Plus } from "lucide-react";
import {
  Background,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useViewport,
  type NodeProps,
} from "@xyflow/react";
import type { VisionPlan } from "./api";
import { layoutVision, STAGE_LABELS, type VisionFlowNode } from "./visionGraph";
import "@xyflow/react/dist/style.css";

const SelectNode = createContext<(id: string) => void>(() => {});
function VisionNode({ id, data, selected }: NodeProps<VisionFlowNode>) {
  const select = useContext(SelectNode);
  const handles = (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      {data.stage !== null && (
        <Handle type="source" position={Position.Right} isConnectable={false} />
      )}
    </>
  );
  if (data.stage === null)
    return (
      <div className="vision-goal" data-testid="vision-goal">
        {handles}
        <span>目标方向 · 非保证结果</span>
        <strong>{data.title}</strong>
        <p>{data.subtitle}</p>
      </div>
    );
  return (
    <>
      {handles}
      <button
        type="button"
        className={`vision-node nodrag nopan ${data.active ? "is-active" : ""} ${selected ? "is-selected" : ""}`}
        data-testid={`vision-node-${id}`}
        data-active={data.active}
        aria-pressed={!!selected}
        aria-controls="vision-node-detail"
        onClick={() => select(id)}
      >
        <span className="vision-node-meta">
          <span>
            0{data.stage} · {STAGE_LABELS[data.stage - 1]}
          </span>
          {data.shared && <span className="vision-shared">共用节点</span>}
        </span>
        <strong>{data.title}</strong>
        <span className="vision-node-actors">
          {data.subtitle}
          <ArrowRight size={13} />
        </span>
      </button>
    </>
  );
}
const nodeTypes = { vision: VisionNode };
const MIN_ZOOM = 0.15,
  MAX_ZOOM = 1.4;
function Toolbar() {
  const flow = useReactFlow();
  const { zoom } = useViewport();
  return (
    <div className="vision-map-toolbar">
      <div className="vision-map-direction">
        <span className="vision-live-dot" />
        从近期介入 <ArrowRight size={14} /> 到目标条件
      </div>
      <div className="vision-zoom" role="group" aria-label="图表缩放">
        <button
          type="button"
          aria-label="缩小路径图"
          disabled={zoom <= MIN_ZOOM}
          onClick={() => void flow.zoomOut()}
        >
          <Minus size={15} />
        </button>
        <output aria-label="缩放比例">{Math.round(zoom * 100)}%</output>
        <button
          type="button"
          aria-label="放大路径图"
          disabled={zoom >= MAX_ZOOM}
          onClick={() => void flow.zoomIn()}
        >
          <Plus size={15} />
        </button>
        <button
          type="button"
          data-testid="vision-fit"
          onClick={() => void flow.fitView({ padding: 0.15 })}
        >
          <Crosshair size={14} />
          适应
        </button>
      </div>
    </div>
  );
}
export function VisionDiagram({
  plan,
  activePath,
  selectedNode,
  onSelect,
}: {
  plan: VisionPlan;
  activePath: string;
  selectedNode: string;
  onSelect: (id: string) => void;
}) {
  const graph = useMemo(
    () => layoutVision(plan, activePath, selectedNode),
    [plan, activePath, selectedNode],
  );
  return (
    <section
      className="vision-map"
      aria-label="转折点路径图"
      data-testid="vision-diagram"
    >
      <ReactFlowProvider>
        <Toolbar />
        <SelectNode.Provider value={onSelect}>
          <div
            className="vision-map-viewport"
            data-testid="vision-map-viewport"
            aria-label="可平移缩放的路径图；Tab 聚焦节点，方向键切换节点"
            onKeyDown={(event) => {
              const direction = ["ArrowRight", "ArrowDown"].includes(event.key)
                ? 1
                : ["ArrowLeft", "ArrowUp"].includes(event.key)
                  ? -1
                  : 0;
              if (
                !direction ||
                !(event.target instanceof Element) ||
                !event.target.closest(".vision-node")
              )
                return;
              const buttons = [
                ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
                  "button.vision-node",
                ),
              ];
              const index = buttons.indexOf(
                event.target.closest(".vision-node") as HTMLButtonElement,
              );
              if (index < 0) return;
              event.preventDefault();
              event.stopPropagation();
              const next =
                buttons[(index + direction + buttons.length) % buttons.length];
              next.focus();
              next.click();
            }}
          >
            <ReactFlow
              nodes={graph.nodes}
              edges={graph.edges}
              nodeTypes={nodeTypes}
              nodesDraggable={false}
              nodesConnectable={false}
              nodesFocusable={false}
              edgesFocusable={false}
              deleteKeyCode={null}
              selectionKeyCode={null}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              minZoom={MIN_ZOOM}
              maxZoom={MAX_ZOOM}
              colorMode="dark"
              attributionPosition="bottom-left"
            >
              <Background />
            </ReactFlow>
          </div>
        </SelectNode.Provider>
      </ReactFlowProvider>
      <div className="vision-map-caption">
        <span>
          <i />
          当前路径 <i className="vision-legend-muted" />
          其他条件路径
        </span>
        <span>点选转折点查看机制与风险 · 拖动画布平移，滚轮缩放</span>
      </div>
    </section>
  );
}
