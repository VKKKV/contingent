import { describe, expect, it } from "vitest";
import {
  filterIssues,
  issueGraph,
  taskGraph,
  type IssueFilters,
} from "./analysisGraph";
import type { AnalysisRun, AnalysisTask, IssueNode } from "./analysisTypes";

const filters: IssueFilters = {
  candidate: "",
  objectionsOnly: false,
  stakeholder: "",
};
function task(
  id: string,
  parent_id: string | null = null,
  dependencies: string[] = [],
): AnalysisTask {
  return {
    id,
    parent_id,
    dependencies,
    role: "strategy",
    result: null,
    brief: "",
    status: "succeeded",
    model: "test-model",
    started_at: null,
    finished_at: null,
    duration_ms: 12,
    output_tokens: null,
    error: null,
  };
}
function node(
  id: string,
  task_id: string,
  kind: IssueNode["kind"] = "claim",
  stakeholders = ["public"],
): IssueNode {
  return {
    id,
    task_id,
    kind,
    title: id,
    detail: "",
    grounding: kind === "objection" ? "model_objection" : "model_hypothesis",
    stakeholders,
    signals: [],
  };
}
function run(): AnalysisRun {
  return {
    id: "test-run",
    schema_version: "tianji.analysis.v1",
    status: "succeeded",
    request: {
      vision: "test intent",
      horizon: "",
      perspective: "",
      constraints: "",
    },
    budget: {
      max_calls: 8,
      max_seconds: 60,
      max_output_tokens: 1000,
      max_tasks: 8,
      max_revision_depth: 1,
    },
    created_at: "2026-01-01T00:00:00Z",
    finished_at: null,
    tasks: [task("strategy"), task("critic", "strategy", ["strategy"])],
    nodes: [
      node("claim", "strategy"),
      node("outcome", "strategy", "outcome"),
      node("objection", "critic", "objection"),
      node("unrelated", "other", "claim", ["business"]),
      node("isolated-objection", "other", "objection", ["business"]),
    ],
    edges: [
      { source: "claim", target: "outcome", kind: "supports" },
      { source: "outcome", target: "claim", kind: "may-influence" },
      { source: "objection", target: "claim", kind: "challenges" },
    ],
    candidates: [
      {
        id: "candidate",
        task_id: "strategy",
        title: "Candidate",
        mechanism: "",
        node_ids: ["claim", "outcome"],
        prerequisites: [],
        tradeoffs: [],
        supersedes: null,
      },
    ],
    summary: "",
    unresolved: [],
    calls: 0,
    reserved_output_tokens: 0,
    duration_ms: 0,
    error: null,
    architecture: "bounded_same_model_agents",
  };
}

describe("analysis graphs", () => {
  it("lays out cyclic issue feedback without dropping or rewriting edges", () => {
    const input = run();
    const before = structuredClone(input);
    const graph = issueGraph(input, filters, "", "");
    expect(
      graph.edges.map(({ source, target, label }) => ({
        source,
        target,
        kind: label,
      })),
    ).toEqual(input.edges);
    expect(graph.nodes).toHaveLength(input.nodes.length);
    for (const item of graph.nodes) {
      expect(Number.isFinite(item.position.x)).toBe(true);
      expect(Number.isFinite(item.position.y)).toBe(true);
    }
    expect(
      new Set(graph.nodes.map((item) => JSON.stringify(item.position))).size,
    ).toBe(graph.nodes.length);
    expect(input).toEqual(before);
  });

  it("preserves source-task links and selects issues by source task or issue ID", () => {
    const input = run();
    const graph = issueGraph(input, filters, "strategy", "objection");
    expect(
      graph.nodes.filter((item) => item.selected).map((item) => item.id),
    ).toEqual(["claim", "outcome", "objection"]);
    for (const item of graph.nodes) {
      expect(item.data.taskId).toBe(
        input.nodes.find((source) => source.id === item.id)!.task_id,
      );
      expect(item.ariaLabel).toContain(item.data.taskId);
    }
  });

  it("keeps distinct parent and dependency edges for the same task endpoints", () => {
    const graph = taskGraph(run(), "critic");
    expect(graph.edges.map((edge) => edge.data?.relation)).toEqual([
      "parent",
      "dependency",
    ]);
    expect(new Set(graph.edges.map((edge) => edge.id)).size).toBe(2);
    expect(graph.nodes.find((item) => item.id === "critic")).toMatchObject({
      selected: true,
      data: { taskId: "critic", status: "succeeded" },
    });
    expect(
      graph.nodes.find((item) => item.id === "critic")!.position.x,
    ).toBeGreaterThan(
      graph.nodes.find((item) => item.id === "strategy")!.position.x,
    );
  });

  it("retains objections against candidate claims and excludes unrelated issues", () => {
    expect(
      filterIssues(run(), { ...filters, candidate: "candidate" }).map(
        (item) => item.id,
      ),
    ).toEqual(["claim", "outcome", "objection"]);
    expect(filterIssues(run(), { ...filters, candidate: "missing" })).toEqual(
      [],
    );
  });

  it("shows challenged claims and isolated objections in objections-only mode", () => {
    expect(
      filterIssues(run(), { ...filters, objectionsOnly: true }).map(
        (item) => item.id,
      ),
    ).toEqual(["claim", "objection", "isolated-objection"]);
    const graph = issueGraph(
      run(),
      { ...filters, candidate: "candidate", objectionsOnly: true },
      "",
      "",
    );
    expect(graph.nodes.map((item) => item.id)).toEqual(["claim", "objection"]);
    expect(graph.edges.map((item) => item.label)).toEqual(["challenges"]);
    const ids = new Set(graph.nodes.map((item) => item.id));
    expect(
      graph.edges.every((edge) => ids.has(edge.source) && ids.has(edge.target)),
    ).toBe(true);
  });

  it("intersects stakeholder and candidate filters without dangling edges", () => {
    const graph = issueGraph(
      run(),
      { ...filters, stakeholder: "business" },
      "",
      "",
    );
    expect(graph.nodes.map((item) => item.id)).toEqual([
      "unrelated",
      "isolated-objection",
    ]);
    expect(graph.edges).toEqual([]);
    expect(
      filterIssues(run(), {
        ...filters,
        candidate: "candidate",
        stakeholder: "business",
      }),
    ).toEqual([]);
  });

  it.each(["", "candidate"])(
    "keeps untagged objections against stakeholder-matched claims (candidate=%s)",
    (candidate) => {
      const input = run();
      input.nodes.find((item) => item.id === "objection")!.stakeholders = [];
      input.nodes.push(node("other-objection", "other", "objection", []));
      input.edges.push({
        source: "other-objection",
        target: "unrelated",
        kind: "challenges",
      });
      const before = structuredClone(input);
      const graph = issueGraph(
        input,
        { candidate, stakeholder: "public", objectionsOnly: true },
        "",
        "",
      );
      expect(graph.nodes.map((item) => item.id)).toEqual([
        "claim",
        "objection",
      ]);
      expect(
        graph.edges.map(({ source, target }) => ({ source, target })),
      ).toEqual([{ source: "objection", target: "claim" }]);
      expect(
        filterIssues(input, {
          candidate,
          stakeholder: "missing",
          objectionsOnly: true,
        }),
      ).toEqual([]);
      expect(input).toEqual(before);
    },
  );

  it("accepts an empty graph while a run is queued", () => {
    const input = { ...run(), tasks: [], nodes: [], edges: [], candidates: [] };
    expect(taskGraph(input, "")).toEqual({ nodes: [], edges: [] });
    expect(issueGraph(input, filters, "", "")).toEqual({
      nodes: [],
      edges: [],
    });
  });
});
