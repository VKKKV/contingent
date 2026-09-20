import { useEffect, useState, useSyncExternalStore } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Check,
  ChevronDown,
  GitBranch,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Unplug,
} from "lucide-react";
import { VisionSession } from "./visionSession";
import { VisionDiagram } from "./VisionDiagram";
import type { VisionDraft } from "./api";

const EXAMPLE = "促进 AI 发展，实现世界和平";
function storedToken() {
  try {
    return sessionStorage.getItem("tianji-token") ?? "";
  } catch {
    return "";
  }
}
function DetailsList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="vision-detail-section">
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="vision-muted">模型未列出，仍需进一步明确。</p>
      )}
    </section>
  );
}
function Result({
  draft,
  session,
  saved,
  busy,
}: {
  draft: VisionDraft;
  session: VisionSession;
  saved: boolean;
  busy: string | null;
}) {
  const [pathId, setPathId] = useState(draft.plan.paths[0].id);
  const [nodeId, setNodeId] = useState(draft.plan.paths[0].node_ids[0]);
  const path =
    draft.plan.paths.find((p) => p.id === pathId) ?? draft.plan.paths[0];
  const node =
    draft.plan.nodes.find((n) => n.id === nodeId) ?? draft.plan.nodes[0];
  return (
    <section
      className="vision-result"
      data-testid="vision-result"
      aria-label="目标推演结果"
    >
      <div className="vision-result-heading">
        <div>
          <span className="vision-eyebrow">
            CONDITIONAL PATHWAYS / 条件路径
          </span>
          <h2>{draft.plan.title}</h2>
        </div>
        <button
          type="button"
          data-testid="vision-save"
          disabled={
            !!busy ||
            saved ||
            !session.supports("vision_save", "vision_get", "vision_list")
          }
          onClick={() => void session.save()}
        >
          {saved ? <Check size={15} /> : <Bookmark size={15} />}
          {saved
            ? "已保存并读回"
            : busy === "saving"
              ? "保存并核对中…"
              : "保存项目"}
        </button>
      </div>
      <div className="vision-grounding">
        <span className="vision-hypothesis" data-testid="vision-grounding">
          模型假设 · 尚未验证
        </span>
        <p>这些路径用于发现值得检验的条件，不是事实证据、预测或成功保证。</p>
      </div>
      {!session.supports("vision_save", "vision_get", "vision_list") && (
        <p className="vision-muted">
          当前服务未开放完整项目保存能力，草稿仅保留在本页。
        </p>
      )}
      <p className="vision-interpretation">{draft.plan.interpretation}</p>
      <div className="vision-route-tabs" role="group" aria-label="选择条件路径">
        {draft.plan.paths.map((p, index) => (
          <button
            type="button"
            key={p.id}
            data-testid={`vision-route-${p.id}`}
            aria-pressed={path.id === p.id}
            onClick={() => {
              setPathId(p.id);
              if (!p.node_ids.includes(nodeId)) setNodeId(p.node_ids[0]);
            }}
          >
            <span>0{index + 1}</span>
            {p.title}
            <ArrowUpRight size={15} />
          </button>
        ))}
      </div>
      <div className="vision-route-summary" data-testid="vision-route-detail">
        <div>
          <strong>{path.title}</strong>
          <p>{path.summary}</p>
        </div>
        <div className="vision-tradeoff">
          <span>这条路的取舍</span>
          <p>{path.tradeoff}</p>
        </div>
      </div>
      <VisionDiagram
        plan={draft.plan}
        activePath={path.id}
        selectedNode={node.id}
        onSelect={setNodeId}
      />
      <div className="vision-analysis-grid">
        <section
          id="vision-node-detail"
          className="vision-node-detail"
          data-testid="vision-node-detail"
          aria-label="转折点详情"
          aria-live="polite"
        >
          <div className="vision-detail-heading">
            <span className="vision-eyebrow">转折点 / 0{node.stage}</span>
            <h2>{node.title}</h2>
          </div>
          <div className="vision-actors">
            <span>行动主体</span>
            {node.actors.length ? node.actors.join(" · ") : "待明确"}
          </div>
          <div className="vision-mechanism">
            <section>
              <h3>关键行动</h3>
              <p>{node.action}</p>
            </section>
            <section>
              <h3>为什么可能推动转折</h3>
              <p>{node.mechanism}</p>
            </section>
          </div>
          <div className="vision-detail-lists">
            <DetailsList title="必要前提" items={node.prerequisites} />
            <DetailsList title="风险与阻力" items={node.risks} />
            <DetailsList title="待观察信号 · 非已获证据" items={node.signals} />
          </div>
        </section>
        <aside className="vision-assumptions">
          <span className="vision-eyebrow">保持怀疑 / KEEP QUESTIONING</span>
          <DetailsList
            title="这张图依赖的假设"
            items={draft.plan.assumptions}
          />
          <DetailsList title="不能跳过的张力" items={draft.plan.tensions} />
          <p className="vision-provenance">
            模型：{draft.model}
            <br />
            生成时间：{draft.generated_at}
          </p>
        </aside>
      </div>
    </section>
  );
}

export default function VisionHome() {
  const [session] = useState(() => new VisionSession());
  const state = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const [token, setToken] = useState(storedToken);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    session.start();
    return () => session.stop();
  }, [session]);
  useEffect(() => {
    if (!state.startedAt) {
      setElapsed(0);
      return;
    }
    const start = state.startedAt;
    const tick = () =>
      setElapsed(Math.min(180, Math.floor((Date.now() - start) / 1000)));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [state.startedAt]);
  const generating = state.busy === "generating";
  return (
    <main className="vision-home" data-testid="vision-home">
      <section className="vision-intro">
        <div className="vision-intro-copy">
          <span className="vision-eyebrow">
            <GitBranch size={14} />
            目标导向情景分析 / SCENARIO ANALYSIS
          </span>
          <h1>
            明确目标，
            <br className="vision-mobile-break" />
            <em>分析干预路径</em>
          </h1>
          <p>
            定义目标状态与约束，识别可能影响结果的关键条件，
            <br className="vision-desktop-break" />
            比较候选路径的前提、风险与权衡。
          </p>
        </div>
        <div className="vision-intro-note">
          <span>方法边界</span>
          <strong>
            模型生成的
            <br />
            待验证假设。
          </strong>
          <div className="vision-mini-line" aria-hidden="true">
            <i />
            <b />
            <i />
            <b />
            <i />
          </div>
        </div>
      </section>
      <div className="vision-compose-grid">
        <section className="vision-composer" aria-label="描述目标">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void session.generate();
            }}
          >
            <div className="vision-field-heading">
              <label htmlFor="vision-input">你希望怎样的未来发生？</label>
              <span>开放问题，不限领域</span>
            </div>
            <textarea
              id="vision-input"
              data-testid="vision-input"
              value={state.request.vision}
              onChange={(event) => session.edit({ vision: event.target.value })}
              placeholder={EXAMPLE}
              rows={3}
              maxLength={1200}
            />
            <button
              className="vision-example"
              type="button"
              data-testid="vision-example"
              onClick={() => session.edit({ vision: EXAMPLE })}
            >
              试填一个目标：{EXAMPLE}
              <ArrowUpRight size={13} />
            </button>
            <details className="vision-options">
              <summary>
                补充边界 <span>可选</span>
                <ChevronDown size={14} />
              </summary>
              <div className="vision-options-fields">
                <label>
                  时间范围
                  <input
                    data-testid="vision-horizon"
                    value={state.request.horizon}
                    onChange={(e) => session.edit({ horizon: e.target.value })}
                    placeholder="例如：未来 10 年"
                    maxLength={100}
                  />
                </label>
                <label>
                  观察视角
                  <input
                    data-testid="vision-perspective"
                    value={state.request.perspective}
                    onChange={(e) =>
                      session.edit({ perspective: e.target.value })
                    }
                    placeholder="例如：公共研究机构"
                    maxLength={200}
                  />
                </label>
                <label className="vision-constraints">
                  不能忽略的约束
                  <textarea
                    data-testid="vision-constraints"
                    value={state.request.constraints}
                    onChange={(e) =>
                      session.edit({ constraints: e.target.value })
                    }
                    placeholder="资源、价值底线、地区或现实阻力…"
                    rows={2}
                    maxLength={1000}
                  />
                </label>
              </div>
            </details>
            <div className="vision-generate-row">
              <span>
                {!state.connected
                  ? "可先写目标，连接后再生成。"
                  : !session.supports("vision_generate")
                    ? "当前服务未开放目标生成，请更新服务。"
                    : "生成不会保存；确认后可单独保存项目。"}
              </span>
              <button
                type="submit"
                className="vision-primary"
                data-testid="vision-generate"
                disabled={
                  !state.request.vision.trim() ||
                  !session.supports("vision_generate") ||
                  !!state.busy
                }
              >
                {generating ? (
                  <LoaderCircle className="vision-spin" size={17} />
                ) : (
                  <Sparkles size={17} />
                )}
                {generating ? "模型思考中" : "寻找转折点"}
                <ArrowRight size={16} />
              </button>
            </div>
          </form>
        </section>
        <aside className="vision-connection" aria-label="本地服务连接">
          <div className="vision-connection-heading">
            <KeyRound size={16} />
            <h2>连接 Contingent 服务</h2>
            <span
              className={
                state.connected ? "vision-status is-connected" : "vision-status"
              }
              data-testid="vision-connection-status"
            >
              {state.connected ? "已连接" : "未连接"}
            </span>
          </div>
          <p>
            使用服务启动时提供的令牌。仅保留在当前浏览器标签页，不会写入项目。
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void session.connect(token);
            }}
          >
            <label htmlFor="vision-token">服务令牌</label>
            <input
              id="vision-token"
              data-testid="vision-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={token}
              placeholder="输入本地服务令牌"
              disabled={state.connected || state.busy === "connecting"}
              onChange={(e) => setToken(e.target.value)}
            />
            {state.connected ? (
              <button
                type="button"
                data-testid="vision-disconnect"
                onClick={() => session.disconnect()}
              >
                <Unplug size={14} />
                断开连接
              </button>
            ) : (
              <button
                type="submit"
                data-testid="vision-connect"
                disabled={!token.trim() || state.busy === "connecting"}
              >
                {state.busy === "connecting" ? "连接中…" : "连接服务"}
                <ArrowRight size={14} />
              </button>
            )}
          </form>
          <p className="vision-privacy-note">
            你的目标将发送给本地服务配置的模型。
            <br />
            输入修改后，旧结果会立即隐藏。
          </p>
        </aside>
      </div>
      {state.error && (
        <div className="vision-error" role="alert" data-testid="vision-error">
          {state.error}
        </div>
      )}
      {state.notice && (
        <p className="vision-notice" role="status">
          {state.notice}
        </p>
      )}
      {state.busy && state.busy !== "connecting" && (
        <div className="vision-wait" role="status" data-testid="vision-busy">
          <LoaderCircle size={20} className="vision-spin" />
          <div>
            <strong>
              {generating
                ? "正在等待模型返回完整路径"
                : state.busy === "saving"
                  ? "正在保存并读回核对"
                  : "正在读取已保存项目"}
            </strong>
            <p>
              {generating
                ? `已等待 ${elapsed} 秒 · 最多等待 180 秒。生成可能需要约一分钟；没有预设进度，也不会自动保存。`
                : "以服务端实际返回为准。"}
            </p>
          </div>
          {generating && (
            <button type="button" onClick={() => session.cancel()}>
              停止等待
            </button>
          )}
        </div>
      )}
      {state.draft ? (
        <Result
          key={`${state.draft.generated_at}:${state.draft.request.vision}`}
          draft={state.draft}
          session={session}
          saved={!!state.saved}
          busy={state.busy}
        />
      ) : (
        !generating &&
        state.busy !== "loading" && (
          <section
            className="vision-empty"
            data-testid="vision-empty"
            aria-label="等待目标"
          >
            <div className="vision-empty-axis" aria-hidden="true">
              <span />
              <i />
              <span />
              <i />
              <span className="vision-empty-goal" />
            </div>
            <div>
              <span className="vision-eyebrow">
                从一个问题开始，而非一个确定答案
              </span>
              <h2>未来不是一条直线。</h2>
              <p>
                生成后，这里会展开关键转折、条件路径与尚待验证的信号。
                <br />
                目前没有推演结果；示例只会填入目标，不会生成演示数据。
              </p>
            </div>
            <ArrowUpRight size={32} />
          </section>
        )
      )}
      <section
        className="vision-projects"
        aria-label="已保存项目"
        data-testid="vision-projects"
      >
        <div className="vision-projects-heading">
          <h2>
            <Bookmark size={16} />
            已保存项目
          </h2>
          <button
            type="button"
            data-testid="vision-reload"
            disabled={!session.supports("vision_list") || state.listBusy}
            onClick={() => void session.reload()}
          >
            <RefreshCw
              size={14}
              className={state.listBusy ? "vision-spin" : ""}
            />
            刷新列表
          </button>
        </div>
        {state.listError && (
          <p className="vision-error" role="alert">
            {state.listError}
          </p>
        )}
        {!state.connected ? (
          <p className="vision-muted">
            连接服务后读取项目。未保存的草稿不会出现在这里。
          </p>
        ) : !session.supports("vision_list") ? (
          <p className="vision-muted">当前服务未开放项目列表。</p>
        ) : state.listBusy && !state.listLoaded ? (
          <p className="vision-muted">正在读取服务端项目…</p>
        ) : state.listLoaded && !state.items.length ? (
          <p className="vision-muted">
            还没有保存的项目。生成后可显式保存，稍后继续查看。
          </p>
        ) : null}
        <div className="vision-project-list">
          {state.items.map((item) => (
            <button
              type="button"
              className="vision-project"
              key={item.id}
              data-testid={`vision-project-${item.id}`}
              disabled={
                !session.supports("vision_get") || state.busy === "saving"
              }
              onClick={() => void session.load(item.id)}
            >
              <div>
                <strong>{item.title}</strong>
                <span>{item.vision}</span>
              </div>
              <time>{item.created_at}</time>
              <ArrowUpRight size={16} />
            </button>
          ))}
        </div>
      </section>
      <footer className="vision-footer">
        <span>Contingent · 把目标变成可讨论的条件</span>
        <span>模型提供假设，人来判断与验证。</span>
      </footer>
    </main>
  );
}
