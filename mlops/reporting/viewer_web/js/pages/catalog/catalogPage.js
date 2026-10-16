import { getCatalog, getCurriculumTraceability } from "../../core/api.js";
import { el, esc } from "../../core/dom.js";
import { createStore } from "../../core/state.js";
import { renderCurriculumPanel } from "./curriculumTab.js";
import { renderCompareHint, renderModelSummary } from "./compareTab.js";

const store = createStore({
  catalog: null,
  selectedEngine: "",
  selectedModel: "",
  traceRows: [],
});

function engineModels(engineName) {
  const cat = store.get().catalog || {};
  const engines = Array.isArray(cat.engines) ? cat.engines : [];
  const e = engines.find((x) => String(x.engine || "") === String(engineName || ""));
  return Array.isArray(e && e.models) ? e.models : [];
}

function selectedModelRow() {
  const st = store.get();
  const models = engineModels(st.selectedEngine);
  return models.find((m) => String(m.model_id || "") === String(st.selectedModel || ""));
}

function render() {
  const st = store.get();
  const engines = Array.isArray((st.catalog || {}).engines) ? st.catalog.engines : [];
  const enginesRoot = el("engines");
  const modelsRoot = el("models");
  const historyRoot = el("history");
  if (enginesRoot) {
    enginesRoot.innerHTML = engines.map((e) => {
      const active = st.selectedEngine === e.engine ? "active" : "";
      return `<div class="item ${active}" data-engine="${esc(e.engine)}"><b>${esc(e.engine)}</b></div>`;
    }).join("");
    enginesRoot.querySelectorAll("[data-engine]").forEach((n) => {
      n.onclick = () => {
        const nextEngine = n.getAttribute("data-engine") || "";
        const firstModel = engineModels(nextEngine)[0];
        store.set({ selectedEngine: nextEngine, selectedModel: firstModel ? firstModel.model_id : "" });
      };
    });
  }
  if (modelsRoot) {
    const models = engineModels(st.selectedEngine);
    modelsRoot.innerHTML = models.map((m) => {
      const active = st.selectedModel === m.model_id ? "active" : "";
      return `<div class="item ${active}" data-model="${esc(m.model_id)}">
        <div><b>${esc(m.model_id)}</b></div>
        <div class="muted">trains=${esc(m.train_runs_count)} evals=${esc(m.eval_history_total_count)}</div>
      </div>`;
    }).join("");
    modelsRoot.querySelectorAll("[data-model]").forEach((n) => {
      n.onclick = () => store.set({ selectedModel: n.getAttribute("data-model") || "" });
      n.ondblclick = () => {
        const modelId = n.getAttribute("data-model") || "";
        const url = `/model?engine=${encodeURIComponent(st.selectedEngine)}&model=${encodeURIComponent(modelId)}`;
        window.open(url, "_blank", "noopener,noreferrer");
      };
    });
  }
  if (historyRoot) {
    const m = selectedModelRow();
    if (!m) {
      historyRoot.innerHTML = '<div class="muted">Select engine/model.</div>';
    } else {
      historyRoot.innerHTML = `
        <div class="kpi-grid">
          <div class="kpi"><div class="k">model_id</div><div class="v">${esc(m.model_id || "")}</div></div>
          <div class="kpi"><div class="k">latest_train_run_id</div><div class="v">${esc(m.latest_train_run_id || "")}</div></div>
          <div class="kpi"><div class="k">eval_history_total_count</div><div class="v">${esc(m.eval_history_total_count || 0)}</div></div>
          <div class="kpi"><div class="k">latest_eval_created_at</div><div class="v">${esc(m.latest_eval_created_at_utc || "")}</div></div>
        </div>`;
      renderCurriculumPanel(historyRoot, st.traceRows);
      renderCompareHint(historyRoot);
      renderModelSummary(historyRoot, m);
    }
  }
  const meta = el("meta");
  if (meta) {
    meta.textContent = `schema=${esc((st.catalog || {}).schema_version || "")} source=${esc((st.catalog || {}).catalog_source || "")}`;
  }
}

async function boot() {
  const catalog = await getCatalog();
  const trace = await getCurriculumTraceability(400);
  const engines = Array.isArray(catalog.engines) ? catalog.engines : [];
  const firstEngine = engines[0] || {};
  const firstModels = Array.isArray(firstEngine.models) ? firstEngine.models : [];
  store.set({
    catalog,
    selectedEngine: String(firstEngine.engine || ""),
    selectedModel: String((firstModels[0] || {}).model_id || ""),
    traceRows: Array.isArray(trace.rows) ? trace.rows : [],
  });
}

store.subscribe(render);
el("reloadBtn").onclick = () => boot().catch((e) => {
  const meta = el("meta");
  if (meta) meta.textContent = `error: ${String(e && e.message || e)}`;
});
boot().catch((e) => {
  const meta = el("meta");
  if (meta) meta.textContent = `error: ${String(e && e.message || e)}`;
});
