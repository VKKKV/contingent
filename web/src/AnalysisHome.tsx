import { useEffect, useState, useSyncExternalStore } from "react";
import type { VisionRequest } from "./api";
import AnalysisGraph from "./AnalysisGraph";
import VisionHome from "./VisionHome";
import { AnalysisSession, analysisSession, tabRead } from "./analysisSession";
import { analysisActive, analysisStatusLabel } from "./analysisTypes";
import "./analysis.css";

function Workspace({ session }: { session: AnalysisSession }) {
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [token, setToken] = useState(() => tabRead("tianji-token"));
  useEffect(() => {
    session.start();
    const stored = tabRead("tianji-token");
    if (stored) void session.connect(stored);
    return () => session.stop();
  }, [session]);
  const edit = (key: keyof VisionRequest, value: string) =>
    session.edit({ [key]: value });
  const run = state.run;
  return (
    <main className="analysis-home" data-testid="analysis-home">
      <header>
        <span className="analysis-eyebrow">CONTINGENT / DURABLE ANALYSIS</span>
        <h1>目标导向情景分析</h1>
        <p>
          从问题界定、候选策略与质疑审查，到有条件的综合。这里展示真实任务及其公开产出。
        </p>
      </header>
      <aside className="analysis-warning" role="note">
        <strong>模型假设，不是现实验证。</strong>
        同一模型的不同任务不是独立验证，也不是多方共识。图上的关系没有经过现实因果检验；没有自动证据检索。
      </aside>
      <form
        className="analysis-connection"
        onSubmit={(e) => {
          e.preventDefault();
          void session.connect(token);
        }}
      >
        <label>
          本地服务令牌
          <input
            data-testid="analysis-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => {
              session.disconnect();
              setToken(e.target.value);
            }}
          />
        </label>
        <button
          type="submit"
          data-testid="analysis-connect"
          disabled={!token.trim() || state.busy === "connecting"}
        >
          {state.busy === "connecting"
            ? "连接中…"
            : state.connected
              ? "重新连接"
              : "连接服务"}
        </button>
        <span role="status">
          {state.connected ? "已连接 · 令牌仅保留在当前标签页" : "未连接"}
        </span>
      </form>
      {state.connected &&
        !session.supports(
          "analysis_start",
          "analysis_get",
          "analysis_list",
        ) && (
          <p role="alert">
            当前服务未开放持久分析操作。仍可从「旧版单次结果」访问原有项目。
          </p>
        )}
      <form
        className="analysis-editor"
        onSubmit={(e) => {
          e.preventDefault();
          void session.create();
        }}
      >
        <fieldset disabled={state.busy === "creating" || state.pendingStart}>
          <legend>新分析输入</legend>
          <label>
            你希望达成什么目标？
            <textarea
              data-testid="analysis-input"
              required
              maxLength={1200}
              value={state.request.vision}
              onChange={(e) => edit("vision", e.target.value)}
              placeholder="描述目标、受影响的人和待解决的问题"
            />
          </label>
          <div className="analysis-input-row">
            <label>
              时间范围
              <input
                maxLength={100}
                value={state.request.horizon}
                onChange={(e) => edit("horizon", e.target.value)}
              />
            </label>
            <label>
              分析视角
              <input
                maxLength={200}
                value={state.request.perspective}
                onChange={(e) => edit("perspective", e.target.value)}
              />
            </label>
          </div>
          <label>
            现实约束
            <textarea
              maxLength={1000}
              value={state.request.constraints}
              onChange={(e) => edit("constraints", e.target.value)}
            />
          </label>
        </fieldset>
        <p className="analysis-warning">
          点击后立即创建持久项目，保存本次输入、任务状态和校验后的结构化结果；不是临时草稿。不保存原始模型回复或隐藏思维链。关闭此页不会取消服务端运行。
        </p>
        <button
          className="analysis-primary"
          type="submit"
          disabled={
            !!state.busy ||
            !state.request.vision.trim() ||
            !session.supports("analysis_start", "analysis_get", "analysis_list")
          }
        >
          {state.busy === "creating"
            ? "正在创建…"
            : state.pendingStart
              ? "安全重试同一创建请求"
              : "创建并运行分析"}
        </button>
        {state.pendingStart && (
          <p>
            上次创建请求待确认；保留原输入和幂等标识，重试不会另建项目。可先刷新下方列表核对。
          </p>
        )}
      </form>
      {state.error && (
        <p className="analysis-error" role="alert">
          {state.error}
        </p>
      )}
      {state.notice && <p role="status">{state.notice}</p>}
      <section className="analysis-projects" aria-label="持久分析项目">
        <div className="analysis-section-heading">
          <h2>持久分析项目</h2>
          <button
            type="button"
            disabled={!session.supports("analysis_list") || state.listBusy}
            onClick={() => void session.reload()}
          >
            {state.listBusy ? "读取中…" : "刷新项目列表"}
          </button>
        </div>
        {state.listError && <p role="alert">{state.listError}</p>}
        <ul>
          {state.items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={state.selectedId === item.id}
                disabled={
                  !session.supports("analysis_get") ||
                  state.busy === "creating" ||
                  state.busy === "cancelling"
                }
                onClick={() => void session.load(item.id)}
              >
                <strong>{item.request.vision}</strong>
                <span>
                  {analysisStatusLabel[item.status]} · {item.created_at}
                </span>
                <code>{item.id}</code>
              </button>
            </li>
          ))}
        </ul>
        {!state.items.length && (
          <p>
            {state.connected
              ? "服务端列表中暂无项目。"
              : "连接后读取服务端项目；不会展示演示数据。"}
          </p>
        )}
      </section>
      {state.selectedId && (
        <div className="analysis-section-heading">
          <p>
            当前项目 <code>{state.selectedId}</code>
          </p>
          <button
            type="button"
            disabled={!!state.busy || !session.supports("analysis_get")}
            onClick={() => void session.load(state.selectedId)}
          >
            重新读取当前项目
          </button>
        </div>
      )}
      {state.busy === "loading" && <p role="status">正在读取持久分析…</p>}
      {run && (
        <article className="analysis-run" aria-label="当前分析">
          <header>
            <div className="analysis-section-heading">
              <h2>{analysisStatusLabel[run.status]}</h2>
              <button
                type="button"
                disabled={
                  !!state.busy ||
                  !analysisActive(run.status) ||
                  !session.supports("job_cancel")
                }
                onClick={() => void session.cancel()}
              >
                {state.busy === "cancelling" ? "确认取消中…" : "取消此分析"}
              </button>
            </div>
            <h3>{run.request.vision}</h3>
            <p>
              {run.request.horizon} · {run.request.perspective}
            </p>
            <p>约束：{run.request.constraints || "未提供"}</p>
            <p>
              模型调用 {run.calls} / {run.budget.max_calls} · 已记录运行耗时{" "}
              {run.duration_ms} ms · 任务 {run.tasks.length} /{" "}
              {run.budget.max_tasks}
            </p>
            <p>
              预算：{run.budget.max_seconds} 秒 · 输出 token 预留{" "}
              {run.reserved_output_tokens} / {run.budget.max_output_tokens} ·
              最大修订深度 {run.budget.max_revision_depth}
            </p>
            <p>
              创建：{run.created_at} · 结束：{run.finished_at ?? "尚未结束"}
            </p>
            {run.status === "partial" && (
              <p className="analysis-warning">
                部分结果：有任务未成功完成。保留已校验的任务产出，不代表完整分析。
              </p>
            )}
            {run.error && (
              <p className="analysis-error" role="alert">
                {run.error}
              </p>
            )}
            {run.summary && (
              <section>
                <h3>综合摘要</h3>
                <p>{run.summary}</p>
              </section>
            )}
            {run.unresolved.length > 0 && (
              <section>
                <h3>未解决问题</h3>
                <ul>
                  {run.unresolved.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </section>
            )}
          </header>
          <AnalysisGraph key={run.id} run={run} />
        </article>
      )}
    </main>
  );
}
export default function AnalysisHome({
  session = analysisSession,
}: {
  session?: AnalysisSession;
}) {
  const [legacy, setLegacy] = useState(false);
  return (
    <>
      <div className="analysis-tabs" aria-label="分析模式">
        <button
          type="button"
          aria-pressed={!legacy}
          onClick={() => setLegacy(false)}
        >
          持久任务分析
        </button>
        <button
          type="button"
          data-testid="analysis-legacy"
          aria-pressed={legacy}
          onClick={() => setLegacy(true)}
        >
          旧版单次结果
        </button>
      </div>
      {legacy ? (
        <>
          <p className="analysis-legacy-note">
            旧版是单次模型生成与显式保存；已有结果仍可读取。旧结果不转换为任务，也不伪造执行记录。
          </p>
          <VisionHome />
        </>
      ) : (
        <Workspace session={session} />
      )}
    </>
  );
}
