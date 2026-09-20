// In-memory only: no prompt, output or timing archives.
export interface RunTiming {
  milliseconds: number;
  completedAt: string;
}
let latest: RunTiming | null = null;
export function recordTiming(milliseconds: number) {
  if (Number.isFinite(milliseconds) && milliseconds >= 0)
    latest = { milliseconds, completedAt: new Date().toISOString() };
}
export function latestTiming() {
  return latest;
}
export function meterValue(value: number | null, digits = 6): string {
  if (value === null || !Number.isFinite(value) || value < 0)
    return "—".repeat(digits);
  return Math.floor(value).toString().padStart(digits, "0");
}
