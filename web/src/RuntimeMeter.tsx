import { useEffect, useRef, useState } from "react";
import { Api, type AnalysisStats } from "./api";
import { latestTiming } from "./runTiming";
import { tabRead, tabWrite } from "./analysisSession";
import NixieClock from "./NixieClock";
import "./meter.css";

export default function RuntimeMeter() {
  const [token, setToken] = useState(() => tabRead("tianji-token"));
  const [stats, setStats] = useState<AnalysisStats | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const generation = useRef(0);
  const timing = latestTiming();
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  async function refresh() {
    const current = ++generation.current;
    setBusy(true);
    setError("");
    setStats(null);
    try {
      const api = new Api(token);
      await api.catalog();
      if (current !== generation.current) return;
      const result = await api.op("analysis_stats", {});
      if (current !== generation.current) return;
      if (
        result.scope !== "saved_analyses_only" ||
        result.architecture !== "single_model_single_call" ||
        ![result.saved_analyses, result.nodes, result.paths].every(
          (v) => Number.isSafeInteger(v) && v >= 0,
        )
      )
        throw new Error("统计响应格式无效");
      tabWrite("tianji-token", token);
      setStats(result);
    } catch (e) {
      if (current === generation.current)
        setError(e instanceof Error ? e.message : "统计读取失败");
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }
  return (
    <main className="runtime-meter" data-testid="runtime-meter">
      <section className="meter-hero">
        <h1 className="meter-kicker">CONTINGENT / UTC CLOCK</h1>
        <NixieClock />
        <p className="meter-note">
          设备时钟 · 协调世界时；不是独立授时服务，无需连接 API 或模型。
        </p>
      </section>
      <section className="meter-report">
        <h2>LOCAL STATUS REPORT</h2>
        <p className="meter-note">
          以下计数仅含明确保存的旧版单次调用分析，不含新多代理运行。同一内容另存一次会分别计数，不代表执行次数、独立事实或成功概率。
        </p>
        <form
          className="meter-connect"
          onSubmit={(e) => {
            e.preventDefault();
            void refresh();
          }}
        >
          <label>
            本地服务令牌
            <input
              data-testid="meter-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => {
                generation.current++;
                setBusy(false);
                setStats(null);
                setError("");
                setToken(e.target.value);
              }}
            />
          </label>
          <button data-testid="meter-refresh" disabled={!token.trim() || busy}>
            {busy ? "读取中…" : "读取 / 刷新统计"}
          </button>
        </form>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <div className="meter-table-scroll">
          <table>
            <thead>
              <tr>
                <th>指标</th>
                <th>数值</th>
                <th>口径</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>已保存单次调用分析</td>
                <td data-testid="meter-count">
                  {stats?.saved_analyses ?? "未读取"}
                </td>
                <td>旧版单模型 · 单次调用；仅显式保存的对象</td>
              </tr>
              <tr>
                <td>节点 / 路径</td>
                <td>{stats ? `${stats.nodes} / ${stats.paths}` : "未读取"}</td>
                <td>所有已保存单次调用分析的合计，不跨分析去重</td>
              </tr>
              <tr>
                <td>最近成功单次生成耗时</td>
                <td>
                  {timing
                    ? `${(timing.milliseconds / 1000).toFixed(2)} s`
                    : "未测量"}
                </td>
                <td>当前页面会话，含网络与结构校验；刷新清空，非纯推理耗时</td>
              </tr>
              <tr>
                <td>新分析架构</td>
                <td>同一模型 · 有界多代理任务</td>
                <td>在分析页单独查看真实任务状态；不以旧版保存计数推算</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section className="meter-method">
        <h2>ANALYSIS PIPELINE</h2>
        <ol>
          <li>输入目标与约束</li>
          <li>分角色、分上下文执行有界任务</li>
          <li>批评与综合保留异议和未知</li>
          <li>查看真实任务与议题关系</li>
        </ol>
        <p>
          议题图不是子代理树；执行任务与议题关系分开呈现。多个角色仍使用同一模型，意见一致不等于独立事实核验或因果效力验证。旧版单次调用结果不会被补造为多代理运行。
        </p>
      </section>
      <footer className="meter-footer">
        Static nixie artwork via{" "}
        <a
          href="https://github.com/FrancescoCaracciolo/DivergenceMeter"
          target="_blank"
          rel="noreferrer"
        >
          DivergenceMeter
        </a>{" "}
        · 上游鸣谢 LuqueDaniel/Divergence-Meter · GPLv3。{" "}
        <a href="/vendor/divergencemeter/README.md">素材来源与许可</a>
        {" · "}
        <a href="/vendor/divergencemeter/COPYING">GPL 全文</a>
        {" · 本地原始 PNG；不加载外站数据、动画、音频或脚本。"}
      </footer>
    </main>
  );
}
