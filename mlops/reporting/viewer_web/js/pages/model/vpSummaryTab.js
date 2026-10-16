import { esc } from "../../core/dom.js";

function pickMainResult(evalRows) {
  for (const row of (evalRows || [])) {
    const results = Array.isArray(row && row.results) ? row.results : [];
    if (results.length) return results[0];
  }
  return null;
}

export function renderVpSummaryTab(ctx) {
  const main = pickMainResult(ctx.evalRows);
  if (!main) return '<div class="muted">No VP summary available.</div>';
  const k = main.phase_2_9_eval_kpis || {};
  return `
    <div class="kpi-grid">
      <div class="kpi"><div class="k">xai_vp_capture_take_rate</div><div class="v">${esc(k.xai_vp_capture_take_rate ?? "-")}</div></div>
      <div class="kpi"><div class="k">tracked_captured_avg</div><div class="v">${esc(main.tracked_captured_avg ?? "-")}</div></div>
      <div class="kpi"><div class="k">timeout_rate</div><div class="v">${esc(main.timeout_rate ?? "-")}</div></div>
      <div class="kpi"><div class="k">win_rate</div><div class="v">${esc(main.win_rate ?? "-")}</div></div>
    </div>`;
}
