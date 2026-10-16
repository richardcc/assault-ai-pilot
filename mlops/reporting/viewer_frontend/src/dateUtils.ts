/**
 * Converts an ISO UTC timestamp into the browser's local time: "YYYY-MM-DD HH:mm:ss".
 * Handles formats such as:
 *   - "2026-06-27T07:50:37.123456Z"
 *   - "2026-06-27T07:50:37+00:00"
 *   - "2026-06-27T07:50:37" (treated as UTC when no tz offset is present)
 */
export function formatLocalDate(isoUtc?: string | null): string {
  if (!isoUtc || isoUtc === "-") return "-";
  const raw = String(isoUtc).trim();
  if (!raw || raw === "-") return "-";

  const hasTz = raw.endsWith("Z") || raw.includes("+") || /-\d{2}:\d{2}$/.test(raw);
  const normalized = hasTz ? raw : `${raw}Z`;

  const date = new Date(normalized);
  if (isNaN(date.getTime())) {
    return raw.slice(0, 19).replace("T", " ");
  }

  const pad = (n: number) => String(n).padStart(2, "0");
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const mins = pad(date.getMinutes());
  const secs = pad(date.getSeconds());

  return `${year}-${month}-${day} ${hours}:${mins}:${secs}`;
}
