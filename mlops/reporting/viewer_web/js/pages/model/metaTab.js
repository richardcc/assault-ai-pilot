import { esc } from "../../core/dom.js";

export function renderMetaTab(ctx) {
  const model = ctx.model || {};
  return `
    <div class="kpi-grid">
      <div class="kpi"><div class="k">model_id</div><div class="v">${esc(model.model_id || "")}</div></div>
      <div class="kpi"><div class="k">engine</div><div class="v">${esc(model.engine || "")}</div></div>
      <div class="kpi"><div class="k">algorithm</div><div class="v">${esc(model.algorithm || "")}</div></div>
      <div class="kpi"><div class="k">config_fingerprint</div><div class="v">${esc(model.config_fingerprint || "")}</div></div>
    </div>`;
}
