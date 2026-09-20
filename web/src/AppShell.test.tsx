import { Children, isValidElement, useState, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import AnalysisHome from "./AnalysisHome";
import RuntimeMeter from "./RuntimeMeter";

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return {
    ...react,
    useState: vi.fn(react.useState),
    // The client-only external store has no SSR snapshot. Supply its current
    // snapshot only in this markup test, without replacing the actual pages.
    useSyncExternalStore: ((subscribe, getSnapshot) =>
      react.useSyncExternalStore(
        subscribe,
        getSnapshot,
        getSnapshot,
      )) as typeof react.useSyncExternalStore,
  };
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

type Props = {
  children?: ReactNode;
  "data-testid"?: string;
  "aria-label"?: string;
  "aria-current"?: string;
  onClick?: () => void;
};
function elements(node: ReactNode): React.ReactElement<Props>[] {
  return Children.toArray(node).flatMap((child) =>
    isValidElement<Props>(child)
      ? [child, ...elements(child.props.children)]
      : [],
  );
}

describe("application destinations", () => {
  it("defaults to the real analysis page and exposes only the two supported destinations", () => {
    vi.stubGlobal("sessionStorage", { getItem: () => null });
    const html = renderToStaticMarkup(<AppShell />);
    const nav = html.match(/<nav\b[^>]*>([\s\S]*?)<\/nav>/)?.[1];
    expect(nav).toBeDefined();
    expect(nav?.match(/<button\b/g)).toHaveLength(2);
    expect(nav).toContain('data-testid="nav-meter"');
    expect(nav).toContain('data-testid="nav-vision" aria-current="page"');
    expect(html).toContain('data-testid="analysis-home"');
    expect(html).toContain('data-testid="analysis-input"');
    expect(html).toContain('data-testid="analysis-connect"');
    expect(html).not.toContain('data-testid="runtime-meter"');
    expect(html).not.toContain("nav-supply");
    expect(html).not.toContain("供应链");
    expect(html).not.toContain("run-forward");
  });

  it("routes meter, analysis and brand clicks to the existing pages with matching active navigation", () => {
    // Exercise the shell's actual click handlers and child selection without
    // adding a DOM dependency; full browser navigation is checked separately.
    let page = "vision";
    const setPage = vi.fn((next: unknown) => {
      expect(typeof next).toBe("string");
      page = next as string;
    });
    function renderShell() {
      vi.mocked(useState).mockReturnValueOnce([page, setPage]);
      const tree = AppShell();
      const nodes = elements(tree);
      return {
        nodes,
        button: (id: string) => {
          const button = nodes.find(
            (node) =>
              node.type === "button" &&
              (node.props["data-testid"] === id ||
                node.props["aria-label"] === id),
          );
          expect(button).toBeDefined();
          return button!;
        },
      };
    }
    let shell = renderShell();
    for (const destination of ["meter", "vision", "meter"] as const) {
      shell.button(`nav-${destination}`).props.onClick!();
      expect(setPage).toHaveBeenLastCalledWith(destination);
      shell = renderShell();
      expect(shell.button(`nav-${destination}`).props["aria-current"]).toBe(
        "page",
      );
      expect(
        shell.button(`nav-${destination === "meter" ? "vision" : "meter"}`)
          .props["aria-current"],
      ).toBeUndefined();
      expect(
        shell.nodes
          .filter(
            (node) => node.type === AnalysisHome || node.type === RuntimeMeter,
          )
          .map((node) => node.type),
      ).toEqual([destination === "meter" ? RuntimeMeter : AnalysisHome]);
      expect(
        shell.nodes.some((node) => node.props["data-testid"] === "nav-supply"),
      ).toBe(false);
    }
    shell.button("Contingent 目标首页").props.onClick!();
    expect(setPage).toHaveBeenLastCalledWith("vision");
    shell = renderShell();
    expect(shell.button("nav-vision").props["aria-current"]).toBe("page");
    expect(shell.nodes.some((node) => node.type === AnalysisHome)).toBe(true);
    expect(shell.nodes.some((node) => node.type === RuntimeMeter)).toBe(false);
  });
});
