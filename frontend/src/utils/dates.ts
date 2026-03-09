/**
 * Date utilities for the Enigma Engine frontend.
 *
 * Backend datetimes are stored and serialized as naive UTC (no Z suffix).
 * JavaScript's Date constructor parses strings without a timezone designator
 * as LOCAL time, which would display 5h ahead for an EST user.
 * All helpers here append "Z" before parsing to force UTC interpretation,
 * then let toLocaleString/toLocaleDateString/toLocaleTimeString convert to
 * the user's browser timezone.
 */

/** Parse a UTC datetime string from the backend, handling the missing Z. */
export function parseUtc(s: string): Date {
  return new Date(s.endsWith("Z") ? s : s + "Z");
}

/** Full locale datetime string in the user's local timezone. */
export function fmtUtc(s: string): string {
  return parseUtc(s).toLocaleString();
}

/** Date-only locale string in the user's local timezone. */
export function fmtUtcDate(s: string): string {
  return parseUtc(s).toLocaleDateString();
}

/** Time-only locale string in the user's local timezone. */
export function fmtUtcTime(s: string): string {
  return parseUtc(s).toLocaleTimeString();
}

/** Human-readable relative time ("just now", "3h ago", etc.). Falls back to date string beyond 7 days. */
export function fmtRelative(s: string): string {
  const d = parseUtc(s);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}
