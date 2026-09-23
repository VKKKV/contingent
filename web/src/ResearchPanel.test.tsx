import { Children, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import ResearchPanel, {
  Citations,
  citationText,
  safeResearchUrl,
} from "./ResearchPanel";
import { defaultResearchOptions, type AnalysisRunV2 } from "./analysisTypes";

// Synthetic hostile evidence is confined to tests, never a product fallback.
function fixture(): AnalysisRunV2 {
  return {
    id: "test",
    schema_version: "tianji.analysis.v2",
    status: "partial",
    request: { vision: "test", horizon: "", perspective: "", constraints: "" },
    budget: {
      max_calls: 8,
      max_seconds: 60,
      max_output_tokens: 1000,
      max_tasks: 8,
      max_revision_depth: 1,
    },
    created_at: "test-time",
    finished_at: null,
    nodes: [],
    edges: [],
    candidates: [],
    summary: "",
    unresolved: [],
    calls: 1,
    reserved_output_tokens: 100,
    duration_ms: 1,
    error: null,
    architecture: "bounded_same_model_agents",
    tasks: [
      {
        id: "synthesis",
        role: "synthesis",
        parent_id: null,
        dependencies: [],
        brief: "",
        status: "succeeded",
        model: "test",
        started_at: null,
        finished_at: null,
        duration_ms: 1,
        output_tokens: 10,
        error: null,
        result: {
          summary: "<script>claimed()</script>",
          alternatives: [],
          unresolved: ["unknown"],
        },
      },
    ],
    research_options: defaultResearchOptions(),
    research: {
      status: "partial",
      queries: ["test query"],
      hits: [
        {
          title: "<img src=x>",
          url: "javascript:alert(1)",
          snippet: "search snippet",
        },
      ],
      sources: [
        {
          id: "source_1",
          title: "<svg onload=evil()>",
          url: "https://example.org/article",
          resolved_url: "https://example.org/article",
          publisher: "test",
          published_at: null,
          retrieved_at: "retrieval-time",
          text: "<img src=https://evil.invalid/pixel> quoted text",
          text_sha256: "test-hash",
          extractor: "test-only",
          origin: "public_web",
        },
      ],
      passages: [
        {
          id: "source_1_p1",
          source_id: "source_1",
          start: 36,
          end: 47,
          quote: "quoted text",
        },
      ],
      errors: ["fetch_failed"],
      queries_used: 1,
      pages_used: 2,
      fetched_bytes: 400,
      started_at: "start-time",
      finished_at: "finish-time",
    },
    citations: [
      {
        task_id: "synthesis",
        target: "/summary",
        passage_id: "source_1_p1",
        relation: "challenge",
        epistemic: "inference",
      },
    ],
    task_passages: { synthesis: ["source_1_p1"] },
  };
}
describe("stored research evidence", () => {
  it.each([
    "javascript:alert(1)",
    "data:text/html,test",
    "//evil.invalid",
    "/local",
    "https://user:secret@example.org",
    "https://example.org/\npath",
    "https:\\evil.invalid",
    "file:///etc/passwd",
  ])("rejects unsafe link %s", (url) => {
    expect(safeResearchUrl(url)).toBeNull();
  });
  it("allows only absolute credential-free HTTP(S) links", () => {
    expect(safeResearchUrl("https://example.org/a?q=test")).toBe(
      "https://example.org/a?q=test",
    );
    expect(safeResearchUrl("http://example.org/a")).toBe(
      "http://example.org/a",
    );
  });
  it("renders hostile source, snippets and model text inertly without remote embeds", () => {
    const html = renderToStaticMarkup(
      <ResearchPanel
        run={fixture()}
        selectedPassage="source_1_p1"
        onPassage={() => {}}
      />,
    );
    expect(html).not.toMatch(/<(script|img|svg|iframe)\b/);
    expect(html).not.toContain('href="javascript:');
    expect(html).toContain("&lt;script&gt;claimed()&lt;/script&gt;");
    expect(html).toContain("&lt;img src=https://evil.invalid/pixel&gt;");
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('referrerPolicy="no-referrer"');
    expect(html).toContain("搜索摘要（非正文）");
    expect(html).toContain("完整留存正文");
    expect(html).toContain("retrieval-time");
    expect(html).toContain("test-hash");
    expect(html).toContain("未核实");
    expect(html).toContain("分析推断 · 质疑");
    expect(html).toContain("/summary");
    expect(html).toContain("quoted text");
    expect(html).toContain("fetch_failed");
    expect(html).toContain("调查不完整");
  });
  it("resolves only existing string targets in task results", () => {
    const result = fixture().tasks[0].result;
    expect(citationText(result, "/summary")).toBe("<script>claimed()</script>");
    expect(citationText(result, "/unresolved/0")).toBe("unknown");
    for (const pointer of [
      "summary",
      "/unresolved",
      "/unresolved/1",
      "/constructor",
      "/__proto__/test",
      "/bad~2escape",
    ])
      expect(citationText(result, pointer)).toBeNull();
  });
  it("citation button navigates to its saved passage and unseen citations are disabled", () => {
    const run = fixture();
    const onPassage = vi.fn();
    type Props = {
      children?: ReactNode;
      onClick?: () => void;
      disabled?: boolean;
    };
    const flatten = (node: ReactNode): React.ReactElement<Props>[] =>
      Children.toArray(node).flatMap((child) =>
        isValidElement<Props>(child)
          ? [child, ...flatten(child.props.children)]
          : [],
      );
    let button = flatten(Citations({ run, onPassage })).find(
      (e) => e.type === "button",
    )!;
    expect(button.props.disabled).toBe(false);
    button.props.onClick!();
    expect(onPassage).toHaveBeenCalledWith("source_1_p1");
    run.task_passages = {};
    button = flatten(Citations({ run, onPassage })).find(
      (e) => e.type === "button",
    )!;
    expect(button.props.disabled).toBe(true);
  });
  it("reports offline and absent evidence honestly", () => {
    const run = fixture();
    run.research_options.mode = "offline";
    run.research.status = "skipped";
    run.research.sources = [];
    run.research.passages = [];
    run.citations = [];
    const html = renderToStaticMarkup(
      <ResearchPanel run={run} selectedPassage="" onPassage={() => {}} />,
    );
    expect(html).toContain("显式离线");
    expect(html).toContain("暂无原文引用");
    expect(html).toContain("尚无已读取并保存的公开正文");
    expect(html).toContain("重新打开项目不会刷新来源");
  });
});
