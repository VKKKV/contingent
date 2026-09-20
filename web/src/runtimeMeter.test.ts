import { afterEach, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  Children,
  createElement,
  isValidElement,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Api } from "./api";
import { meterValue, latestTiming, recordTiming } from "./runTiming";
import RuntimeMeter from "./RuntimeMeter";

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return {
    ...react,
    useState: vi.fn(react.useState),
    useRef: vi.fn(react.useRef),
    useEffect: vi.fn(react.useEffect),
  };
});
afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function elements(node: ReactNode): React.ReactElement<{
  children?: ReactNode;
  onSubmit?: (event: { preventDefault: () => void }) => void;
}>[] {
  return Children.toArray(node).flatMap((child) =>
    isValidElement<{
      children?: ReactNode;
      onSubmit?: (event: { preventDefault: () => void }) => void;
    }>(child)
      ? [child, ...elements(child.props.children)]
      : [],
  );
}

it("renders when tab storage reads throw SecurityError", () => {
  vi.stubGlobal("sessionStorage", {
    getItem: () => {
      throw new DOMException("blocked", "SecurityError");
    },
  });
  const html = renderToStaticMarkup(createElement(RuntimeMeter));
  expect(html).toContain('data-testid="runtime-meter"');
  expect(html).toContain('data-testid="meter-token"');
  expect(html).toContain("未读取");
  expect(html).not.toContain('role="alert"');
});

it("publishes validated statistics even when storing the token throws SecurityError", async () => {
  const setItem = vi.fn(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  vi.stubGlobal("sessionStorage", { setItem });
  const stats = {
    scope: "saved_analyses_only",
    architecture: "single_model_single_call",
    saved_analyses: 3,
    nodes: 12,
    paths: 6,
  } as const;
  const catalog = vi.spyOn(Api.prototype, "catalog").mockResolvedValue([]);
  const op = vi.spyOn(Api.prototype, "op").mockResolvedValue(stats);
  const setStats = vi.fn(),
    setBusy = vi.fn(),
    setError = vi.fn();
  vi.mocked(useState)
    .mockReturnValueOnce(["test-token", vi.fn()])
    .mockReturnValueOnce([null, setStats])
    .mockReturnValueOnce([false, setBusy])
    .mockReturnValueOnce(["", setError]);
  vi.mocked(useRef).mockReturnValueOnce({ current: 0 });
  vi.mocked(useEffect).mockImplementationOnce(() => {});
  // Exercise the component's actual submit/refresh path without a DOM dependency.
  const form = elements(RuntimeMeter()).find(
    (element) => element.type === "form",
  )!;
  const preventDefault = vi.fn();
  form.props.onSubmit!({ preventDefault });
  await vi.waitFor(() => expect(setBusy).toHaveBeenLastCalledWith(false));
  expect(preventDefault).toHaveBeenCalledOnce();
  expect(catalog).toHaveBeenCalledOnce();
  expect(op).toHaveBeenCalledWith("analysis_stats", {});
  expect(setItem).toHaveBeenCalledWith("tianji-token", "test-token");
  expect(setStats).toHaveBeenLastCalledWith(stats);
  expect(setError.mock.calls).toEqual([[""]]);
});
it("formats actual counts without turning missing values into zero", () => {
  expect(meterValue(null)).toBe("——————");
  expect(meterValue(0)).toBe("000000");
  expect(meterValue(1000000)).toBe("1000000");
  expect(meterValue(NaN)).toBe("——————");
});
it("keeps measured duration in memory, ignoring invalid measurements", () => {
  recordTiming(1234);
  expect(latestTiming()?.milliseconds).toBe(1234);
  recordTiming(-1);
  expect(latestTiming()?.milliseconds).toBe(1234);
});
it("renders missing statistics honestly and distinguishes architecture from issue graph", () => {
  vi.stubGlobal("sessionStorage", { getItem: () => null });
  try {
    const html = renderToStaticMarkup(createElement(RuntimeMeter));
    expect(html).toContain("未读取");
    expect(html).toContain("单模型");
    expect(html).toContain("不是子代理树");
    expect(html).toContain("已保存单次调用分析");
    expect(html).toContain("同一模型 · 有界多代理任务");
    expect(html).toContain("不含新多代理运行");
    expect(html).toContain('aria-label="UTC clock"');
    expect(html).toContain('href="/vendor/divergencemeter/README.md"');
    expect(html).toContain('href="/vendor/divergencemeter/COPYING"');
    expect(html).not.toContain("nixie-ghost");
    expect(html).not.toContain("meter-select-");
    expect(html).not.toContain("无多代理运行");
    expect(html).not.toContain("1.048596");
  } finally {
    vi.unstubAllGlobals();
  }
});
