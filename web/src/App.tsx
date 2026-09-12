import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  Download,
  GitBranch,
  Layers,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Square,
  Upload,
  X,
} from "lucide-react";
import {
  actionLabel,
  frameAtTick,
  isTerminal,
  modeLabel,
  schemaFields,
  statusLabel,
} from "./api";
import type {
  Action,
  Branch,
  Comparison,
  Goal,
  JsonSchema,
  Scenario,
} from "./api";
import { useLab } from "./useLab";
import "./styles.css";

const labels: Record<string, string> = {
  name: "场景名称",
  description: "场景说明",
  horizon: "推演周期",
  initial_inventory: "初始库存",
  initial_cash: "初始资金",
  demand_per_tick: "每期需求",
  supplier_stock: "供应商库存",
  shipment_size: "每次订货量",
  standard_cost: "标准订货费用",
  express_cost: "加急订货费用",
  standard_lead: "标准交付周期",
  express_lead: "加急交付周期",
  max_shortage: "累计缺货上限",
  min_cash: "期末资金下限",
  max_spend: "累计支出上限",
  min_inventory: "期末库存下限",
  inventory: "库存",
  cash: "资金",
  shortage: "累计缺货",
  spent: "累计支出",
  delivered: "累计满足需求",
};
const actions: Action[] = ["wait", "order_standard", "order_express"];
const goalDefaults: Goal = {
  max_shortage: 0,
  min_cash: 0,
  max_spend: 100,
  min_inventory: 0,
};
const signed = (n: number) => `${n > 0 ? "+" : ""}${n}`;

function ActionEditor({
  value,
  onChange,
  start = 0,
  prefix,
}: {
  value: Action[];
  onChange: (value: Action[]) => void;
  start?: number;
  prefix: string;
}) {
  return (
    <div className="action-grid">
      {value.map((action, i) => (
        <label key={i}>
          <span className="mono">
            T{start + i} → T{start + i + 1}
          </span>
          <select
            aria-label={`${prefix} T${start + i} 动作`}
            data-testid={`${prefix}-action-${start + i}`}
            value={action}
            onChange={(e) =>
              onChange(
                value.map((v, j) => (j === i ? (e.target.value as Action) : v)),
              )
            }
          >
            {actions.map((a) => (
              <option key={a} value={a}>
                {actionLabel[a]}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}

function NumericField({
  name,
  value,
  schema,
  onChange,
}: {
  name: string;
  value: number;
  schema?: JsonSchema;
  onChange: (n: number) => void;
}) {
  return (
    <label className="field">
      <span>{labels[name] ?? name}</span>
      <input
        data-testid={name.replaceAll("_", "-")}
        name={name}
        type="number"
        required
        step="1"
        min={schema?.minimum}
        max={schema?.maximum}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function Trace({
  branch,
  tick,
  onTick,
}: {
  branch: Branch;
  tick: number;
  onTick: (n: number) => void;
}) {
  const frames = branch.trajectory.frames;
  const max = Math.max(
    1,
    ...frames.flatMap((f) => [
      f.state.inventory,
      f.state.shortage,
      f.state.supplier_stock,
    ]),
  );
  const first = frames[0].state.tick;
  const last = frames[frames.length - 1].state.tick;
  const x = (t: number) => 42 + ((t - first) / Math.max(1, last - first)) * 580;
  const y = (n: number) => 184 - (n / max) * 150;
  const series = [
    { key: "inventory", label: "库存", color: "#6ce1dc" },
    { key: "shortage", label: "累计缺货", color: "#e5b77b" },
    { key: "supplier_stock", label: "供应商库存", color: "#8792b3" },
  ] as const;
  return (
    <div className="trace">
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span className="unit">单位：件</span>
      </div>
      <svg
        viewBox="0 0 650 218"
        role="img"
        aria-label="库存、累计缺货和供应商库存随时间变化的真实状态轨迹"
      >
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line
              x1="42"
              y1={y(max * f)}
              x2="622"
              y2={y(max * f)}
              className="grid-line"
            />
            <text x="30" y={y(max * f) + 4} textAnchor="end">
              {Math.round(max * f)}
            </text>
          </g>
        ))}
        <line
          x1={x(tick)}
          y1="24"
          x2={x(tick)}
          y2="184"
          className="cursor-line"
        />
        {series.map((s) => (
          <polyline
            key={s.key}
            fill="none"
            stroke={s.color}
            strokeWidth="2"
            points={frames
              .map((f) => `${x(f.state.tick)},${y(f.state[s.key])}`)
              .join(" ")}
          />
        ))}
        {frames.map((f) => (
          <g key={f.state.tick}>
            <text x={x(f.state.tick)} y="207" textAnchor="middle">
              T{f.state.tick}
            </text>
            <circle
              cx={x(f.state.tick)}
              cy={y(f.state.inventory)}
              r={f.state.tick === tick ? 5 : 3}
              fill="#6ce1dc"
            />
            <rect
              x={x(f.state.tick) - 15}
              y="24"
              width="30"
              height="166"
              fill="transparent"
              tabIndex={0}
              role="button"
              aria-label={`查看 T${f.state.tick}`}
              onClick={() => onTick(f.state.tick)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onTick(f.state.tick);
                }
              }}
            />
          </g>
        ))}
      </svg>
    </div>
  );
}

export default function App() {
  const lab = useLab();
  const selected = lab.scenarios.find((s) => s.id === lab.scenarioId);
  const [draft, setDraft] = useState<Scenario | null>(null);
  const [baseRevision, setBaseRevision] = useState(0);
  const [dirty, setDirty] = useState(false);
  const editorId = useRef("");
  const [forward, setForward] = useState<Action[]>([]);
  const [forkActions, setForkActions] = useState<Action[]>([]);
  const [goal, setGoal] = useState<Goal>(goalDefaults);
  const [maxNodes, setMaxNodes] = useState(5000);
  const [runName, setRunName] = useState("");
  const [compareId, setCompareId] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [notice, setNotice] = useState("");
  const branch = lab.branch;
  const tick = lab.workspace?.tick ?? 0;
  const frame = branch ? frameAtTick(branch, tick) : null;
  const panel = lab.workspace?.panel ?? "timeline";
  const scenarioSchema = schemaFields(lab.catalog, "scenario_create", "spec");
  const goalSchema = schemaFields(lab.catalog, "run_backward", "goal");
  const backwardSchema = schemaFields(lab.catalog, "run_backward");
  const disabled = !lab.api || lab.busy;
  const forkLength = branch ? Math.max(0, branch.spec.horizon - tick) : 0;

  useEffect(() => {
    if (selected && (editorId.current !== selected.id || !dirty)) {
      setDraft({ ...selected.spec });
      setBaseRevision(selected.revision);
      setDirty(false);
      editorId.current = selected.id;
    }
  }, [selected, dirty]);
  useEffect(() => {
    setForward(
      Array.from({ length: selected?.spec.horizon ?? 0 }, () => "wait"),
    );
  }, [selected?.id, selected?.spec.horizon]);
  useEffect(() => {
    setForkActions(Array.from({ length: forkLength }, () => "wait"));
  }, [branch?.id, tick, forkLength]);
  useEffect(() => {
    setComparison(null);
    setCompareId(lab.workspace?.compare_branch_id ?? "");
    let active = true;
    if (
      lab.api &&
      branch &&
      lab.workspace?.compare_branch_id &&
      panel === "compare"
    ) {
      void lab.api
        .op("branch_compare", {
          left_id: branch.id,
          right_id: lab.workspace.compare_branch_id,
        })
        .then((result) => {
          if (active) setComparison(result);
        })
        .catch((e) => {
          if (active) lab.setError(e instanceof Error ? e.message : String(e));
        });
    }
    return () => {
      active = false;
    };
  }, [branch?.id, lab.workspace?.compare_branch_id, lab.api, panel]);

  const perform = (task: () => Promise<void>) => {
    setNotice("");
    void lab.act(task);
  };
  const setPanel = (next: "timeline" | "compare" | "goal") =>
    perform(async () => {
      await lab.updateWorkspace({ panel: next });
    });
  const setTick = (next: number) =>
    perform(async () => {
      await lab.updateWorkspace({ tick: next });
    });
  const save = () =>
    perform(async () => {
      if (!lab.api || !selected || !draft) return;
      await lab.api.op("scenario_update", {
        id: selected.id,
        revision: baseRevision,
        spec: draft,
      });
      const records = await lab.api.op("scenario_list", {});
      const verified = records.items.find((s) => s.id === selected.id);
      if (!verified) throw new Error("保存后未能读取场景，请刷新重试。");
      setDraft({ ...verified.spec });
      setBaseRevision(verified.revision);
      setDirty(false);
      await lab.refresh();
      setNotice(`场景已保存 · revision ${verified.revision}`);
    });
  const create = () =>
    perform(async () => {
      if (!lab.api || !draft) return;
      const record = await lab.api.op("scenario_create", {
        spec: {
          ...draft,
          name: draft.name.trim()
            ? `${draft.name.slice(0, 90)} · 副本`
            : "新场景",
        },
      });
      const verified = (await lab.api.op("scenario_list", {})).items.find(
        (s) => s.id === record.id,
      );
      if (!verified) throw new Error("新建场景未能读回，请刷新检查。");
      await lab.updateWorkspace({
        scenario_id: verified.id,
        branch_id: null,
        tick: 0,
        panel: "timeline",
      });
      setDirty(false);
      lab.setScenarioId(verified.id);
      await lab.refresh();
      setNotice("已新建独立场景，可编辑名称和参数。");
    });
  const submitForward = () =>
    perform(async () => {
      if (!lab.api || !selected) return;
      await lab.trackJob(
        await lab.api.op("run_forward", {
          scenario_id: selected.id,
          actions: forward,
          ...(runName.trim() ? { name: runName.trim() } : {}),
        }),
      );
    });
  const submitBackward = () =>
    perform(async () => {
      if (!lab.api || !selected) return;
      await lab.trackJob(
        await lab.api.op("run_backward", {
          scenario_id: selected.id,
          goal,
          max_nodes: maxNodes,
          ...(runName.trim() ? { name: runName.trim() } : {}),
        }),
      );
    });
  const submitFork = () =>
    perform(async () => {
      if (!lab.api || !branch) return;
      await lab.trackJob(
        await lab.api.op("branch_fork", {
          id: branch.id,
          tick,
          actions: forkActions,
          ...(runName.trim() ? { name: runName.trim() } : {}),
        }),
      );
    });
  const compare = () =>
    perform(async () => {
      if (!lab.api || !branch || !compareId) return;
      const result = await lab.api.op("branch_compare", {
        left_id: branch.id,
        right_id: compareId,
      });
      await lab.updateWorkspace({
        panel: "compare",
        compare_branch_id: compareId,
      });
      setComparison(result);
    });
  const download = () =>
    perform(async () => {
      if (!lab.api || !branch) return;
      const bundle = await lab.api.op("branch_export", { id: branch.id });
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(bundle, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `tianji-${branch.id}.json`;
      document.body.append(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("已下载真实分支包，包含规则、轨迹与摘要。");
    });
  const upload = (file: File) =>
    perform(async () => {
      if (!lab.api) return;
      if (file.size > 1_000_000)
        throw new Error("导入文件超过 1 MB，请选择单个分支 JSON。");
      let bundle: unknown;
      try {
        bundle = JSON.parse(await file.text());
      } catch {
        throw new Error("文件不是有效 JSON，请使用导出的分支包。");
      }
      if (!bundle || typeof bundle !== "object" || Array.isArray(bundle))
        throw new Error("分支包必须是 JSON 对象。");
      const result = await lab.api.op("branch_import", { bundle });
      const verified = await lab.api.op("branch_get", { id: result.id });
      await lab.refresh();
      lab.setScenarioId(verified.scenario_id);
      await lab.selectBranch(verified);
      setNotice("分支已导入，服务端已验证摘要与正向回放。");
    });

  return (
    <div className="lab-shell">
      <header className="masthead">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={25} />
          </div>
          <div>
            <h1>
              天机 <span>TIANJI</span>
            </h1>
            <p>双向世界推演实验室</p>
          </div>
        </div>
        <div className="header-meta">
          <span className="model-tag">规则模型 · 虚构供应链</span>
          <span
            className={`connection ${lab.api ? "connected" : ""}`}
            data-testid="connection-status"
          >
            <i />
            {lab.api ? (lab.busy ? "正在操作" : "API 已连接") : "等待连接"}
          </span>
        </div>
      </header>
      <section className="connection-bar" aria-label="服务连接">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void lab.connect();
          }}
        >
          <label htmlFor="token">本地服务令牌</label>
          <input
            id="token"
            data-testid="token-input"
            type="password"
            autoComplete="off"
            placeholder="输入 token 文件中的令牌"
            value={lab.token}
            onChange={(e) => lab.setToken(e.target.value)}
          />
          <button
            data-testid="connect-button"
            disabled={lab.busy}
            type="submit"
          >
            {lab.api ? "重新连接" : "连接实验室"}
            <ArrowRight size={14} />
          </button>
        </form>
        <div className="sync-info">
          {lab.workspace ? (
            <>
              <span>
                WORKSPACE{" "}
                <code data-testid="workspace-id">{lab.workspace.id}</code>
              </span>
              <span>
                rev {lab.workspace.revision} ·{" "}
                {lab.syncAt ? `同步 ${lab.syncAt}` : "等待同步"}
              </span>
            </>
          ) : (
            <span>仅连接本地服务 · 令牌保存在当前会话</span>
          )}
          <button
            className="icon-button"
            aria-label="刷新实验室"
            title="刷新实验室"
            disabled={disabled}
            onClick={() => perform(lab.refresh)}
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </section>
      {lab.error && (
        <div role="alert" className="banner error" data-testid="error-banner">
          <span>{lab.error}</span>
          <button aria-label="关闭错误" onClick={() => lab.setError("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {notice && (
        <div role="status" className="banner notice">
          {notice}
        </div>
      )}
      <nav className="mobile-shortcuts" aria-label="工作台快捷导航">
        <a href="#scenario-editor">场景</a>
        <a href="#lab-operations">推演与反推</a>
        <a href="#worldline-canvas">结果</a>
      </nav>
      <main className="workbench">
        <aside className="scenario-column" id="scenario-editor">
          <section className="panel">
            <div className="section-heading">
              <h2>
                <Layers size={16} />
                场景设定
              </h2>
              <button
                className="icon-button"
                title="以当前参数新建场景"
                aria-label="新建场景"
                data-testid="new-scenario"
                disabled={disabled || !draft}
                onClick={create}
              >
                <Plus size={17} />
              </button>
            </div>
            <label className="field">
              <span>工作场景</span>
              <select
                data-testid="scenario-select"
                value={lab.scenarioId}
                disabled={disabled || !lab.scenarios.length}
                onChange={(e) => {
                  const id = e.target.value;
                  perform(async () => {
                    await lab.updateWorkspace({
                      scenario_id: id,
                      branch_id: null,
                      tick: 0,
                      panel: "timeline",
                    });
                    setDirty(false);
                    lab.setScenarioId(id);
                  });
                }}
              >
                <option value="" disabled>
                  连接后读取场景
                </option>
                {lab.scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.spec.name}
                  </option>
                ))}
              </select>
            </label>
            {draft && selected ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  save();
                }}
              >
                <label className="field">
                  <span>场景名称</span>
                  <input
                    data-testid="scenario-name"
                    required
                    minLength={scenarioSchema.name?.minLength ?? 1}
                    maxLength={scenarioSchema.name?.maxLength ?? 100}
                    value={draft.name}
                    onChange={(e) => {
                      setDraft({ ...draft, name: e.target.value });
                      setDirty(true);
                    }}
                  />
                </label>
                <label className="field">
                  <span>场景说明</span>
                  <textarea
                    rows={5}
                    maxLength={scenarioSchema.description?.maxLength ?? 2000}
                    value={draft.description ?? ""}
                    onChange={(e) => {
                      setDraft({ ...draft, description: e.target.value });
                      setDirty(true);
                    }}
                  />
                </label>
                <div className="parameter-grid">
                  {Object.entries(scenarioSchema)
                    .filter(
                      ([key, schema]) =>
                        key in draft && schema.type === "integer",
                    )
                    .map(([key, schema]) => (
                      <NumericField
                        key={key}
                        name={key}
                        schema={schema}
                        value={draft[key as keyof Scenario] as number}
                        onChange={(n) => {
                          setDraft({ ...draft, [key]: n });
                          setDirty(true);
                        }}
                      />
                    ))}
                </div>
                {dirty && (
                  <p className="edit-note">
                    {selected.revision !== baseRevision
                      ? "服务端版本已变更。保存可能冲突，请核对参数。"
                      : "参数尚未保存；推演使用已保存版本。"}
                  </p>
                )}
                <div className="row-between">
                  <span className="muted mono">revision {baseRevision}</span>
                  <button
                    data-testid="save-scenario"
                    type="submit"
                    disabled={disabled || !dirty}
                  >
                    <Save size={14} />
                    保存场景
                  </button>
                </div>
                {dirty && (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      setDraft({ ...selected.spec });
                      setBaseRevision(selected.revision);
                      setDirty(false);
                    }}
                  >
                    放弃修改，读取最新版本
                  </button>
                )}
              </form>
            ) : (
              <div className="empty small">
                连接本地 API 后读取真实场景与参数约束。
              </div>
            )}
          </section>
          <section className="panel model-note">
            <h3>实验边界</h3>
            <p>
              有限库存、固定需求与确定性交付。结论仅在当前模型和参数下成立，不代表现实预测。
            </p>
            <div className="mono">
              rules-v1 / fictional
              <br />
              model-conditional
            </div>
            <details>
              <summary>参与者与可见性</summary>
              <p>
                当前 Web/API/MCP
                均为完整权限的导演视图。内核已有零售商／供应商观察投影，但尚未接入多用户权限或真实协商。不要把导演令牌交给不可信玩家。
              </p>
            </details>
          </section>
        </aside>
        <section className="canvas-column" id="worldline-canvas">
          <section className="panel branch-panel">
            <div className="section-heading">
              <h2>
                <GitBranch size={16} />
                推演分支 <span className="count">{lab.branches.length}</span>
              </h2>
              <div className="toolbar">
                <label
                  className={`button file-button ${disabled ? "disabled" : ""}`}
                >
                  <Upload size={14} />
                  导入
                  <input
                    type="file"
                    accept=".json,application/json"
                    aria-label="上传分支包"
                    data-testid="import-bundle"
                    disabled={disabled}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) upload(file);
                      e.target.value = "";
                    }}
                  />
                </label>
                <button
                  data-testid="export-branch"
                  disabled={disabled || !branch}
                  onClick={download}
                >
                  <Download size={14} />
                  导出
                </button>
              </div>
            </div>
            <div data-testid="branch-list" className="branch-list">
              {lab.branches.length ? (
                lab.branches.map((b) => (
                  <button
                    key={b.id}
                    className={`branch-card ${branch?.id === b.id ? "selected" : ""} ${b.parent_id ? "is-fork" : ""}`}
                    disabled={disabled}
                    onClick={() =>
                      perform(async () => {
                        await lab.selectBranch(b);
                      })
                    }
                    data-testid={`branch-${b.id}`}
                    aria-pressed={branch?.id === b.id}
                  >
                    <span className="row-between">
                      <strong>
                        {b.name}{" "}
                        <small className="mono muted">{b.id.slice(0, 6)}</small>
                      </strong>
                      <span className="branch-mode">{modeLabel[b.mode]}</span>
                    </span>
                    <span className="branch-stats">
                      支出 {b.trajectory.final_state.spent}{" "}
                      <span>缺货 {b.trajectory.final_state.shortage}</span>
                    </span>
                    <span className="branch-provenance">
                      {b.parent_id
                        ? `↳ ${lab.branches.find((p) => p.id === b.parent_id)?.name ?? b.parent_id.slice(0, 8)} / T${b.fork_tick}`
                        : `场景 rev ${b.scenario_revision}`}{" "}
                      {b.trajectory.goal_met !== null && (
                        <span
                          className={
                            b.trajectory.goal_met ? "goal-met" : "goal-missed"
                          }
                        >
                          {b.trajectory.goal_met ? "目标达成" : "目标未达成"}
                        </span>
                      )}
                    </span>
                  </button>
                ))
              ) : (
                <div className="empty">
                  尚无推演分支。编辑场景后，在右侧运行正向推演或目标反推。
                </div>
              )}
            </div>
          </section>
          <section className="panel timeline-panel">
            <div className="section-heading">
              <h2>
                <Activity size={16} />
                {branch?.name ?? "状态轨迹"}
              </h2>
              <nav className="tabs" aria-label="工作区视图">
                {(["timeline", "goal", "compare"] as const).map((p) => (
                  <button
                    key={p}
                    disabled={disabled}
                    className={panel === p ? "active" : ""}
                    aria-pressed={panel === p}
                    onClick={() => setPanel(p)}
                  >
                    {{ timeline: "时间线", goal: "目标", compare: "比较" }[p]}
                  </button>
                ))}
              </nav>
            </div>
            {branch && frame ? (
              <>
                <div className="trace-meta">
                  <span>
                    冻结场景 rev {branch.scenario_revision} ·{" "}
                    {branch.trajectory.rule_version ?? "supply-chain.v1"}
                  </span>
                  <span className="mono">
                    T{tick} / T{branch.spec.horizon}
                  </span>
                </div>
                <div className="frozen-assumptions">
                  {selected?.revision !== branch.scenario_revision && (
                    <p>
                      当前场景已是 rev {selected?.revision}
                      ；下方结果仍使用冻结的 rev {branch.scenario_revision}。
                    </p>
                  )}
                  <details>
                    <summary>查看本分支的冻结参数与目标</summary>
                    <dl>
                      {Object.entries(branch.spec)
                        .filter(([k]) => !["name", "description"].includes(k))
                        .map(([k, v]) => (
                          <div key={k}>
                            <dt>{labels[k] ?? k}</dt>
                            <dd>{v}</dd>
                          </div>
                        ))}
                      {branch.provenance.goal &&
                        Object.entries(branch.provenance.goal).map(([k, v]) => (
                          <div key={k}>
                            <dt>{labels[k] ?? k}</dt>
                            <dd>{v}</dd>
                          </div>
                        ))}
                    </dl>
                    <p className="mono break">
                      {branch.trajectory.actions
                        .map(
                          (a, i) =>
                            `T${branch.trajectory.frames[0].state.tick + i}: ${actionLabel[a]}`,
                        )
                        .join(" · ")}
                    </p>
                  </details>
                </div>
                <Trace branch={branch} tick={tick} onTick={setTick} />
                <label className="timeline-control">
                  <span>回放游标</span>
                  <input
                    data-testid="timeline-slider"
                    type="range"
                    aria-label="时间线周期"
                    min={branch.trajectory.frames[0].state.tick}
                    max={
                      branch.trajectory.frames[
                        branch.trajectory.frames.length - 1
                      ].state.tick
                    }
                    step="1"
                    value={tick}
                    disabled={disabled}
                    onChange={(e) => setTick(Number(e.target.value))}
                  />
                  <output className="mono" data-testid="current-tick">
                    T{tick}
                  </output>
                </label>
                <div className="state-grid">
                  {(["inventory", "cash", "shortage", "spent"] as const).map(
                    (key) => (
                      <div key={key}>
                        <span>{labels[key]}</span>
                        <strong data-testid={`state-${key}`}>
                          {frame.state[key]}
                        </strong>
                      </div>
                    ),
                  )}
                </div>
                <div className="events">
                  <div className="row-between">
                    <h3>
                      T{frame.state.tick} ·{" "}
                      {actionLabel[frame.action] ?? frame.action}
                    </h3>
                    <span className="muted">
                      已满足需求 {frame.state.delivered} · 供应商库存{" "}
                      {frame.state.supplier_stock}
                    </span>
                  </div>
                  <ul>
                    {frame.events.length ? (
                      frame.events.map((event, i) => <li key={i}>{event}</li>)
                    ) : (
                      <li>初始状态，尚未执行动作。</li>
                    )}
                  </ul>
                  {frame.state.shipments.length > 0 && (
                    <p className="muted">
                      在途：
                      {frame.state.shipments.map((s, i) => (
                        <span key={i}>
                          {" "}
                          {s.quantity} 件于 T{s.due_tick} 到达；
                        </span>
                      ))}
                    </p>
                  )}
                  <details>
                    <summary>状态完整性与分支标识</summary>
                    <p className="mono break">
                      Branch: {branch.id}
                      <br />
                      State SHA-256: {frame.state_hash}
                    </p>
                  </details>
                </div>
              </>
            ) : (
              <div className="empty canvas-empty">
                <Activity size={36} />
                <h3>让假设沿时间展开</h3>
                <p>
                  运行真实规则模型，查看每个周期的库存、资金、事件与可回放状态。
                </p>
              </div>
            )}
            {panel === "compare" && (
              <section className="comparison">
                <h3>分支比较 · 右侧减左侧</h3>
                {comparison ? (
                  <>
                    <p>
                      {comparison.left.name} <ArrowRight size={14} />{" "}
                      {comparison.right.name}
                    </p>
                    <div className="table-scroll">
                      <table data-testid="comparison-result">
                        <thead>
                          <tr>
                            <th>期末指标</th>
                            <th>左分支</th>
                            <th>右分支</th>
                            <th>差值</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(comparison.delta).map(
                            ([key, value]) => (
                              <tr key={key}>
                                <th>{labels[key] ?? key}</th>
                                <td>
                                  {
                                    comparison.left.trajectory.final_state[
                                      key as keyof typeof comparison.delta
                                    ]
                                  }
                                </td>
                                <td>
                                  {
                                    comparison.right.trajectory.final_state[
                                      key as keyof typeof comparison.delta
                                    ]
                                  }
                                </td>
                                <td className="mono">{signed(value)}</td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <p className="muted">
                    在右侧选择同一冻结场景的分支并运行比较。
                  </p>
                )}
              </section>
            )}
            {panel === "goal" && (
              <div className="goal-summary">
                <h3>期末目标检查</h3>
                <p>
                  {branch?.trajectory.goal_met === true
                    ? "所选候选在规则模型中通过了目标检查。"
                    : branch?.trajectory.goal_met === false
                      ? "所选分支未满足目标。"
                      : "正向分支未附带目标检查；请在右侧提交反推。"}
                </p>
                <p className="muted">
                  反推结果与搜索边界见任务记录；预算耗尽不等于无解。
                </p>
              </div>
            )}
          </section>
          <section className="panel jobs-panel">
            <div className="section-heading">
              <h2>计算任务</h2>
              <span className="muted">服务端执行 · 自动轮询</span>
            </div>
            <div data-testid="job-status" aria-live="polite">
              {lab.jobs.length ? (
                [...lab.jobs].reverse().map((job) => (
                  <article key={job.id} className="job">
                    <div className="row-between">
                      <strong>
                        {job.kind.includes("backward")
                          ? "目标反推"
                          : job.kind.includes("fork")
                            ? "分支续演"
                            : "正向推演"}
                      </strong>
                      <span className={`job-state ${job.status}`}>
                        {statusLabel[job.status]}
                      </span>
                    </div>
                    <div className="row-between">
                      <code>{job.id}</code>
                      {!isTerminal(job.status) && (
                        <button
                          disabled={disabled}
                          data-testid={`cancel-job-${job.id}`}
                          onClick={() =>
                            perform(async () => {
                              if (lab.api)
                                await lab.trackJob(
                                  await lab.api.op("job_cancel", {
                                    id: job.id,
                                  }),
                                );
                            })
                          }
                        >
                          <Square size={12} />
                          取消任务
                        </button>
                      )}
                    </div>
                    {job.error && <p className="error-text">{job.error}</p>}
                    {job.result?.search && (
                      <p className="search-result">
                        {
                          {
                            found: "找到可行候选",
                            no_solution: "已穷尽搜索，目标无解",
                            budget_exhausted: "预算耗尽，尚不能判定无解",
                          }[job.result.search.status]
                        }{" "}
                        · 展开 {job.result.search.expanded} 节点 ·{" "}
                        {job.result.search.plans.length} 个候选 ·{" "}
                        {job.result.search.exhausted
                          ? "搜索空间已穷尽"
                          : "仍有未搜索状态"}
                      </p>
                    )}
                  </article>
                ))
              ) : (
                <p className="muted">
                  尚未提交任务。这里显示实际任务状态，不预估完成结果。
                </p>
              )}
            </div>
          </section>
        </section>
        <aside className="operations-column" id="lab-operations">
          <section className="panel">
            <div className="section-heading">
              <h2>实验操作</h2>
              <span className="mono muted">CONTROL</span>
            </div>
            <label className="field">
              <span>新分支名称（可选）</span>
              <input
                data-testid="run-name"
                value={runName}
                maxLength={100}
                placeholder="由服务自动命名"
                onChange={(e) => setRunName(e.target.value)}
              />
            </label>
            <form
              className="operation"
              onSubmit={(e) => {
                e.preventDefault();
                submitForward();
              }}
            >
              <h3>
                <Play size={15} />
                正向推演
              </h3>
              <p>
                使用当前已保存场景 rev {selected?.revision ?? "—"}，从 T0 运行至
                T{selected?.spec.horizon ?? "—"}。
              </p>
              <ActionEditor
                prefix="forward"
                value={forward}
                onChange={setForward}
              />
              <button
                className="primary full"
                type="submit"
                data-testid="run-forward"
                disabled={disabled || !selected || dirty}
              >
                <Play size={14} />
                运行正向推演
              </button>
            </form>
            <form
              className={`operation ${panel === "goal" ? "focused" : ""}`}
              onSubmit={(e) => {
                e.preventDefault();
                submitBackward();
              }}
            >
              <h3>
                <Search size={15} />
                从目标反推
              </h3>
              <p>
                使用当前已保存场景 rev {selected?.revision ?? "—"}，寻找 T
                {selected?.spec.horizon ?? "—"} 的可行方案。
              </p>
              <div className="parameter-grid">
                {(Object.keys(goal) as (keyof Goal)[]).map((key) => (
                  <NumericField
                    key={key}
                    name={key}
                    schema={goalSchema[key]}
                    value={goal[key]}
                    onChange={(n) => setGoal({ ...goal, [key]: n })}
                  />
                ))}
              </div>
              <label className="field">
                <span>搜索节点预算</span>
                <input
                  name="max_nodes"
                  data-testid="max-nodes"
                  type="number"
                  required
                  step="1"
                  min={backwardSchema.max_nodes?.minimum ?? 1}
                  max={backwardSchema.max_nodes?.maximum ?? 50000}
                  value={maxNodes}
                  onChange={(e) => setMaxNodes(Number(e.target.value))}
                />
              </label>
              <button
                className="primary full"
                type="submit"
                data-testid="run-backward"
                disabled={disabled || !selected || dirty}
              >
                <Search size={14} />
                搜索可行路径
              </button>
            </form>
            <form
              className="operation"
              onSubmit={(e) => {
                e.preventDefault();
                submitFork();
              }}
            >
              <h3>
                <GitBranch size={15} />
                从当前状态分叉
              </h3>
              <p>
                {branch
                  ? `继承「${branch.name}」到 T${tick}，使用原分支冻结参数继续。`
                  : "先选择一个分支，再移动时间线游标。"}
              </p>
              <ActionEditor
                prefix="fork"
                value={forkActions}
                onChange={setForkActions}
                start={tick}
              />
              <button
                className="full"
                type="submit"
                data-testid="fork-branch"
                disabled={disabled || !branch || forkLength === 0}
              >
                <GitBranch size={14} />从 T{tick} 创建分支
              </button>
              {branch && forkLength === 0 && (
                <p className="muted">当前已到期末，请将游标移到更早的周期。</p>
              )}
            </form>
            <form
              className="operation"
              onSubmit={(e) => {
                e.preventDefault();
                compare();
              }}
            >
              <h3>比较分支</h3>
              <p>左侧为当前选中分支；只比较相同冻结参数。</p>
              <label className="field">
                <span>右侧分支</span>
                <select
                  data-testid="compare-select"
                  value={compareId}
                  onChange={(e) => {
                    setCompareId(e.target.value);
                    setComparison(null);
                  }}
                  disabled={disabled || !branch}
                >
                  <option value="">选择比较对象</option>
                  {lab.branches
                    .filter((b) => b.id !== branch?.id)
                    .map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} · {b.id.slice(0, 6)} · rev{" "}
                        {b.scenario_revision}
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="full"
                type="submit"
                data-testid="compare-branches"
                disabled={disabled || !branch || !compareId}
              >
                比较期末状态
                <ArrowRight size={14} />
              </button>
            </form>
          </section>
          <section className="panel agent-note">
            <h3>外部 Agent · API / MCP 已开放</h3>
            <p>
              Web 与 Agent
              共享操作与工作区版本。外部选择分支、周期和面板后，本页轮询同步。
            </p>
            <details>
              <summary>MCP 接入说明</summary>
              <p>
                在 backend 目录运行，令牌通过环境变量 TIANJI_TOKEN 传入，不写入
                URL：
              </p>
              <code className="break">
                uv run python -m tianji_lab mcp --url http://127.0.0.1:8787
              </code>
              <p>工作区命令是服务端期望状态，不是浏览器渲染回执。</p>
            </details>
            <span className="muted mono">
              {lab.catalog.length
                ? `${lab.catalog.length} capabilities`
                : "连接后发现能力"}
            </span>
          </section>
        </aside>
      </main>
      <footer>
        天机实验室 / M1 <span>确定性规则 · 有界搜索 · 可验证回放</span>
      </footer>
    </div>
  );
}
