import {
  useLayoutEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import { actionLabel, schemaFields } from "./api";
import type {
  Action,
  Api,
  Branch,
  Capability,
  ParticipantRole,
  SavedAdjudication,
} from "./api";
import { DirectorSession } from "./directorSession";

const actions: Action[] = ["wait", "order_standard", "order_express"];
const json = (value: unknown) => JSON.stringify(value, null, 2);

function Preview({
  value,
  history = false,
}: {
  value: SavedAdjudication;
  history?: boolean;
}) {
  const record = value.record;
  return (
    <article
      className="job"
      data-testid={
        history ? `adjudication-history-${value.id}` : "adjudication-result"
      }
    >
      <div className="row-between">
        <strong>
          {record.proposal_actor_id} · {actionLabel[record.action]}
        </strong>
        <span
          className={record.status === "accepted" ? "goal-met" : "goal-missed"}
          data-testid={history ? undefined : "adjudication-status"}
        >
          {record.status === "accepted" ? "接受预览" : "拒绝预览"} ·{" "}
          {record.status}
        </span>
      </div>
      <p
        className="break"
        data-testid={history ? undefined : "adjudication-reason"}
      >
        {record.reason}
      </p>
      <p className="muted break">
        裁判 {record.adjudicator_id} · 记录 {value.id} · 观察{" "}
        {value.observation_id}
      </p>
      <details open={!history}>
        <summary>
          {record.status === "accepted"
            ? "内核返回的预览后状态（未写入分支）"
            : "拒绝后的未改变状态（未写入分支）"}
        </summary>
        <pre
          className="director-json"
          data-testid={history ? undefined : "adjudication-next-state"}
        >
          {json(value.next_state)}
        </pre>
      </details>
      <details>
        <summary>完整导演裁决记录与摘要</summary>
        <pre
          className="director-json"
          data-testid={history ? undefined : "adjudication-record"}
        >
          {json(record)}
        </pre>
      </details>
    </article>
  );
}

export interface DirectorPanelProps {
  api: Api | null;
  catalog: Capability[];
  branch: Branch | null;
  tick: number;
  disabled: boolean;
}

export default function DirectorPanel({
  api,
  catalog,
  branch,
  tick,
  disabled,
}: DirectorPanelProps) {
  const [role, setRole] = useState<ParticipantRole>("retailer");
  const [actorId, setActorId] = useState("");
  const [action, setAction] = useState<Action>("wait");
  const [referee, setReferee] = useState("");
  const branchId = branch?.id ?? null;
  // A new immutable session means old responses cannot install into the new
  // branch/tick/identity, even when the operator leaves and returns to the same
  // values. API replacement also isolates reconnection from in-flight work.
  const session = useMemo(
    () =>
      new DirectorSession({
        api,
        catalog,
        branchId,
        tick,
        role,
        actorId,
      }),
    [api, catalog, branchId, tick, role, actorId],
  );
  const state = useSyncExternalStore(
    session.subscribe,
    session.getSnapshot,
    session.getSnapshot,
  );
  useLayoutEffect(() => {
    setAction("wait");
    setReferee("");
    session.start();
    return () => session.stop();
  }, [session]);

  const observationFields = schemaFields(catalog, "observation_create");
  const adjudicationFields = schemaFields(catalog, "adjudication_create");
  const recorded = !!branch?.trajectory.frames.some(
    (frame) => frame.state.tick === tick,
  );
  const unavailable = disabled || !api || !recorded;
  const canObserve = session.supports("observation_create", "observation_get");
  const canAdjudicate = session.supports(
    "adjudication_create",
    "adjudication_get",
    "adjudication_list",
  );
  const canList = session.supports("adjudication_list");
  const refereeValid = !!referee.trim() && referee !== actorId;
  return (
    <section
      className="panel director-panel"
      data-testid="director-panel"
      aria-label="导演观察与裁决"
    >
      <div className="section-heading">
        <h2>角色观察与手动裁决</h2>
        <span className="mono muted">DIRECTOR ONLY</span>
      </div>
      <p className="edit-note" data-testid="director-warning">
        仅供导演审计。角色投影不是多用户权限；演员与裁判 ID
        只是审计标签，不是已认证身份。
        不要向不可信参与者提供导演令牌。接受或拒绝均为预览，不写入分支、不自动分叉；没有调用模型或
        FakeActor。
      </p>
      <p className="muted break" data-testid="observation-selection">
        {branch
          ? `${branch.name} · ${branch.id} · T${tick} · 冻结场景 rev ${branch.scenario_revision}`
          : "请先连接服务并选择已有分支。"}
      </p>
      {api && (!canObserve || !canAdjudicate) && (
        <p className="edit-note" data-testid="director-capability-missing">
          服务未开放完整观察／裁决能力；缺失操作已禁用，请检查服务版本。
        </p>
      )}
      {branch && !recorded && (
        <p className="edit-note">当前周期没有已记录状态，不能创建观察。</p>
      )}
      <form
        className="operation"
        onSubmit={(e) => {
          e.preventDefault();
          if (!unavailable) void session.observe();
        }}
      >
        <div className="parameter-grid">
          <label className="field">
            <span>观察角色</span>
            <select
              data-testid="observation-role"
              value={role}
              disabled={unavailable}
              onChange={(e) => setRole(e.target.value as ParticipantRole)}
            >
              <option value="retailer">零售商 retailer</option>
              <option value="supplier">供应商 supplier</option>
            </select>
          </label>
          <label className="field">
            <span>演员 ID（审计标签）</span>
            <input
              data-testid="observation-actor"
              value={actorId}
              required
              disabled={unavailable}
              minLength={observationFields.actor_id?.minLength ?? 1}
              maxLength={observationFields.actor_id?.maxLength ?? 100}
              placeholder="例如 retailer-a"
              onChange={(e) => setActorId(e.target.value)}
            />
          </label>
        </div>
        <button
          type="submit"
          data-testid="observation-create"
          disabled={unavailable || !canObserve || !actorId.trim() || state.busy}
        >
          创建并读回角色观察
        </button>
      </form>
      {state.observation ? (
        <div className="operation" data-testid="observation-result">
          <h3>服务端角色投影 · 原样 JSON</h3>
          <pre className="director-json" data-testid="observation-projection">
            {json(state.observation.observation.projection)}
          </pre>
          <details>
            <summary>完整观察信封、冻结上下文与摘要</summary>
            <pre className="director-json" data-testid="observation-envelope">
              {json(state.observation)}
            </pre>
          </details>
        </div>
      ) : (
        <p className="muted" data-testid="observation-empty">
          尚无当前角色／周期的已读回观察。
        </p>
      )}
      <form
        className="operation"
        onSubmit={(e) => {
          e.preventDefault();
          if (!unavailable) void session.adjudicate(action, referee);
        }}
      >
        <h3>提交单个手动提案</h3>
        <p>
          策略 manual.director.v1。供应商只允许
          wait；其他动作仍可提交，由真实裁决拒绝，不替换动作。
        </p>
        <div className="parameter-grid">
          <label className="field">
            <span>提案动作</span>
            <select
              data-testid="adjudication-action"
              value={action}
              disabled={unavailable || state.busy}
              onChange={(e) => {
                setAction(e.target.value as Action);
                session.clearResult();
              }}
            >
              {actions.map((item) => (
                <option key={item} value={item}>
                  {actionLabel[item]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>独立裁判 ID（不同于演员）</span>
            <input
              data-testid="adjudication-referee"
              value={referee}
              required
              disabled={unavailable || state.busy}
              minLength={adjudicationFields.adjudicator_id?.minLength ?? 1}
              maxLength={adjudicationFields.adjudicator_id?.maxLength ?? 100}
              placeholder="例如 referee-a"
              onChange={(e) => {
                setReferee(e.target.value);
                session.clearResult();
              }}
            />
          </label>
        </div>
        {referee && referee === actorId && (
          <p className="edit-note">裁判 ID 必须与演员 ID 不同。</p>
        )}
        <button
          type="submit"
          data-testid="adjudication-submit"
          disabled={
            unavailable ||
            !canAdjudicate ||
            !state.observation ||
            !refereeValid ||
            state.busy
          }
        >
          保存并读回裁决预览
        </button>
      </form>
      {state.busy && (
        <p role="status" data-testid="director-busy">
          正在请求服务并读回持久化记录…
        </p>
      )}
      {state.error && (
        <p role="alert" className="error-text" data-testid="director-error">
          {state.error} 未确认成功时请先刷新历史，避免重复提交。
        </p>
      )}
      {state.result && (
        <div className="operation" aria-live="polite">
          <Preview value={state.result} />
        </div>
      )}
      <div className="operation">
        <div className="row-between">
          <h3>本分支持久化裁决历史（全部周期／角色）</h3>
          <button
            type="button"
            data-testid="adjudication-reload"
            disabled={unavailable || !canList || state.historyBusy}
            onClick={() => void session.reloadHistory()}
          >
            刷新历史
          </button>
        </div>
        {state.historyBusy && <p role="status">正在读取历史…</p>}
        {state.historyError && (
          <p
            role="alert"
            className="error-text"
            data-testid="adjudication-history-error"
          >
            {state.historyError}
          </p>
        )}
        <div data-testid="adjudication-history" aria-busy={state.historyBusy}>
          {state.history.map((value) => (
            <Preview key={value.id} value={value} history />
          ))}
        </div>
        {!state.history.length && (
          <p className="muted" data-testid="adjudication-history-empty">
            {state.historyLoaded ? "本分支暂无已保存裁决。" : "历史尚未读取。"}
          </p>
        )}
      </div>
    </section>
  );
}
