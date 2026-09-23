import { useEffect, useRef } from "react";
import type {
  AnalysisRunV2,
  AnalysisTask,
  ResearchState,
} from "./analysisTypes";

/** No Markdown/HTML rendering or remote embeds; only explicit user-opened links. */
export function safeResearchUrl(value: string): string | null {
  if (!/^https?:\/\//i.test(value) || /[\s\u0000-\u001f\u007f\\]/u.test(value))
    return null;
  try {
    const url = new URL(value);
    return (url.protocol === "https:" || url.protocol === "http:") &&
      !url.username &&
      !url.password &&
      !!url.hostname
      ? url.href
      : null;
  } catch {
    return null;
  }
}
export function SourceLink({ url, label }: { url: string; label?: string }) {
  const href = safeResearchUrl(url);
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      referrerPolicy="no-referrer"
    >
      {label ?? url}
    </a>
  ) : (
    <span>{label ?? url}（链接不可打开）</span>
  );
}
/** Resolve only own JSON fields. A pointer never becomes code or a DOM selector. */
export function citationText(
  result: AnalysisTask["result"],
  pointer: string,
): string | null {
  if (!pointer.startsWith("/") || /~(?![01])/u.test(pointer)) return null;
  let value: unknown = result;
  for (const part of pointer.slice(1).split("/")) {
    const key = part.replace(/~1/g, "/").replace(/~0/g, "~");
    if (!value || typeof value !== "object" || !Object.hasOwn(value, key))
      return null;
    value = (value as Record<string, unknown>)[key];
  }
  return typeof value === "string" ? value : null;
}
const epistemicLabels = {
  source_statement: "来源陈述",
  inference: "分析推断",
  assumption: "情景假设",
};
const relationLabels = { support: "支持", challenge: "质疑", context: "背景" };
const researchLabels: Record<ResearchState["status"], string> = {
  not_started: "尚未开始",
  running: "调查中",
  succeeded: "检索读取已完成",
  partial: "调查不完整",
  failed: "调查失败",
  cancelled: "已取消",
  interrupted: "已中断",
  skipped: "已跳过（离线）",
};
export function Citations({
  run,
  taskId,
  onPassage,
}: {
  run: AnalysisRunV2;
  taskId?: string;
  onPassage: (id: string) => void;
}) {
  const citations = run.citations.filter(
    (c) => !taskId || c.task_id === taskId,
  );
  return (
    <section
      className="analysis-citations"
      aria-label={taskId ? "任务引用" : "判断与原文引用"}
    >
      <h3>{taskId ? "任务引用" : "判断与原文引用"}</h3>
      <p>
        来源陈述、分析推断、情景假设是表述类型，不是真实性认证。引用存在不等于支持充分或因果成立。
      </p>
      {!citations.length && <p>暂无原文引用；不能视为已获公开证据支持。</p>}
      <ul>
        {citations.map((c, i) => {
          const task = run.tasks.find((t) => t.id === c.task_id);
          const text = task ? citationText(task.result, c.target) : null;
          const passage = run.research.passages.find(
            (p) => p.id === c.passage_id,
          );
          const visible = run.task_passages[c.task_id]?.includes(c.passage_id);
          return (
            <li key={`${c.task_id}:${c.target}:${c.passage_id}:${i}`}>
              <p>
                <strong>
                  {epistemicLabels[c.epistemic]} · {relationLabels[c.relation]}
                </strong>{" "}
                · {c.task_id} <code>{c.target}</code>
              </p>
              <p>{text ?? "引用目标不可读"}</p>
              <button
                type="button"
                disabled={!passage || !visible || text === null}
                onClick={() => onPassage(c.passage_id)}
              >
                查看原文片段 {c.passage_id}
              </button>
              {(!passage || !visible) && (
                <p>片段缺失或不在该任务可见范围，不能追溯此引用。</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
export default function ResearchPanel({
  run,
  selectedPassage,
  onPassage,
}: {
  run: AnalysisRunV2;
  selectedPassage: string;
  onPassage: (id: string) => void;
}) {
  const { research, research_options: options } = run;
  const passage = research.passages.find((p) => p.id === selectedPassage);
  const source = research.sources.find((s) => s.id === passage?.source_id);
  const passageDetail = useRef<HTMLElement>(null);
  useEffect(() => {
    if (passage) passageDetail.current?.focus();
  }, [selectedPassage, passage?.id]);
  return (
    <section className="analysis-research" aria-label="公开情报与来源">
      <h2>公开情报与来源</h2>
      <p role="status">
        {options.mode === "online" ? "在线调查" : "显式离线"} ·{" "}
        {researchLabels[research.status]}
      </p>
      <p>
        外发查询尝试 {research.queries_used} / {options.budget.max_queries} ·
        网页读取尝试 {research.pages_used} / {options.budget.max_pages} ·
        已保存正文 {research.sources.length} · 原文片段{" "}
        {research.passages.length}
      </p>
      <p>
        公共网页获取流量 {research.fetched_bytes} /{" "}
        {options.budget.max_total_bytes} 字节 · 单响应上限{" "}
        {options.budget.max_response_bytes} 字节 · 调查时间上限{" "}
        {options.budget.max_seconds} 秒。流量计数不包含搜索服务网络流量。
      </p>
      <p>
        开始：{research.started_at ?? "未开始"} · 结束：
        {research.finished_at ?? "未结束"}
      </p>
      {(research.status !== "succeeded" || !run.citations.length) && (
        <p className="analysis-warning">
          证据缺口：调查未完整完成或尚无带引用的产出。保留已有结果，不用纯模型回答冒充已调查结论。
        </p>
      )}
      {options.mode === "offline" && (
        <p>此项目不检索公开网页；模型假设未通过在线调查。</p>
      )}
      {research.errors.length > 0 && (
        <ul aria-label="调查错误">
          {research.errors.map((error, i) => (
            <li key={i}>{error}</li>
          ))}
        </ul>
      )}
      <details>
        <summary>
          检索问题与命中（{research.queries.length} / {research.hits.length}）
        </summary>
        <p>查询计划不等于已执行；命中摘要不是已读取正文，也不是可引用原文。</p>
        <ol>
          {research.queries.map((query, i) => (
            <li key={i}>{query}</li>
          ))}
        </ol>
        <ul>
          {research.hits.map((hit, i) => (
            <li key={i}>
              <SourceLink url={hit.url} label={hit.title || hit.url} />
              <p>搜索摘要（非正文）：{hit.snippet}</p>
            </li>
          ))}
        </ul>
      </details>
      <Citations run={run} onPassage={onPassage} />
      {passage && source && (
        <section
          ref={passageDetail}
          tabIndex={-1}
          className="analysis-passage"
          aria-label="所选原文片段"
        >
          <h3>
            {passage.id} · {source.title}
          </h3>
          <blockquote>{passage.quote}</blockquote>
          <p>
            正文字符范围 [{passage.start}, {passage.end}) · 来源 {source.id}
          </p>
          <SourceLink url={source.url} />
          <details key={passage.id}>
            <summary>展开此来源的完整留存正文</summary>
            <pre>{source.text}</pre>
          </details>
        </section>
      )}
      <h3>已保存来源快照</h3>
      <p>
        仅显示本次留存的有界提取正文，不是网页全文档案。重新打开项目不会刷新来源；外链仅在你主动打开时访问。
      </p>
      {!research.sources.length && (
        <p>尚无已读取并保存的公开正文。不会用搜索摘要替代来源。</p>
      )}
      {research.sources.map((s) => (
        <details key={s.id} className="analysis-source">
          <summary>
            {s.title || s.id} · {s.id}
          </summary>
          <p>
            发布方：{s.publisher || "未确认"} · 发布时间：
            {s.published_at ?? "未核实"}
          </p>
          <p>
            获取时间：{s.retrieved_at} · 提取器：{s.extractor} · 公开网页
          </p>
          <p>
            原始链接：
            <SourceLink url={s.url} />
          </p>
          <p>
            最终链接：
            <SourceLink url={s.resolved_url} />
          </p>
          <p>
            正文 SHA-256：<code>{s.text_sha256}</code>
            （完整性标识，不是真实性认证）
          </p>
          <ul>
            {research.passages
              .filter((p) => p.source_id === s.id)
              .map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => onPassage(p.id)}>
                    查看原文片段 {p.id}
                  </button>
                </li>
              ))}
          </ul>
          <h4>完整留存正文（可能截断）</h4>
          <pre>{s.text}</pre>
        </details>
      ))}
    </section>
  );
}
