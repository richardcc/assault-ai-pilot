import { getModel, getModelEvals } from "../../core/api.js";
import { el, esc } from "../../core/dom.js";
import { queryParam } from "../../core/router.js";
import { createStore } from "../../core/state.js";
import { renderTrainHistory } from "./trainHistoryTab.js";
import { renderEvalMetricsTab } from "./evalMetricsTab.js";
import { renderVpSummaryTab } from "./vpSummaryTab.js";
import { renderMetaTab } from "./metaTab.js";
import { renderReplayTab } from "./replayTab.js";
import { renderEvalDecisionsTab } from "./evalDecisionsTab.js";
import { renderMatchReplayTab } from "./matchReplayTab.js";

const tabRegistry = {
  vpSummary: renderVpSummaryTab,
  evalMetrics: renderEvalMetricsTab,
  meta: renderMetaTab,
  replay: renderReplayTab,
  evalDecisions: renderEvalDecisionsTab,
  matchReplay: renderMatchReplayTab,
};

const store = createStore({
  engine: queryParam("engine", ""),
  modelId: queryParam("model", ""),
  model: null,
  trainRows: [],
  selectedTrainRun: "",
  selectedScenario: "__all__",
  evalRowsByKey: {},
  activeTab: "vpSummary",
});

function rowScenarioIds(row) {
  const ids = Array.isArray(row && row.scenario_ids) ? row.scenario_ids : [];
  const cleaned = ids.map((x) => String(x || "").trim()).filter((x) => x && !x.startsWith("multi:"));
  if (cleaned.length) return Array.from(new Set(cleaned));
  const sid = String((row && row.scenario_id) || "").trim();
  return sid && !sid.startsWith("multi:") ? [sid] : [];
}

function modelScenarioOptions(model) {
  const out = new Set();
  const trains = Array.isArray(model && model.train_history) ? model.train_history : [];
  const seen = Array.isArray(model && model.scenarios_seen) ? model.scenarios_seen : [];
  for (const s of seen) {
    const v = String(s || "").trim();
    if (v && !v.startsWith("multi:")) out.add(v);
  }
  for (const tr of trains) {
    for (const sid of rowScenarioIds(tr)) out.add(sid);
  }
  return Array.from(out).sort();
}

function currentEvalRows() {
  const st = store.get();
  const key = `${st.selectedTrainRun}::${st.selectedScenario}`;
  const rows = st.evalRowsByKey[key];
  return Array.isArray(rows) ? rows : [];
}

function renderToolbar() {
  const root = el("analysisToolbar");
  if (!root) return;
  const st = store.get();
  const tabs = [
    ["vpSummary", "VP Summary"],
    ["evalMetrics", "Eval Metrics"],
    ["evalDecisions", "Eval Decisions"],
    ["matchReplay", "Match Replay"],
    ["replay", "Replay"],
    ["meta", "Meta"],
  ];
  root.innerHTML = tabs.map(([id, label]) => (
    `<button class="tab-btn ${st.activeTab === id ? "active" : ""}" data-tab="${esc(id)}">${esc(label)}</button>`
  )).join("");
  root.querySelectorAll("[data-tab]").forEach((n) => {
    n.onclick = () => store.set({ activeTab: n.getAttribute("data-tab") || "vpSummary" });
  });
}

function renderScenarioFilter() {
  const root = el("scenarioFilterHost");
  if (!root) return;
  const st = store.get();
  const options = modelScenarioOptions(st.model || {});
  const html = [
    `<div class="muted">Scenario</div>`,
    `<select id="scenarioFilter" style="margin-top:4px;background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:4px;padding:4px 6px;">`,
    `<option value="__all__">all</option>`,
    ...options.map((s) => `<option value="${esc(s)}" ${st.selectedScenario === s ? "selected" : ""}>${esc(s)}</option>`),
    `</select>`,
  ].join("");
  root.innerHTML = html;
  const sel = el("scenarioFilter");
  if (sel) {
    sel.onchange = () => {
      store.set({ selectedScenario: sel.value || "__all__" });
      ensureEvalRowsForTrain().then(() => render());
    };
  }
}

function renderModelDetail() {
  const st = store.get();
  const m = st.model || {};
  const root = el("modelDetail");
  if (!root) return;
  root.innerHTML = `
    <div class="kpi-grid">
      <div class="kpi"><div class="k">model_id</div><div class="v">${esc(m.model_id || "")}</div></div>
      <div class="kpi"><div class="k">latest_train_run_id</div><div class="v">${esc(m.latest_train_run_id || "")}</div></div>
      <div class="kpi"><div class="k">train_count</div><div class="v">${esc((m.train_history || []).length)}</div></div>
      <div class="kpi"><div class="k">eval_count</div><div class="v">${esc(m.eval_history_total_count || 0)}</div></div>
    </div>`;
}

function renderAnalysisBody() {
  const root = el("analysisBody");
  if (!root) return;
  const st = store.get();
  const fn = tabRegistry[st.activeTab] || renderVpSummaryTab;
  root.innerHTML = fn({
    model: st.model,
    trainRows: st.trainRows,
    selectedTrainRun: st.selectedTrainRun,
    selectedScenario: st.selectedScenario,
    evalRows: currentEvalRows(),
  });
}

function attachTrainClicks() {
  const root = el("trainList");
  if (!root) return;
  root.querySelectorAll("[data-run-id]").forEach((n) => {
    n.onclick = async () => {
      store.set({ selectedTrainRun: n.getAttribute("data-run-id") || "" });
      await ensureEvalRowsForTrain();
      render();
    };
  });
}

function render() {
  const st = store.get();
  el("title").textContent = `Model Detail - ${String((st.model && st.model.model_id) || st.modelId || "")}`;
  renderModelDetail();
  renderScenarioFilter();
  renderTrainHistory({
    trainListRoot: el("trainList"),
    trainRows: st.trainRows,
    selectedTrainRun: st.selectedTrainRun,
  });
  attachTrainClicks();
  renderToolbar();
  renderAnalysisBody();
}

async function ensureEvalRowsForTrain() {
  const st = store.get();
  const runId = String(st.selectedTrainRun || "");
  if (!runId) return;
  const scenarioId = String(st.selectedScenario || "__all__");
  const key = `${runId}::${scenarioId}`;
  if (Object.prototype.hasOwnProperty.call(st.evalRowsByKey, key)) return;
  const payload = await getModelEvals(st.engine, st.modelId, runId, scenarioId, 0, 128);
  const rows = Array.isArray(payload && payload.rows) ? payload.rows : [];
  store.set({ evalRowsByKey: { ...store.get().evalRowsByKey, [key]: rows } });
}

async function boot() {
  const st = store.get();
  const model = await getModel(st.engine, st.modelId);
  const trainRows = Array.isArray(model && model.train_history) ? model.train_history : [];
  const selectedTrainRun = String((trainRows[0] && trainRows[0].run_id) || "");
  store.set({ model, trainRows, selectedTrainRun });
  await ensureEvalRowsForTrain();
}

store.subscribe(render);
boot().catch((e) => {
  const root = el("analysisBody");
  if (root) root.innerHTML = `<div class="muted">Error: ${esc(String(e && e.message || e))}</div>`;
});
