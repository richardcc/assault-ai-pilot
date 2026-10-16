import { esc } from "../../core/dom.js";

export function renderCurriculumPanel(root, rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (!root) return;
  if (!list.length) {
    root.innerHTML = '<div class="muted">No curriculum traceability rows.</div>';
    return;
  }
  const recent = list.slice(0, 20);
  root.innerHTML = `
    <h3 style="margin:0 0 8px 0;">Curriculum Traceability</h3>
    <table>
      <thead><tr><th>phase</th><th>train_run_id</th><th>gate</th><th>decision</th></tr></thead>
      <tbody>
        ${recent.map((r) => `<tr>
          <td>${esc(r.phase_name || "")}</td>
          <td>${esc(r.train_run_id || "")}</td>
          <td>${esc(r.gate_result_status || "")}</td>
          <td>${esc(r.promotion_decision || "")}</td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}
