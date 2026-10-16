import { esc, fmtDate } from "../../core/dom.js";

export function renderEvalMetricsTab(ctx) {
  const rows = Array.isArray(ctx.evalRows) ? ctx.evalRows : [];
  if (!rows.length) return '<div class="muted">No eval rows.</div>';
  return `<table>
    <thead><tr><th>eval_id</th><th>created_at</th><th>scenario</th><th>results</th></tr></thead>
    <tbody>
      ${rows.map((r) => `<tr>
        <td>${esc(r.eval_id || "")}</td>
        <td>${esc(fmtDate(r.created_at_utc || ""))}</td>
        <td>${esc(r.scenario_id || "")}</td>
        <td>${esc(Array.isArray(r.results) ? r.results.length : 0)}</td>
      </tr>`).join("")}
    </tbody>
  </table>`;
}
