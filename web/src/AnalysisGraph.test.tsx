import {
  Children,
  isValidElement,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { describe, expect, it, vi } from "vitest";
import AnalysisGraph, { AnalysisNode } from "./AnalysisGraph";
import type { AnalysisRun } from "./analysisTypes";
import type { AnalysisFlowNode } from "./analysisGraph";
import type { NodeProps } from "@xyflow/react";

vi.mock("react", async (original) => {
  const react = await original<typeof import("react")>();
  return {
    ...react,
    useState: vi.fn(),
    useMemo: vi.fn(),
    useRef: vi.fn(),
    useContext: vi.fn(),
  };
});

type Props = { children?: ReactNode; [key: string]: unknown };
function elements(tree: ReactNode): React.ReactElement<Props>[] {
  return Children.toArray(tree).flatMap((child) =>
    isValidElement<Props>(child)
      ? [child, ...elements(child.props.children)]
      : [],
  );
}
const filters = { candidate: "", stakeholder: "", objectionsOnly: false };
const run = {
  tasks: [],
  candidates: [],
  edges: [],
  schema_version: "tianji.analysis.v1",
  nodes: [
    {
      id: "one",
      task_id: "task",
      title: "First",
      kind: "claim",
      detail: "first detail",
      stakeholders: ["public"],
      signals: [],
    },
    {
      id: "two",
      task_id: "task",
      title: "Second",
      kind: "claim",
      detail: "second detail",
      stakeholders: ["business"],
      signals: [],
    },
  ],
} as unknown as AnalysisRun;
function renderGraph() {
  vi.resetAllMocks();
  const setTask = vi.fn(),
    setIssue = vi.fn(),
    setFilters = vi.fn(),
    focus = vi.fn();
  vi.mocked(useState)
    .mockReturnValueOnce([false, vi.fn()])
    .mockReturnValueOnce(["task", setTask])
    .mockReturnValueOnce(["one", setIssue])
    .mockReturnValueOnce([filters, setFilters]);
  vi.mocked(useMemo).mockImplementation((factory) => factory());
  vi.mocked(useRef).mockReturnValue({ current: { focus } });
  return {
    nodes: elements(AnalysisGraph({ run })),
    setTask,
    setIssue,
    setFilters,
    focus,
  };
}

describe("analysis canvas interaction", () => {
  it.each([
    ["相关方", { target: { value: "business" } }],
    ["候选策略", { target: { value: "missing" } }],
    ["checkbox", { target: { checked: true } }],
  ])(
    "clears hidden issue and linked detail without moving focus (%s)",
    (label, event) => {
      const view = renderGraph();
      const input = view.nodes.find(
        (n) => n.props["aria-label"] === label || n.props.type === label,
      )!;
      (input.props.onChange as (event: unknown) => void)(event);
      expect(view.setIssue).toHaveBeenCalledWith("");
      expect(view.setTask).toHaveBeenCalledWith("");
      expect(view.focus).not.toHaveBeenCalled();
    },
  );
  it("keeps visible selection and leaves the canvas unkeyed and wheel scrolling available", () => {
    const view = renderGraph();
    const select = view.nodes.find((n) => n.props["aria-label"] === "相关方")!;
    (select.props.onChange as (event: unknown) => void)({
      target: { value: "public" },
    });
    expect(view.setIssue).not.toHaveBeenCalled();
    const flow = view.nodes.find((n) => Array.isArray(n.props.nodes))!;
    expect(flow.key).not.toContain("public");
    expect(flow.props).toMatchObject({
      zoomOnScroll: false,
      preventScrolling: false,
      zoomOnPinch: true,
      nodesFocusable: false,
    });
    const pressed = view.nodes.filter(
      (n) => n.type === "button" && n.props["aria-pressed"] === true,
    );
    expect(pressed).toHaveLength(1);
  });
  it("uses native button activation, suppresses repeat/default bubbling and never steals focus", () => {
    const select = vi.fn();
    vi.mocked(useContext).mockReturnValue(select);
    const tree = AnalysisNode({
      id: "one",
      data: { label: "First", taskId: "task" },
      selected: true,
    } as NodeProps<AnalysisFlowNode>);
    const button = elements(tree).find((n) => n.type === "button")!;
    expect(button.props.type).toBe("button");
    for (const key of ["Enter", " "]) {
      const event = {
        key,
        repeat: false,
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      };
      (button.props.onKeyDown as (event: unknown) => void)(event);
      expect(event.preventDefault).not.toHaveBeenCalled();
      expect(event.stopPropagation).toHaveBeenCalledOnce();
      (button.props.onKeyDown as (event: unknown) => void)({
        ...event,
        repeat: true,
      });
      expect(event.preventDefault).toHaveBeenCalledOnce();
    }
    expect(select).not.toHaveBeenCalled();
    (button.props.onClick as (event: unknown) => void)({
      stopPropagation: vi.fn(),
    });
    expect(select).toHaveBeenCalledExactlyOnceWith("one");
  });
});
