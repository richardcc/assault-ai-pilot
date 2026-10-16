import { esc, fmtDate } from "../../core/dom.js";

export function renderTrainHistory(ctx) {
  const root = ctx.trainListRoot;
  const rows = Array.isArray(ctx.trainRows) ? ctx.trainRows : [];
  if (!root) return;
  if (!rows.length) {
    root.innerHTML = '<div class="muted">No train rows.</div>';
    return;
  }
  root.innerHTML = rows.map((t) => {
    const active = String(ctx.selectedTrainRun || "") === String(t.run_id || "") ? "active" : "";
    return `<div class="item ${active}" data-run-id="${esc(t.run_id || "")}">
      <div><b>${esc(t.run_id || "")}</b></div>
      <div class="muted">${esc(fmtDate(t.created_at_utc))} | scenario=${esc(t.scenario_id || "")}</div>
    </div>`;
  }).join("");
}
