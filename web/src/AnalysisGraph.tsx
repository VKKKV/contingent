import { useMemo, useRef, useState } from "react";
import { Background, Controls, ReactFlow } from "@xyflow/react";
import {
  filterIssues,
  issueGraph,
  taskGraph,
  type IssueFilters,
} from "./analysisGraph";
import {
  analysisRoleLabel,
  analysisStatusLabel,
  type AnalysisRun,
  type AnalysisTask,
} from "./analysisTypes";
import "@xyflow/react/dist/style.css";

function Lines({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>未提供</p>
      )}
    </div>
  );
}
export function TaskResult({ task }: { task: AnalysisTask }) {
  if (!task.result)
    return <p>暂无公开结构化结果；排队或失败不代表已完成调用。</p>;
  switch (task.role) {
    case "framing":
      return (
        <>
          <h4>目标</h4>
          <p>{task.result.objective}</p>
          <Lines title="操作标准" items={task.result.criteria} />
          <Lines title="假设" items={task.result.assumptions} />
          <Lines title="未知" items={task.result.unknowns} />
          <Lines title="视角" items={task.result.perspectives} />
          {task.result.clarification && (
            <p>需要澄清：{task.result.clarification}</p>
          )}
        </>
      );
    case "strategy":
    case "revision":
      return (
        <>
          <h4>{task.result.title}</h4>
          <p>{task.result.mechanism}</p>
          <Lines title="前提条件" items={task.result.prerequisites} />
          <Lines title="取舍" items={task.result.tradeoffs} />
          {task.result.claims.map((claim) => (
            <section key={claim.id}>
              <h4>
                {claim.id} · {claim.title} · {claim.kind}
              </h4>
              <p>{claim.detail}</p>
              <Lines title="相关方" items={claim.stakeholders} />
              <Lines title="可观察信号" items={claim.signals} />
            </section>
          ))}
          <Lines
            title="关系"
            items={task.result.links.map(
              (link) => `${link.source} — ${link.kind} → ${link.target}`,
            )}
          />
        </>
      );
    case "critic":
      return (
        <>
          <p>{task.result.limitation}</p>
          {task.result.objections.map((objection, i) => (
            <section key={i}>
              <h4>质疑 {objection.target_claim_id}</h4>
              <p>{objection.concern}</p>
              <p>建议检验：{objection.test}</p>
            </section>
          ))}
          {!task.result.objections.length && (
            <p>未提出质疑，不代表得到事实验证。</p>
          )}
          <p>修订目标：{task.result.revision_task_id || "无"}</p>
        </>
      );
    case "synthesis":
      return (
        <>
          <p>{task.result.summary}</p>
          <Lines title="保留候选" items={task.result.alternatives} />
          <Lines title="未解决问题" items={task.result.unresolved} />
        </>
      );
  }
}
export default function AnalysisGraph({ run }: { run: AnalysisRun }) {
  const [taskId, setTaskId] = useState("");
  const [issueId, setIssueId] = useState("");
  const [filters, setFilters] = useState<IssueFilters>({
    candidate: "",
    objectionsOnly: false,
    stakeholder: "",
  });
  const detail = useRef<HTMLElement>(null);
  const task = run.tasks.find((t) => t.id === taskId);
  const issue = run.nodes.find((n) => n.id === issueId);
  const tasks = useMemo(() => taskGraph(run, taskId), [run, taskId]);
  const issues = useMemo(
    () => issueGraph(run, filters, taskId, issueId),
    [run, filters, taskId, issueId],
  );
  const visible = filterIssues(run, filters);
  const candidate = run.candidates.find((c) => c.id === filters.candidate);
  const stakeholders = [...new Set(run.nodes.flatMap((n) => n.stakeholders))];
  const selectIssue = (id: string) => {
    const node = run.nodes.find((n) => n.id === id);
    if (node) {
      setIssueId(id);
      setTaskId(node.task_id);
    }
  };
  return (
    <div className="analysis-results">
      <section aria-label="执行任务 DAG">
        <h2>执行任务 DAG</h2>
        <p>
          实线箭头：调度依赖 ·
          虚线：父子层级（不等于依赖）。仅展示服务端实际任务。
        </p>
        {run.tasks.length ? (
          <div className="analysis-flow">
            <ReactFlow
              nodes={tasks.nodes}
              edges={tasks.edges}
              onNodeClick={(_, node) => {
                setTaskId(node.id);
                setIssueId("");
              }}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              colorMode="dark"
              minZoom={0.15}
              maxZoom={2}
              attributionPosition="bottom-left"
            >
              <Background />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        ) : (
          <p>尚未创建任务。</p>
        )}
        <ul className="analysis-task-list" aria-label="任务列表">
          {run.tasks.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                aria-pressed={t.id === taskId}
                onClick={() => {
                  setTaskId(t.id);
                  setIssueId("");
                }}
              >
                {t.id} · {analysisRoleLabel[t.role]} ·{" "}
                {analysisStatusLabel[t.status]}
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="议题图">
        <h2>议题图</h2>
        <p>
          选择议题定位产出任务；选择任务高亮其贡献。关系是模型假设，允许反馈环，不代表因果证明。
        </p>
        <div className="analysis-filters">
          <label>
            候选策略
            <select
              aria-label="候选策略"
              value={filters.candidate}
              onChange={(e) => {
                setFilters({ ...filters, candidate: e.target.value });
                setIssueId("");
              }}
            >
              <option value="">全部候选</option>
              {run.candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                  {c.supersedes ? `（修订 ${c.supersedes}）` : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            相关方
            <select
              aria-label="相关方"
              value={filters.stakeholder}
              onChange={(e) =>
                setFilters({ ...filters, stakeholder: e.target.value })
              }
            >
              <option value="">全部相关方</option>
              {stakeholders.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="analysis-check">
            <input
              type="checkbox"
              checked={filters.objectionsOnly}
              onChange={(e) =>
                setFilters({ ...filters, objectionsOnly: e.target.checked })
              }
            />
            仅质疑与受质疑议题
          </label>
        </div>
        {candidate && (
          <div className="analysis-candidate">
            <h3>
              {candidate.title} · {candidate.id}
            </h3>
            <p>{candidate.mechanism}</p>
            <Lines title="前提条件" items={candidate.prerequisites} />
            <Lines title="取舍" items={candidate.tradeoffs} />
            <button
              type="button"
              onClick={() => {
                setTaskId(candidate.task_id);
                detail.current?.focus();
              }}
            >
              定位产出任务 {candidate.task_id}
            </button>
          </div>
        )}
        {issues.nodes.length ? (
          <div className="analysis-flow">
            <ReactFlow
              key={`${filters.candidate}:${filters.objectionsOnly}:${filters.stakeholder}`}
              nodes={issues.nodes}
              edges={issues.edges}
              onNodeClick={(_, node) => selectIssue(node.id)}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              colorMode="dark"
              minZoom={0.15}
              maxZoom={2}
              attributionPosition="bottom-left"
            >
              <Background />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        ) : (
          <p>此筛选下暂无议题。未完成的任务不会生成演示节点。</p>
        )}
        <ul className="analysis-task-list" aria-label="议题列表">
          {visible.map((n) => (
            <li key={n.id}>
              <button
                type="button"
                aria-pressed={n.id === issueId || n.task_id === taskId}
                onClick={() => selectIssue(n.id)}
              >
                {n.title} · {n.task_id}
              </button>
            </li>
          ))}
        </ul>
        {issue && (
          <section className="analysis-issue">
            <h3>
              {issue.id} · {issue.title}
            </h3>
            <p>{issue.detail}</p>
            <p>
              产出任务：{issue.task_id} ·{" "}
              {issue.grounding === "model_objection" ? "模型质疑" : "模型假设"}
            </p>
            <Lines title="相关方" items={issue.stakeholders} />
            <Lines title="可观察信号" items={issue.signals} />
          </section>
        )}
      </section>
      <section
        className="analysis-task-detail"
        ref={detail}
        tabIndex={-1}
        aria-label="任务详情"
      >
        <h2>任务详情</h2>
        {task ? (
          <>
            <h3>
              {task.id} · {analysisRoleLabel[task.role]} ·{" "}
              {analysisStatusLabel[task.status]}
            </h3>
            <dl>
              <dt>父任务</dt>
              <dd>{task.parent_id ?? "无"}</dd>
              <dt>调度依赖</dt>
              <dd>{task.dependencies.join("、") || "无"}</dd>
              <dt>模型</dt>
              <dd>{task.model}</dd>
              <dt>开始 / 结束</dt>
              <dd>
                {task.started_at ?? "未开始"} / {task.finished_at ?? "未结束"}
              </dd>
              <dt>实际耗时</dt>
              <dd>
                {task.duration_ms === null
                  ? "未记录"
                  : `${task.duration_ms} ms`}
              </dd>
              <dt>输出 token</dt>
              <dd>{task.output_tokens ?? "未记录"}</dd>
            </dl>
            <h4>任务简报</h4>
            <p>{task.brief}</p>
            {task.error && <p role="alert">{task.error}</p>}
            <h3>公开结构化结果</h3>
            <TaskResult task={task} />
          </>
        ) : (
          <p>
            选择任务或议题查看简报与结构化结果。不展示隐藏思维链或模拟对话。
          </p>
        )}
      </section>
    </div>
  );
}
