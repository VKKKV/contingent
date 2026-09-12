import { useCallback, useEffect, useRef, useState } from "react";
import { Api, ApiError, isTerminal } from "./api";
import type { Branch, Capability, Job, ScenarioRecord, Workspace } from "./api";

const stored = (key: string) => {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
};
const store = (key: string, value: string) => {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* Private browsing may disallow storage. */
  }
};
export function useLab() {
  const [token, setToken] = useState(stored("tianji-token") ?? "");
  const [api, setApi] = useState<Api | null>(null);
  const [catalog, setCatalog] = useState<Capability[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioRecord[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branch, setBranch] = useState<Branch | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [syncAt, setSyncAt] = useState<string | null>(null);
  const current = useRef({ api, scenarioId, workspace, jobs });
  current.current = { api, scenarioId, workspace, jobs };
  const revision = useRef<Workspace | null>(null);
  const loadedBranchId = useRef<string | null>(null);
  const generation = useRef(0);
  const report = useCallback((e: unknown) => {
    setError(
      e instanceof ApiError && e.status === 409
        ? `版本冲突：${e.message}。已请求最新状态；请检查后重试。`
        : e instanceof Error
          ? e.message
          : String(e),
    );
  }, []);
  const acceptWorkspace = useCallback(
    async (client: Api, next: Workspace, epoch: number) => {
      if (epoch !== generation.current) return;
      if (
        revision.current?.id === next.id &&
        revision.current.revision > next.revision
      )
        return;
      const changed =
        revision.current?.branch_id !== next.branch_id ||
        loadedBranchId.current !== next.branch_id;
      revision.current = next;
      setWorkspace(next);
      setScenarioId(next.scenario_id);
      store("tianji-workspace", next.id);
      if (!next.branch_id) {
        loadedBranchId.current = null;
        setBranch(null);
        return;
      }
      if (changed) {
        // Clear the stale branch while the new one loads; fork/compare/export
        // must not act on a workspace/branch mismatch.
        setBranch(null);
        const loaded = await client.op("branch_get", { id: next.branch_id });
        if (
          epoch !== generation.current ||
          revision.current?.branch_id !== loaded.id
        )
          return;
        loadedBranchId.current = loaded.id;
        setBranch(loaded);
        setScenarioId(loaded.scenario_id);
      }
    },
    [],
  );
  const refresh = useCallback(async () => {
    const { api: client, scenarioId: id } = current.current;
    if (!client) return;
    const epoch = generation.current;
    const records = await client.op("scenario_list", {});
    if (epoch !== generation.current) return;
    setScenarios(records.items);
    if (id) {
      const list = await client.op("branch_list", { scenario_id: id });
      if (epoch === generation.current && current.current.scenarioId === id)
        setBranches(list.items);
    }
  }, []);
  const connect = async () => {
    if (!token.trim()) {
      setError("请输入本地服务令牌。令牌位于服务启动时提示的 token 文件。");
      return;
    }
    setBusy(true);
    setError("");
    const epoch = ++generation.current;
    setApi(null);
    loadedBranchId.current = null;
    try {
      const client = new Api(token.trim());
      const caps = await client.catalog();
      const records = await client.op("scenario_list", {});
      let attached: Workspace;
      const id = stored("tianji-workspace");
      try {
        attached = await client.op("workspace_attach", id ? { id } : {});
      } catch (e) {
        if (e instanceof ApiError && e.status === 404)
          attached = await client.op("workspace_attach", {});
        else throw e;
      }
      attached = await client.op("workspace_get", { id: attached.id });
      if (epoch !== generation.current) return;
      revision.current = null;
      setCatalog(caps);
      setScenarios(records.items);
      setScenarioId(records.items[0]?.id ?? "");
      setApi(client);
      store("tianji-token", token.trim());
      await acceptWorkspace(client, attached, epoch);
      let ids: string[] = [];
      try {
        const value: unknown = JSON.parse(stored("tianji-jobs") ?? "[]");
        if (Array.isArray(value))
          ids = value
            .filter((v): v is string => typeof v === "string")
            .slice(-20);
      } catch {
        /* Ignore invalid local history, never invent job state. */
      }
      const restored = await Promise.all(
        ids.map((id) => client.op("job_get", { id }).catch(() => null)),
      );
      if (epoch === generation.current) {
        const previous = restored.filter((j): j is Job => !!j);
        completed.current = new Set(
          previous.filter((j) => isTerminal(j.status)).map((j) => j.id),
        );
        setJobs(previous);
      }
    } catch (e) {
      report(e);
    } finally {
      if (epoch === generation.current) setBusy(false);
    }
  };
  const workspaceQueue = useRef<Promise<unknown>>(Promise.resolve());
  const updateWorkspace = useCallback(
    (patch: {
      branch_id?: string | null;
      scenario_id?: string;
      compare_branch_id?: string | null;
      tick?: number;
      panel?: "timeline" | "compare" | "goal";
    }) => {
      const task = async () => {
        const client = current.current.api;
        const ws = revision.current;
        if (!client || !ws) return;
        const epoch = generation.current;
        try {
          const updated = await client.op("workspace_update", {
            id: ws.id,
            revision: ws.revision,
            ...patch,
          });
          const verified = await client.op("workspace_get", { id: updated.id });
          await acceptWorkspace(client, verified, epoch);
        } catch (e) {
          if (e instanceof ApiError && e.status === 409)
            await acceptWorkspace(
              client,
              await client.op("workspace_get", { id: ws.id }),
              epoch,
            );
          report(e);
          throw e;
        }
      };
      const result = workspaceQueue.current.then(task, task);
      workspaceQueue.current = result.catch(() => undefined);
      return result;
    },
    [acceptWorkspace, report],
  );
  const selectBranch = (b: Branch) =>
    updateWorkspace({
      branch_id: b.id,
      tick: b.trajectory.frames[0].state.tick,
      panel: "timeline",
    });
  const trackJob = async (submitted: Job) => {
    const client = current.current.api;
    if (!client) return;
    const job = await client.op("job_get", { id: submitted.id });
    setJobs((old) => {
      const next = [...old.filter((j) => j.id !== job.id), job].slice(-20);
      store("tianji-jobs", JSON.stringify(next.map((j) => j.id)));
      return next;
    });
    // Persisted result is handled by the poller even if a tiny job already finished.
    completed.current.delete(job.id);
  };
  const completed = useRef(new Set<string>());
  useEffect(() => {
    if (!api) return;
    let disposed = false;
    const epoch = generation.current;
    const tick = async () => {
      try {
        const ws = revision.current;
        if (ws)
          await acceptWorkspace(
            api,
            await api.op("workspace_get", { id: ws.id }),
            epoch,
          );
        if (disposed) return;
        const records = await api.op("scenario_list", {});
        if (disposed) return;
        setScenarios(records.items);
        const id = current.current.scenarioId;
        if (id) {
          const list = await api.op("branch_list", { scenario_id: id });
          if (!disposed && current.current.scenarioId === id)
            setBranches(list.items);
        }
        for (const old of current.current.jobs) {
          if (disposed) return;
          if (isTerminal(old.status) && completed.current.has(old.id)) continue;
          const fresh = await api.op("job_get", { id: old.id });
          if (disposed) return;
          setJobs((all) => all.map((j) => (j.id === fresh.id ? fresh : j)));
          if (isTerminal(fresh.status)) {
            completed.current.add(fresh.id);
            if (fresh.status === "failed" || fresh.status === "interrupted")
              setError(
                fresh.error ??
                  `任务${fresh.status === "failed" ? "失败" : "因服务重启中断"}，请重新提交。`,
              );
            const result = fresh.result?.branch ?? fresh.result?.branches?.[0];
            if (fresh.status === "succeeded" && result) {
              await updateWorkspace({
                branch_id: result.id,
                tick: result.trajectory.frames[0].state.tick,
                panel:
                  fresh.kind === "run_backward" || fresh.kind === "backward"
                    ? "goal"
                    : "timeline",
              });
            }
          }
        }
        if (!disposed)
          setSyncAt(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
      } catch (e) {
        if (!disposed) report(e);
      }
      if (!disposed) timer = window.setTimeout(tick, 1200);
    };
    let timer = window.setTimeout(tick, 0);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [api, acceptWorkspace, report, updateWorkspace]);
  useEffect(() => {
    if (api) void refresh().catch(report);
  }, [api, scenarioId, refresh, report]);
  const act = async (task: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  return {
    token,
    setToken,
    api,
    catalog,
    scenarios,
    scenarioId,
    setScenarioId,
    branches,
    branch,
    workspace,
    jobs,
    error,
    setError,
    busy,
    syncAt,
    connect,
    refresh,
    updateWorkspace,
    selectBranch,
    trackJob,
    act,
  };
}
