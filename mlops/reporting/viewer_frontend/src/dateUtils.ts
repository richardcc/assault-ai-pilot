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

export function calculateDurationSeconds(startIso?: string | null, endIso?: string | null): number | null {
  if (!startIso || !endIso) return null;
  const rawS = String(startIso).trim();
  const rawE = String(endIso).trim();
  if (!rawS || !rawE || rawS === "-" || rawE === "-") return null;

  const sHasTz = rawS.endsWith("Z") || rawS.includes("+") || /-\d{2}:\d{2}$/.test(rawS);
  const eHasTz = rawE.endsWith("Z") || rawE.includes("+") || /-\d{2}:\d{2}$/.test(rawE);

  const startMs = new Date(sHasTz ? rawS : `${rawS}Z`).getTime();
  const endMs = new Date(eHasTz ? rawE : `${rawE}Z`).getTime();

  if (isNaN(startMs) || isNaN(endMs) || endMs < startMs) return null;
  return (endMs - startMs) / 1000;
}

export function formatDuration(seconds?: number | null): string {
  if (seconds === undefined || seconds === null || isNaN(seconds) || seconds < 0) return "-";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const totalMins = Math.floor(seconds / 60);
  const remainingSecs = Math.round(seconds % 60);
  if (totalMins < 60) {
    return remainingSecs > 0 ? `${totalMins}m ${remainingSecs}s` : `${totalMins}m`;
  }
  const hours = Math.floor(totalMins / 60);
  const mins = totalMins % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

export function formatDurationDetailed(seconds?: number | null): string {
  if (seconds === undefined || seconds === null || isNaN(seconds) || seconds < 0) return "-";
  if (seconds < 60) return `${Math.round(seconds)} segundos`;
  const totalMins = Math.floor(seconds / 60);
  const remainingSecs = Math.round(seconds % 60);
  if (totalMins < 60) {
    return `${totalMins} min ${remainingSecs} seg`;
  }
  const hours = Math.floor(totalMins / 60);
  const mins = totalMins % 60;
  return `${hours}h ${mins}m ${remainingSecs}s`;
}
