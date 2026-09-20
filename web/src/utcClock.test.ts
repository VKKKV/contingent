import { afterEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import NixieClock from "./NixieClock";
import { startUtcClock, utcClock } from "./utcClock";

class Visibility extends EventTarget {
  visibilityState: DocumentVisibilityState = "visible";
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("UTC clock", () => {
  it.each([
    ["2026-01-01T00:00:00Z", "00.00.00", "2026-01-01"],
    ["2026-12-31T23:59:59Z", "23.59.59", "2026-12-31"],
    ["2026-09-19T00:04:09+08:00", "16.04.09", "2026-09-18"],
    ["2024-02-29T23:59:59Z", "23.59.59", "2024-02-29"],
  ])("uses UTC components, not local time: %s", (input, time, calendarDate) => {
    expect(utcClock(Date.parse(input))).toEqual({
      time,
      calendarDate,
      dateTime: new Date(input).toISOString(),
    });
  });

  it("renders eight local original PNGs, accessible time and no live announcements", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-19T12:34:56Z"));
    const html = renderToStaticMarkup(createElement(NixieClock));
    const paths = [...html.matchAll(/<img\b[^>]*src="([^"]+)"/g)].map(
      (match) => match[1],
    );
    expect(paths).toEqual(
      ["1", "2", "p", "3", "4", "p", "5", "6"].map(
        (digit) => `/vendor/divergencemeter/${digit}.png`,
      ),
    );
    expect(html.match(/alt=""/g)).toHaveLength(8);
    expect(html.match(/width="130" height="384"/g)).toHaveLength(8);
    expect(html).toContain('aria-label="UTC clock" aria-live="off"');
    expect(html).toContain('data-testid="meter-digits" aria-hidden="true"');
    expect(html).toContain('dateTime="2026-09-19T12:34:56.000Z"');
    expect(html).toContain("12:34:56 UTC · 2026-09-19");
    expect(html).not.toMatch(/\.gif|https?:\/\/|nixie-ghost|role="timer"/);
  });

  it("reads real wall-clock time on every tick, including delayed callbacks and clock corrections", () => {
    vi.useFakeTimers();
    const initial = Date.parse("2026-12-31T23:59:59.250Z");
    vi.setSystemTime(initial);
    const visibility = new Visibility();
    const update = vi.fn();
    const stop = startUtcClock(update, visibility);
    expect(update).toHaveBeenLastCalledWith(initial);
    vi.advanceTimersByTime(749);
    expect(update).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(utcClock(update.mock.lastCall![0]).time).toBe("00.00.00");
    expect(utcClock(update.mock.lastCall![0]).calendarDate).toBe("2027-01-01");

    const later = Date.parse("2027-01-03T07:08:09.800Z");
    vi.setSystemTime(later);
    vi.advanceTimersByTime(1000);
    expect(update).toHaveBeenLastCalledWith(later + 1000);
    const earlier = Date.parse("2026-01-01T02:03:04.400Z");
    vi.setSystemTime(earlier);
    vi.advanceTimersByTime(200);
    expect(update).toHaveBeenLastCalledWith(earlier + 200);
    expect(vi.getTimerCount()).toBe(1);
    stop();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("refreshes immediately on tab resume and cleans up timers/listeners", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    const visibility = new Visibility();
    const remove = vi.spyOn(visibility, "removeEventListener");
    const update = vi.fn();
    const stop = startUtcClock(update, visibility);
    visibility.visibilityState = "hidden";
    visibility.dispatchEvent(new Event("visibilitychange"));
    expect(vi.getTimerCount()).toBe(0);
    update.mockClear();
    vi.advanceTimersByTime(125_000);
    expect(update).not.toHaveBeenCalled();
    visibility.visibilityState = "visible";
    visibility.dispatchEvent(new Event("visibilitychange"));
    expect(update).toHaveBeenLastCalledWith(Date.now());
    expect(utcClock(update.mock.lastCall![0]).time).toBe("00.02.05");
    expect(vi.getTimerCount()).toBe(1);
    stop();
    expect(remove).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function),
    );
    update.mockClear();
    visibility.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(5000);
    expect(update).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
