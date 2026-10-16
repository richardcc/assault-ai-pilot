import { esc } from "../../core/dom.js";

export function renderCompareHint(root) {
  if (!root) return;
  const old = root.innerHTML || "";
  root.innerHTML = `
    ${old}
    <div style="margin-top:10px;" class="muted">
      Compare tab moved to modular frontend. Use latest curriculum compare endpoint from Curriculum panel.
    </div>`;
}

export function renderModelSummary(root, model) {
  if (!root || !model) return;
  root.innerHTML += `<div class="muted" style="margin-top:8px;">selected model: ${esc(model.model_id || "")}</div>`;
}
