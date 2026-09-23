import { useEffect, useState, useSyncExternalStore } from "react";
import type { VisionRequest } from "./api";
import AnalysisGraph from "./AnalysisGraph";
import ResearchPanel from "./ResearchPanel";
import VisionHome from "./VisionHome";
import { AnalysisSession, analysisSession, tabRead } from "./analysisSession";
import {
  analysisActive,
  analysisStatusLabel,
  type AnalysisRun,
} from "./analysisTypes";
export function AnalysisResults({ run }: { run: AnalysisRun }) {
  const [passage, setPassage] = useState("");
  const [view, setView] = useState<"paths" | "sources">("paths");
  const openPassage = (id: string) => {
    setPassage(id);
    setView("sources");
  };
  return (
    <>
      <div
        className="analysis-view-switch"
        role="group"
        aria-label="分析结果视图"
      >
        <button
          type="button"
          aria-pressed={view === "paths"}
          onClick={() => setView("paths")}
        >
          世界线与路径
        </button>
        {run.schema_version === "tianji.analysis.v2" && (
          <button
            type="button"
            aria-pressed={view === "sources"}
            onClick={() => setView("sources")}
          >
            情报与引用 · {run.research.sources.length} 来源
          </button>
        )}
      </div>
      <div hidden={view !== "paths"}>
        <AnalysisGraph run={run} onPassage={openPassage} />
      </div>
      {run.schema_version === "tianji.analysis.v2" ? (
        view === "sources" && (
          <ResearchPanel
            run={run}
            selectedPassage={passage}
            onPassage={setPassage}
          />
        )
      ) : (
        <p className="analysis-warning">
          旧版 v1 离线项目：未执行自动公开情报检索。重新读取不会升级或联网调查。
        </p>
      )}
    </>
  );
}
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
        同一模型的不同任务不是独立验证，也不是多方共识。在线调查可提供可追溯来源，但不证明判断真实或图上关系具有因果效力。
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
      {state.connected && !session.canCreate() && (
        <p role="alert">
          当前服务未开放持久分析操作。仍可从「旧版单次结果」访问原有项目。
        </p>
      )}
      {state.connected && !session.supports("analysis_start_v2") && (
        <p className="analysis-warning">
          当前服务仅支持旧版离线兼容分析，不会联网检索。升级服务后才能创建在线调查。
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
            调查模式
            <select
              aria-label="调查模式"
              value={
                session.startOperation() === "analysis_start" && state.connected
                  ? "legacy"
                  : state.research.mode
              }
              disabled={
                state.connected && session.startOperation() === "analysis_start"
              }
              onChange={(e) =>
                session.editResearch({
                  mode: e.target.value as "online" | "offline",
                })
              }
            >
              <option value="online">在线调查（默认）</option>
              <option value="offline">离线分析（不检索公开网页）</option>
              {state.connected &&
                session.startOperation() === "analysis_start" && (
                  <option value="legacy">旧版 v1 离线兼容</option>
                )}
            </select>
          </label>
          <p>只需填写目标，无需上传材料。当前版本不支持补充材料附件。</p>
          <p className="analysis-warning">
            在线模式会根据目标、视角和约束生成查询并发送到公开搜索服务，再访问公开网页；请勿输入私密资料。查询、搜索摘要、有界提取正文与片段、来源链接、时间及哈希随项目保存在本地，不保存网页脚本或图片。离线模式不执行这些检索。
          </p>
          <details>
            <summary>调查预算</summary>
            <p>按顺序读取少量公开来源；无登录、Cookie 或自定义网址输入。</p>
            <div className="analysis-input-row">
              <label>
                最多查询数（1–3）
                <input
                  type="number"
                  min={1}
                  max={3}
                  value={state.research.budget.max_queries}
                  onChange={(e) =>
                    session.editResearch({
                      budget: { max_queries: Number(e.target.value) },
                    })
                  }
                />
              </label>
              <label>
                最多网页数（1–5）
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={state.research.budget.max_pages}
                  onChange={(e) =>
                    session.editResearch({
                      budget: { max_pages: Number(e.target.value) },
                    })
                  }
                />
              </label>
              <label>
                调查秒数（5–180）
                <input
                  type="number"
                  min={5}
                  max={180}
                  value={state.research.budget.max_seconds}
                  onChange={(e) =>
                    session.editResearch({
                      budget: { max_seconds: Number(e.target.value) },
                    })
                  }
                />
              </label>
            </div>
            <p>
              公共网页单响应上限 {state.research.budget.max_response_bytes}{" "}
              字节；累计 {state.research.budget.max_total_bytes}{" "}
              字节。不包含搜索服务网络流量。
            </p>
          </details>
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
            !!state.busy || !state.request.vision.trim() || !session.canCreate()
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
            上次创建请求待确认；原输入、操作版本、调查模式、预算和幂等标识均已锁定，重试不会另建项目或切换联网方式。可先刷新下方列表核对。
            {state.pendingOperation === "analysis_start" &&
              " 此请求为旧版 v1 离线请求，绝不会自动升级为在线调查。"}
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
            disabled={
              !session.supports(session.listOperation()) || state.listBusy
            }
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
                部分结果：任务、调查或引用依据存在缺口。保留已校验的任务产出，不代表完整分析。
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
          <AnalysisResults key={run.id} run={run} />
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
