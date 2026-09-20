/** Device time in UTC; never a network-synchronized time authority. */
export function utcClock(timestamp: number) {
  const date = new Date(timestamp);
  const pair = (value: number) => String(value).padStart(2, "0");
  const time = [date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds()]
    .map(pair)
    .join(".");
  const calendarDate = [
    String(date.getUTCFullYear()).padStart(4, "0"),
    pair(date.getUTCMonth() + 1),
    pair(date.getUTCDate()),
  ].join("-");
  return { time, calendarDate, dateTime: date.toISOString() };
}

/** Re-read the wall clock on every tick and tab resume; never increment time. */
export function startUtcClock(
  update: (timestamp: number) => void,
  visibility: Pick<
    Document,
    "visibilityState" | "addEventListener" | "removeEventListener"
  > = document,
) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  const refresh = () => {
    if (stopped) return;
    clearTimeout(timer);
    const timestamp = Date.now();
    update(timestamp);
    if (visibility.visibilityState !== "hidden") {
      // Align with the next wall-clock second, including after delayed callbacks.
      timer = setTimeout(refresh, 1000 - (timestamp % 1000));
    }
  };
  visibility.addEventListener("visibilitychange", refresh);
  refresh();
  return () => {
    stopped = true;
    clearTimeout(timer);
    visibility.removeEventListener("visibilitychange", refresh);
  };
}
