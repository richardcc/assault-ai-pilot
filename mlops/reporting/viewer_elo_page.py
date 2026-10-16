from __future__ import annotations


def elo_page_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ELO Evolution Viewer</title>
  <style>
    html, body { height: 100%; }
    body { font-family: Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    .wrap { box-sizing: border-box; padding: 12px; width: 100vw; height: 100vh; display: flex; flex-direction: column; gap: 10px; }
    .bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .panel { border: 1px solid #334155; border-radius: 8px; background: #111827; }
    .muted { color: #94a3b8; font-size: 12px; }
    .content { overflow: auto; min-height: 0; flex: 1; }
    .tabs { display:flex; gap:8px; margin-top:8px; }
    .tab-btn { padding:6px 10px; border:1px solid #475569; border-radius:6px; cursor:pointer; background:#1f2937; color:#e2e8f0; }
    .tab-btn.active { background:#0ea5e9; color:#0f172a; border-color:#0ea5e9; font-weight:700; }
    .tab-pane { display:none; }
    .tab-pane.active { display:block; }
    .chart-wrap { width:100%; height:420px; border:1px solid #334155; border-radius:8px; background:#0b1220; padding:8px; box-sizing:border-box; }
    .chart-svg { width:100%; height:100%; display:block; }
    button { background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; cursor: pointer; }
    button:hover { background: #475569; }
    select, input {
      background:#1e293b; color:#e2e8f0; border:1px solid #475569; border-radius:4px; padding:4px 6px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border: 1px solid #334155; padding: 6px; text-align: left; vertical-align: top; }
    th { background: #1f2937; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="bar">
      <h1 style="margin:0;font-size:20px;">ELO Evolution (Standalone)</h1>
      <span id="meta" class="muted"></span>
    </div>
    <div class="bar panel" style="padding:8px;">
      <label>engine <select id="engineSelect"></select></label>
      <label>model (single) <select id="modelSelect"></select></label>
      <label>compare models
        <select id="modelMultiSelect" multiple size="5" style="min-width:380px;max-width:520px;"></select>
      </label>
      <button id="modelMultiAllBtn" title="Select all visible models">All models</button>
      <button id="modelMultiNoneBtn" title="Clear model selection">Clear models</button>
      <label>side <select id="sideSelect"><option value="__all__">all</option></select></label>
      <label>controller <select id="controllerSelect"><option value="__all__">all</option></select></label>
      <label>created_at <input id="createdAtFilter" type="text" placeholder="contains..." style="width:140px;" /></label>
      <label>eval_id <input id="evalIdFilter" type="text" placeholder="contains..." style="width:120px;" /></label>
      <label>scenario <select id="scenarioFilter"><option value="__all__">all</option></select></label>
      <label>type/profile <select id="profileFilter"><option value="__all__">all</option></select></label>
      <label>curriculum phase <select id="curriculumPhaseFilter"><option value="__all__">all</option></select></label>
      <label>chart granularity
        <select id="chartGranularitySelect">
          <option value="eval" selected>per eval</option>
          <option value="episode">per episode/row</option>
        </select>
      </label>
      <label>ELO scoring
        <select id="eloScoringSelect">
          <option value="classic" selected>classic (W/D/L)</option>
          <option value="outcome_weighted">outcome weighted</option>
        </select>
      </label>
      <label>2nd metric
        <select id="secondaryMetricSelect">
          <option value="tracked_captured_avg" selected>tracked_captured_avg</option>
          <option value="vp_net_avg_side">vp_net_avg_side</option>
        </select>
      </label>
      <button id="reloadBtn">Reload</button>
      <button id="openModelBtn">Open Model Detail</button>
      <span class="muted">Proxy ELO: start=1200, K=24, weighted by episodes. Overlay shows 2nd metric on right axis.</span>
    </div>
    <div class="tabs">
      <button id="tabSummaryBtn" class="tab-btn active">Summary Table</button>
      <button id="tabChartBtn" class="tab-btn">ELO Chart</button>
    </div>
    <div id="tabSummary" class="panel content tab-pane active" style="padding:8px;"></div>
    <div id="tabChart" class="panel content tab-pane" style="padding:8px;">
      <div id="chartRoot" class="chart-wrap"></div>
    </div>
  </div>
  <script>
    const el = (id) => document.getElementById(id);
    const esc = (v) => String((v === undefined || v === null) ? "" : v).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
    const q = new URLSearchParams(window.location.search);
    let selectedEngine = String(q.get("engine") || "");
    let selectedModel = String(q.get("model") || "__all__");
    let selectedModels = [];
    let selectedModelsInitialized = false;
    let selectedSide = "__all__";
    let selectedController = "MuZero";
    let scenarioFilter = "__all__";
    let profileFilter = "__all__";
    let curriculumPhaseFilter = "__all__";
    let createdAtFilter = "";
    let evalIdFilter = "";
    let chartGranularity = "eval";
    let eloScoringMode = "classic";
    let secondaryMetric = "tracked_captured_avg";
    let activeTab = "summary";
    let catalog = null;
    let eloRowsUniverse = [];
    let eloLastError = "";
    let eloCalcNote = "";

    function safeNum(v) {
      if (v === null || v === undefined || v === "") return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    }
    function shortModelId(v, maxLen) {
      const raw = String(v || "");
      const lim = Math.max(8, Number(maxLen || 28));
      if (raw.length <= lim) return raw;
      return raw.slice(0, lim - 1) + "…";
    }
    function fmtNum(v, d) {
      const n = safeNum(v);
      const dd = Number.isFinite(Number(d)) ? Math.max(0, Math.min(6, Number(d))) : 3;
      return n === null ? "N/A" : n.toFixed(dd);
    }
    function fmtLocal(s) {
      if (!s || s === "-") return "-";
      var raw = String(s).trim();
      if (!raw || raw === "-") return "-";
      var hasTz = raw.endsWith("Z") || raw.indexOf("+") >= 0 || /-\\d{2}:\\d{2}$/.test(raw);
      var d = new Date(hasTz ? raw : raw + "Z");
      if (isNaN(d.getTime())) return raw.slice(0, 19).replace("T", " ");
      var pad = function(n) { return (n < 10 ? "0" : "") + n; };
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " +
             pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }
    function currentEngineRow() {
      const engines = Array.isArray(catalog && catalog.engines) ? catalog.engines : [];
      return engines.find(e => String((e && e.engine) || "") === selectedEngine) || { models: [] };
    }
    async function loadEloUniverse() {
      if (!selectedEngine) {
        eloRowsUniverse = [];
        return;
      }
      const p = new URLSearchParams();
      p.set("engine", String(selectedEngine));
      p.set("model", "__all__");
      p.set("limit", "50000");
      const r = await fetch("/api/v2/elo?" + p.toString());
      const payload = await r.json();
      eloRowsUniverse = Array.isArray(payload && payload.rows) ? payload.rows : [];
      eloLastError = String((payload && payload.error) || "");
    }
    function buildRows() {
      const rows = (Array.isArray(eloRowsUniverse) ? eloRowsUniverse : []).map(function (r) {
        return {
          model_id: String(r.model_id || ""),
          created_at_utc: String(r.created_at_utc || ""),
          eval_id: String(r.eval_id || ""),
          scenario_id: String(r.scenario_id || ""),
          matchup_profile: String(r.matchup_profile || ""),
          curriculum_phase: String(r.curriculum_phase || ""),
          side: String(r.side || ""),
          controller: String(r.controller || "Unknown"),
          seed: safeNum(r.seed),
          episodes: Math.max(1, Number(r.episodes || 1)),
          score: safeNum(r.score),
          draw_rate: safeNum(r.draw_rate),
          total_victory_rate: safeNum(r.total_victory_rate),
          victory_rate: safeNum(r.victory_rate),
          defeat_rate: safeNum(r.defeat_rate),
          total_defeat_rate: safeNum(r.total_defeat_rate),
          tracked_captured_avg: safeNum(r.tracked_captured_avg),
          vp_net_avg_side: safeNum(r.vp_net_avg_side),
        };
      });
      rows.sort((a, b) => {
        const ta = Date.parse(String(a.created_at_utc || "")) || 0;
        const tb = Date.parse(String(b.created_at_utc || "")) || 0;
        if (ta !== tb) return tb - ta;
        return String(b.eval_id || "").localeCompare(String(a.eval_id || ""));
      });
      const createdNeedle = String(createdAtFilter || "").trim().toLowerCase();
      const evalNeedle = String(evalIdFilter || "").trim().toLowerCase();
      return rows.filter(function (r) {
        if (Array.isArray(selectedModels) && selectedModels.length > 0 && !selectedModels.includes(String(r.model_id || ""))) return false;
        if (selectedSide !== "__all__" && String(r.side || "") !== selectedSide) return false;
        if (selectedController !== "__all__" && String(r.controller || "") !== selectedController) return false;
        if (scenarioFilter !== "__all__" && String(r.scenario_id || "") !== scenarioFilter) return false;
        if (profileFilter !== "__all__" && String(r.matchup_profile || "") !== profileFilter) return false;
        if (curriculumPhaseFilter !== "__all__" && String(r.curriculum_phase || "") !== curriculumPhaseFilter) return false;
        if (createdNeedle && String(r.created_at_utc || "").toLowerCase().indexOf(createdNeedle) < 0) return false;
        if (evalNeedle && String(r.eval_id || "").toLowerCase().indexOf(evalNeedle) < 0) return false;
        return true;
      });
    }
    function renderSelectors() {
      const engines = Array.isArray(catalog && catalog.engines) ? catalog.engines : [];
      if (!selectedEngine && engines.length) selectedEngine = String((engines[0] && engines[0].engine) || "");
      el("engineSelect").innerHTML = engines.map(function (e) {
        const eid = String((e && e.engine) || "");
        return "<option value='" + esc(eid) + "' " + (eid === selectedEngine ? "selected" : "") + ">" + esc(eid) + "</option>";
      }).join("");

      const models = (Array.isArray(currentEngineRow().models) ? currentEngineRow().models : []).slice();
      models.sort(function (a, b) {
        const aEval = Date.parse(String((a && a.latest_eval_created_at_utc) || "")) || 0;
        const bEval = Date.parse(String((b && b.latest_eval_created_at_utc) || "")) || 0;
        if (aEval !== bEval) return bEval - aEval;
        return String((a && a.model_id) || "").localeCompare(String((b && b.model_id) || ""));
      });
      const modelIds = models.map(m => String((m && m.model_id) || "")).filter(Boolean);
      if (!selectedModel) selectedModel = "__all__";
      if (selectedModel !== "__all__" && !modelIds.includes(selectedModel)) selectedModel = "__all__";
      el("modelSelect").innerHTML = ["<option value='__all__' " + (selectedModel === "__all__" ? "selected" : "") + ">all</option>"].concat(
        models.map(function (m) {
          const mid = String((m && m.model_id) || "");
          const evalTs = String((m && m.latest_eval_created_at_utc) || "");
          const trainTs = String((m && m.latest_train_created_at_utc) || "");
          const stamp = fmtLocal(evalTs || trainTs);
          const source = evalTs ? "eval" : (trainTs ? "train" : "na");
          const label = stamp && stamp !== "-" ? (shortModelId(mid, 30) + " [" + source + ": " + stamp + "]") : shortModelId(mid, 30);
          return "<option value='" + esc(mid) + "' title='" + esc(mid) + "' " + (selectedModel === mid ? "selected" : "") + ">" + esc(label) + "</option>";
        })
      ).join("");

      const multi = el("modelMultiSelect");
      if (multi) {
        selectedModels = (Array.isArray(selectedModels) ? selectedModels : []).filter(mid => modelIds.includes(String(mid)));
        if (!selectedModelsInitialized) {
          if (selectedModel && selectedModel !== "__all__" && modelIds.includes(selectedModel)) selectedModels = [selectedModel];
          else selectedModels = modelIds.slice();
          selectedModelsInitialized = true;
        }
        multi.innerHTML = modelIds.map(function (mid) {
          const m = models.find(x => String((x && x.model_id) || "") === mid) || {};
          const evalTs = String((m && m.latest_eval_created_at_utc) || "");
          const trainTs = String((m && m.latest_train_created_at_utc) || "");
          const stamp = fmtLocal(evalTs || trainTs);
          const source = evalTs ? "eval" : (trainTs ? "train" : "na");
          const label = stamp && stamp !== "-" ? (shortModelId(mid, 32) + " [" + source + ": " + stamp + "]") : shortModelId(mid, 32);
          const sel = selectedModels.includes(mid) ? " selected" : "";
          return "<option value='" + esc(mid) + "'" + sel + " title='" + esc(mid) + "'>" + esc(label) + "</option>";
        }).join("");
      }

      function renderDistinctSelect(selectId, key, selectedVal) {
        const set = {};
        for (const row of (Array.isArray(eloRowsUniverse) ? eloRowsUniverse : [])) {
          const v = String((row && row[key]) || "");
          // Hide synthetic aggregate scenario id (multi:...) from scenario selector.
          // Users should filter by concrete scenario ids only.
          if (key === "scenario_id" && v.startsWith("multi:")) continue;
          if (v) set[v] = true;
        }
        const vals = Object.keys(set).sort();
        const html = ["<option value='__all__'>all</option>"].concat(vals.map(function (v) {
          return "<option value='" + esc(v) + "' " + (String(selectedVal) === v ? "selected" : "") + ">" + esc(v) + "</option>";
        })).join("");
        el(selectId).innerHTML = html;
      }
      renderDistinctSelect("sideSelect", "side", selectedSide);
      renderDistinctSelect("controllerSelect", "controller", selectedController);
      renderDistinctSelect("scenarioFilter", "scenario_id", scenarioFilter);
      renderDistinctSelect("profileFilter", "matchup_profile", profileFilter);
      renderDistinctSelect("curriculumPhaseFilter", "curriculum_phase", curriculumPhaseFilter);
      el("createdAtFilter").value = createdAtFilter;
      el("evalIdFilter").value = evalIdFilter;
      const granNode = el("chartGranularitySelect");
      if (granNode) granNode.value = String(chartGranularity || "eval");
      const eloModeNode = el("eloScoringSelect");
      if (eloModeNode) eloModeNode.value = String(eloScoringMode || "classic");
      const secMetricNode = el("secondaryMetricSelect");
      if (secMetricNode) secMetricNode.value = String(secondaryMetric || "tracked_captured_avg");
    }
    function renderSummary(rows) {
      const root = el("tabSummary");
      if (!root) return;
      if (!rows.length) {
        root.innerHTML = "<div class='muted'>No rows for current filters.</div>";
        return;
      }
      const sample = rows.slice(0, 300);
      const tr = sample.map(function (r) {
        return "<tr>" +
          "<td>" + esc(r.model_id) + "</td>" +
          "<td>" + esc(r.eval_id) + "</td>" +
          "<td>" + esc(fmtLocal(r.created_at_utc)) + "</td>" +
          "<td>" + esc(r.side) + "</td>" +
          "<td>" + esc(r.controller) + "</td>" +
          "<td>" + esc(r.scenario_id) + "</td>" +
          "<td>" + esc(r.matchup_profile) + "</td>" +
          "<td>" + fmtNum(r.score, 3) + "</td>" +
          "<td>" + esc(String(r.episodes || 0)) + "</td>" +
          "</tr>";
      }).join("");
      root.innerHTML = "<div class='muted' style='margin-bottom:8px;'>rows: " + esc(String(rows.length)) + (eloLastError ? (" | source error: " + esc(eloLastError)) : "") + "</div>" +
        "<table><thead><tr>" +
        "<th>model</th><th>eval_id</th><th>created_at</th><th>side</th><th>controller</th><th>scenario</th><th>profile</th><th>score</th><th>episodes</th>" +
        "</tr></thead><tbody>" + tr + "</tbody></table>";
    }
    function renderEloChart(rows) {
      const host = el("chartRoot");
      if (!host) return;
      const raw = Array.isArray(rows) ? rows.slice() : [];
      const muzeroOnly = raw.filter(function (r) {
        return String((r && r.controller) || "").toLowerCase() === "muzero";
      });
      const src = (muzeroOnly.length > 0) ? muzeroOnly : raw;
      eloCalcNote = (muzeroOnly.length > 0)
        ? "ELO input filtered to controller=MuZero rows."
        : "ELO input uses all rows (MuZero-only rows not found).";
      if (!src.length) {
        host.innerHTML = "<div class='muted'>No chart data.</div>";
        return;
      }
      function eloScoreFromRow(r) {
        if (String(eloScoringMode) === "outcome_weighted") {
          const tv = Number((r && r.total_victory_rate) || 0);
          const v = Number((r && r.victory_rate) || 0);
          const d = Number((r && r.draw_rate) || 0);
          const df = Number((r && r.defeat_rate) || 0);
          const td = Number((r && r.total_defeat_rate) || 0);
          // Outcome-aware weights (can be tuned later):
          // total victory=1.00, victory=0.75, draw=0.50, defeat=0.25, total defeat=0.00
          return (1.00 * tv) + (0.75 * v) + (0.50 * d) + (0.25 * df) + (0.00 * td);
        }
        return Number((r && r.score) || 0);
      }
      const byModel = {};
      for (const r of src) {
        const mid = String((r && r.model_id) || "");
        if (!mid) continue;
        if (!byModel[mid]) byModel[mid] = [];
        byModel[mid].push(r);
      }
      const modelIds = Object.keys(byModel).sort();
      const modelSeries = {};
      for (const mid of modelIds) {
        let rowsModel = [];
        if (String(chartGranularity) === "episode") {
          rowsModel = byModel[mid].map(function (r) {
            return {
              eval_id: String((r && r.eval_id) || ""),
              created_at_utc: String((r && r.created_at_utc) || ""),
              matchup_profile: String((r && r.matchup_profile) || ""),
              side: String((r && r.side) || ""),
              seed: Number((r && r.seed) || 0),
              episodes: Math.max(1, Number((r && r.episodes) || 1)),
              score: Number((r && r.score) || 0),
              draw_rate: Number((r && r.draw_rate) || 0),
              total_victory_rate: Number((r && r.total_victory_rate) || 0),
              victory_rate: Number((r && r.victory_rate) || 0),
              defeat_rate: Number((r && r.defeat_rate) || 0),
              total_defeat_rate: Number((r && r.total_defeat_rate) || 0),
              tracked_captured_avg: Number((r && r.tracked_captured_avg) || 0),
              vp_net_avg_side: Number((r && r.vp_net_avg_side) || 0),
            };
          }).sort(function (a, b) {
            const ta = Date.parse(String((a && a.created_at_utc) || "")) || 0;
            const tb = Date.parse(String((b && b.created_at_utc) || "")) || 0;
            if (ta !== tb) return ta - tb;
            const evalCmp = String((a && a.eval_id) || "").localeCompare(String((b && b.eval_id) || ""));
            if (evalCmp !== 0) return evalCmp;
            const profCmp = String((a && a.matchup_profile) || "").localeCompare(String((b && b.matchup_profile) || ""));
            if (profCmp !== 0) return profCmp;
            const sideCmp = String((a && a.side) || "").localeCompare(String((b && b.side) || ""));
            if (sideCmp !== 0) return sideCmp;
            return Number((a && a.seed) || 0) - Number((b && b.seed) || 0);
          });
        } else {
          const buckets = {};
          for (const r of byModel[mid]) {
            const evalId = String((r && r.eval_id) || "");
            const ts = String((r && r.created_at_utc) || "");
            const key = evalId ? ("eval:" + evalId) : ("ts:" + ts);
            if (!buckets[key]) buckets[key] = { eval_id: evalId, created_at_utc: ts, episodes: 0, score_num: 0.0, score_den: 0.0 };
            const b = buckets[key];
            const eps = Math.max(1, Number((r && r.episodes) || 1));
            const score = eloScoreFromRow(r);
            b.episodes += eps;
            b.score_num += score * eps;
            b.score_den += eps;
            b.tracked_num = Number((b.tracked_num || 0)) + (Number((r && r.tracked_captured_avg) || 0) * eps);
            b.vpnet_num = Number((b.vpnet_num || 0)) + (Number((r && r.vp_net_avg_side) || 0) * eps);
          }
          rowsModel = Object.values(buckets).map(function (b) {
            const den = Math.max(1, Number((b && b.score_den) || 0));
            return {
              eval_id: String((b && b.eval_id) || ""),
              created_at_utc: String((b && b.created_at_utc) || ""),
              episodes: Math.max(1, Number((b && b.episodes) || 1)),
              score: Number((b && b.score_num) || 0) / den,
              tracked_captured_avg: Number((b && b.tracked_num) || 0) / den,
              vp_net_avg_side: Number((b && b.vpnet_num) || 0) / den,
            };
          }).sort(function (a, b) {
            const ta = Date.parse(String((a && a.created_at_utc) || "")) || 0;
            const tb = Date.parse(String((b && b.created_at_utc) || "")) || 0;
            if (ta !== tb) return ta - tb;
            return String((a && a.eval_id) || "").localeCompare(String((b && b.eval_id) || ""));
          });
        }
        let elo = 1200.0;
        const K = 24.0;
        const pts = [];
        for (let i = 0; i < rowsModel.length; i += 1) {
          const r = rowsModel[i] || {};
          const eps = Math.max(1, Number(r.episodes || 1));
          const score = eloScoreFromRow(r);
          const weight = Math.max(0.25, Math.min(3.0, eps / 20.0));
          const delta = K * (score - 0.5) * weight;
          elo += delta;
          pts.push({
            x: i + 1,
            y: elo,
            eval_id: String(r.eval_id || ""),
            score: score,
            tracked_captured_avg: Number((r && r.tracked_captured_avg) || 0),
            vp_net_avg_side: Number((r && r.vp_net_avg_side) || 0),
            delta_elo: delta,
            label: (
              String(r.eval_id || "") + " | " + fmtLocal(r.created_at_utc) + " | " +
              String((r.matchup_profile || "")) + " | side=" + String((r.side || "")) +
              " | seed=" + String((r.seed || "")) + " | " + mid
            ),
          });
        }
        modelSeries[mid] = pts;
      }
      const chosenModel = (
        selectedModel && selectedModel !== "__all__" && modelSeries[selectedModel]
          ? String(selectedModel)
          : (Array.isArray(selectedModels) && selectedModels.length > 0 && modelSeries[selectedModels[0]]
              ? String(selectedModels[0]) : String(modelIds[0] || ""))
      );
      const topPts = Array.isArray(modelSeries[chosenModel]) ? modelSeries[chosenModel] : [];
      const finalRows = modelIds
        .map(function (mid) {
          const pts = Array.isArray(modelSeries[mid]) ? modelSeries[mid] : [];
          const last = pts.length ? pts[pts.length - 1] : null;
          return { model_id: mid, final_elo: last ? Number(last.y || 1200) : 1200, points: pts.length };
        })
        .sort(function (a, b) { return Number(b.final_elo || 0) - Number(a.final_elo || 0); });

      const width = Math.max(760, host.clientWidth - 20);
      const topHeight = 250;
      const bottomHeight = 240;
      const padL = 56;
      const padR = 20;
      const padT = 20;
      const padB = 40;
      const evalColorPalette = [
        "#22d3ee", "#a78bfa", "#f59e0b", "#34d399", "#f472b6",
        "#60a5fa", "#f97316", "#84cc16", "#e879f9", "#f43f5e",
      ];
      function colorForEvalId(evalId) {
        const s = String(evalId || "");
        let h = 0;
        for (let i = 0; i < s.length; i += 1) {
          h = ((h * 31) + s.charCodeAt(i)) | 0;
        }
        const idx = Math.abs(h) % evalColorPalette.length;
        return evalColorPalette[idx];
      }

      function renderTopLine() {
        if (!topPts.length) return "<div class='muted'>No points for selected model.</div>";
        const minY = Math.min.apply(null, topPts.map(function (p) { return Number(p.y || 0); }));
        const maxY = Math.max.apply(null, topPts.map(function (p) { return Number(p.y || 0); }));
        const ySpan = Math.max(1e-6, maxY - minY);
        const xMax = Math.max(1, topPts.length - 1);
        const sx = function (i) { return padL + ((width - padL - padR) * (i / xMax)); };
        const sy = function (v) { const t = (Number(v || 0) - minY) / ySpan; return (topHeight - padB) - (topHeight - padT - padB) * t; };
        const secVals = topPts.map(function (p) {
          return Number(
            String(secondaryMetric) === "vp_net_avg_side"
              ? (p.vp_net_avg_side || 0)
              : (p.tracked_captured_avg || 0)
          );
        });
        const secMin = Math.min.apply(null, secVals);
        const secMax = Math.max.apply(null, secVals);
        const secSpan = Math.max(1e-6, secMax - secMin);
        const sy2 = function (v) {
          const t = (Number(v || 0) - secMin) / secSpan;
          return (topHeight - padB) - (topHeight - padT - padB) * t;
        };
        let grid = "";
        for (let i = 0; i <= 5; i += 1) {
          const yy = padT + ((topHeight - padT - padB) * (i / 5));
          const yVal = maxY - (ySpan * (i / 5));
          grid += "<line x1='" + padL + "' y1='" + yy.toFixed(2) + "' x2='" + (width - padR) + "' y2='" + yy.toFixed(2) + "' stroke='#1e293b' stroke-width='1' />";
          grid += "<text x='" + (padL - 6) + "' y='" + (yy + 4).toFixed(2) + "' fill='#94a3b8' font-size='11' text-anchor='end'>" + esc(yVal.toFixed(1)) + "</text>";
        }
        let evalBoundaries = "";
        for (let i = 1; i < topPts.length; i += 1) {
          const prevEval = String((topPts[i - 1] && topPts[i - 1].eval_id) || "");
          const curEval = String((topPts[i] && topPts[i].eval_id) || "");
          if (prevEval && curEval && prevEval !== curEval) {
            const xb = (sx(i - 1) + sx(i)) / 2.0;
            evalBoundaries += "<line x1='" + xb.toFixed(2) + "' y1='" + padT + "' x2='" + xb.toFixed(2) + "' y2='" + (topHeight - padB) + "' stroke='#475569' stroke-width='1' stroke-dasharray='3 3'><title>" + esc("eval boundary: " + prevEval + " -> " + curEval) + "</title></line>";
          }
        }
        let segs = "";
        for (let i = 1; i < topPts.length; i += 1) {
          const p0 = topPts[i - 1];
          const p1 = topPts[i];
          const segColor = Number(p1.delta_elo || 0) >= 0 ? "#22c55e" : "#ef4444";
          segs += "<line x1='" + sx(i - 1).toFixed(2) + "' y1='" + sy(p0.y).toFixed(2) + "' x2='" + sx(i).toFixed(2) + "' y2='" + sy(p1.y).toFixed(2) + "' stroke='" + segColor + "' stroke-width='2'><title>" + esc("delta_elo=" + Number(p1.delta_elo || 0).toFixed(3)) + "</title></line>";
        }
        const circles = topPts.map(function (p, i) {
          const pointColor = Number(p.delta_elo || 0) >= 0 ? "#22c55e" : "#ef4444";
          return "<circle cx='" + sx(i).toFixed(2) + "' cy='" + sy(p.y).toFixed(2) + "' r='2.8' fill='" + pointColor + "'><title>" + esc(p.label + " | score=" + Number(p.score || 0).toFixed(3) + " | delta_elo=" + Number(p.delta_elo || 0).toFixed(3) + " | elo=" + Number(p.y || 0).toFixed(2)) + "</title></circle>";
        }).join("");
        const secPath = topPts.map(function (p, i) {
          const v = String(secondaryMetric) === "vp_net_avg_side"
            ? Number(p.vp_net_avg_side || 0)
            : Number(p.tracked_captured_avg || 0);
          return (i === 0 ? "M" : "L") + sx(i).toFixed(2) + "," + sy2(v).toFixed(2);
        }).join(" ");
        let secTicks = "";
        for (let i = 0; i <= 5; i += 1) {
          const yy = padT + ((topHeight - padT - padB) * (i / 5));
          const vv = secMax - (secSpan * (i / 5));
          secTicks += "<text x='" + (width - padR + 6) + "' y='" + (yy + 4).toFixed(2) + "' fill='#94a3b8' font-size='11' text-anchor='start'>" + esc(vv.toFixed(2)) + "</text>";
        }
        const granText = (String(chartGranularity) === "episode") ? "episode rows" : "evals";
        const secLabel = String(secondaryMetric) === "vp_net_avg_side" ? "vp_net_avg_side" : "tracked_captured_avg";
        return "<div class='muted' style='margin:0 0 6px 0;'>Selected model: <b>" + esc(chosenModel) + "</b> (" + esc(String(topPts.length)) + " " + esc(granText) + ", axis = sequence index). ELO scoring=" + esc(eloScoringMode) + ", 2nd metric=" + esc(secLabel) + "</div>" +
          "<svg class='chart-svg' viewBox='0 0 " + width + " " + topHeight + "' preserveAspectRatio='none'>" +
          "<rect x='0' y='0' width='" + width + "' height='" + topHeight + "' fill='#0b1220' />" +
          grid +
          evalBoundaries +
          "<line x1='" + padL + "' y1='" + (topHeight - padB) + "' x2='" + (width - padR) + "' y2='" + (topHeight - padB) + "' stroke='#334155' stroke-width='1.2' />" +
          "<line x1='" + padL + "' y1='" + padT + "' x2='" + padL + "' y2='" + (topHeight - padB) + "' stroke='#334155' stroke-width='1.2' />" +
          segs +
          "<path d='" + secPath + "' fill='none' stroke='#38bdf8' stroke-width='1.6' stroke-dasharray='4 3' />" +
          circles +
          secTicks +
          "<text x='" + (width / 2).toFixed(2) + "' y='" + (topHeight - 8) + "' fill='#94a3b8' font-size='11' text-anchor='middle'>evaluation order (1..N), green=ELO up, red=ELO down</text>" +
          "</svg>";
      }

      function renderBottomBars() {
        if (!finalRows.length) return "<div class='muted'>No final ELO values.</div>";
        const minY = Math.min.apply(null, finalRows.map(function (r) { return Number(r.final_elo || 0); }));
        const maxY = Math.max.apply(null, finalRows.map(function (r) { return Number(r.final_elo || 0); }));
        const ySpan = Math.max(1e-6, maxY - minY);
        const chartMin = minY - Math.max(10, ySpan * 0.15);
        const chartMax = maxY + Math.max(10, ySpan * 0.10);
        const chartSpan = Math.max(1e-6, chartMax - chartMin);
        const usableW = (width - padL - padR);
        const slotW = usableW / Math.max(1, finalRows.length);
        const laneGap = 6;
        const mainBarW = Math.max(10, Math.min(36, slotW * 0.38));
        const miniLaneW = Math.max(0, slotW - mainBarW - laneGap - 8);
        const miniBarGap = 1;
        const sy = function (v) { const t = (Number(v || 0) - chartMin) / chartSpan; return (bottomHeight - padB) - (bottomHeight - padT - padB) * t; };
        let grid = "";
        for (let i = 0; i <= 5; i += 1) {
          const yy = padT + ((bottomHeight - padT - padB) * (i / 5));
          const yVal = chartMax - (chartSpan * (i / 5));
          grid += "<line x1='" + padL + "' y1='" + yy.toFixed(2) + "' x2='" + (width - padR) + "' y2='" + yy.toFixed(2) + "' stroke='#1e293b' stroke-width='1' />";
          grid += "<text x='" + (padL - 6) + "' y='" + (yy + 4).toFixed(2) + "' fill='#94a3b8' font-size='11' text-anchor='end'>" + esc(yVal.toFixed(1)) + "</text>";
        }
        let bars = "";
        for (let i = 0; i < finalRows.length; i += 1) {
          const rr = finalRows[i];
          const slotX = padL + (i * slotW);
          const x0 = slotX + 4;
          const y0 = sy(rr.final_elo);
          const yBase = sy(chartMin);
          const h = Math.max(1, yBase - y0);
          const fill = (String(rr.model_id) === String(chosenModel)) ? "#22d3ee" : "#a78bfa";
          bars += "<rect x='" + x0.toFixed(2) + "' y='" + y0.toFixed(2) + "' width='" + mainBarW.toFixed(2) + "' height='" + h.toFixed(2) + "' fill='" + fill + "' opacity='0.9'><title>" + esc(rr.model_id + " | final_elo=" + Number(rr.final_elo).toFixed(2)) + "</title></rect>";
          bars += "<text x='" + (x0 + (mainBarW / 2)).toFixed(2) + "' y='" + (Math.max(12, y0 - 4)).toFixed(2) + "' fill='#e2e8f0' font-size='10' text-anchor='middle'>" + esc(Number(rr.final_elo || 0).toFixed(1)) + "</text>";
          bars += "<text x='" + (x0 + (mainBarW / 2)).toFixed(2) + "' y='" + (bottomHeight - 20) + "' fill='#94a3b8' font-size='10' text-anchor='middle'>" + esc(String(i + 1)) + "</text>";
          bars += "<text x='" + (x0 + (mainBarW / 2)).toFixed(2) + "' y='" + (bottomHeight - 8) + "' fill='#64748b' font-size='9' text-anchor='middle'>" + esc(shortModelId(rr.model_id, 14)) + "</text>";

          const pts = Array.isArray(modelSeries[String(rr.model_id)]) ? modelSeries[String(rr.model_id)] : [];
          if (miniLaneW > 4 && pts.length > 0) {
            // Compact to one mini-bar per eval_id: use final ELO reached within each eval.
            const evalFinals = [];
            const evalIndexById = {};
            for (let j = 0; j < pts.length; j += 1) {
              const pj = pts[j] || {};
              const eid = String(pj.eval_id || ("idx_" + String(j)));
              if (!Object.prototype.hasOwnProperty.call(evalIndexById, eid)) {
                evalIndexById[eid] = evalFinals.length;
                evalFinals.push({ eval_id: eid, y: Number(pj.y || 1200) });
              } else {
                evalFinals[evalIndexById[eid]].y = Number(pj.y || 1200);
              }
            }
            const miniX0 = x0 + mainBarW + laneGap;
            const miniCount = evalFinals.length;
            const miniStep = miniLaneW / Math.max(1, miniCount);
            const miniBarW = Math.max(1, Math.min(8, miniStep - miniBarGap));
            for (let j = 0; j < miniCount; j += 1) {
              const pj = evalFinals[j] || {};
              const xj = miniX0 + (j * miniStep);
              const yj = sy(pj.y);
              const hj = Math.max(1, yBase - yj);
              const miniFill = colorForEvalId(pj.eval_id || ("idx_" + String(j)));
              const miniStroke = (String(rr.model_id) === String(chosenModel) && j === (miniCount - 1)) ? "#22d3ee" : "none";
              const miniStrokeW = (miniStroke === "none") ? 0 : 1.0;
              bars += "<rect x='" + xj.toFixed(2) + "' y='" + yj.toFixed(2) + "' width='" + miniBarW.toFixed(2) + "' height='" + hj.toFixed(2) + "' fill='" + miniFill + "' stroke='" + miniStroke + "' stroke-width='" + miniStrokeW + "' opacity='0.82'><title>" + esc(rr.model_id + " | eval_id=" + String(pj.eval_id || "") + " | eval " + String(j + 1) + "/" + String(miniCount) + " | final_eval_elo=" + Number(pj.y || 0).toFixed(2)) + "</title></rect>";
            }
          }
        }
        return "<div class='muted' style='margin:8px 0 6px 0;'>Final ELO by model (ranked). Main bar = final ELO; mini bars at right = final ELO per eval_id (colored by eval_id).</div>" +
          "<svg class='chart-svg' viewBox='0 0 " + width + " " + bottomHeight + "' preserveAspectRatio='none'>" +
          "<rect x='0' y='0' width='" + width + "' height='" + bottomHeight + "' fill='#0b1220' />" +
          grid +
          "<line x1='" + padL + "' y1='" + (bottomHeight - padB) + "' x2='" + (width - padR) + "' y2='" + (bottomHeight - padB) + "' stroke='#334155' stroke-width='1.2' />" +
          "<line x1='" + padL + "' y1='" + padT + "' x2='" + padL + "' y2='" + (bottomHeight - padB) + "' stroke='#334155' stroke-width='1.2' />" +
          bars +
          "<text x='" + (width / 2).toFixed(2) + "' y='" + (bottomHeight - 6) + "' fill='#94a3b8' font-size='11' text-anchor='middle'>model rank by final ELO (1..N)</text>" +
          "</svg>";
      }

      const legend = finalRows.slice(0, 12).map(function (r, idx) {
        const mark = String(r.model_id) === String(chosenModel) ? "●" : "•";
        return mark + " #" + String(idx + 1) + " " + String(r.model_id) + " (" + Number(r.final_elo || 0).toFixed(1) + ")";
      }).join(" | ");
      host.innerHTML = "<div style='display:flex;flex-direction:column;gap:10px;'>" +
        "<div class='muted'>" + esc(eloCalcNote) + "</div>" +
        "<div class='panel' style='padding:8px;'>" + renderTopLine() + "</div>" +
        "<div class='panel' style='padding:8px;'>" + renderBottomBars() + "<div class='muted' style='margin-top:6px;'>" + esc(legend) + "</div></div>" +
      "</div>";
    }
    function switchTab(nextTab) {
      activeTab = (nextTab === "chart") ? "chart" : "summary";
      const summaryBtn = el("tabSummaryBtn");
      const chartBtn = el("tabChartBtn");
      const summaryPane = el("tabSummary");
      const chartPane = el("tabChart");
      if (summaryBtn) summaryBtn.classList.toggle("active", activeTab === "summary");
      if (chartBtn) chartBtn.classList.toggle("active", activeTab === "chart");
      if (summaryPane) summaryPane.classList.toggle("active", activeTab === "summary");
      if (chartPane) chartPane.classList.toggle("active", activeTab === "chart");
      if (activeTab === "chart") {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            render();
          });
        });
      }
    }
    function render() {
      const rows = buildRows();
      renderSummary(rows);
      renderEloChart(rows);
    }
    async function loadCatalog() {
      const r = await fetch("/api/v2/catalog");
      catalog = await r.json();
      el("meta").textContent = "schema=" + String((catalog && catalog.schema_version) || "?") + " generated=" + String((catalog && catalog.generated_at_utc) || "?");
      renderSelectors();
      await loadEloUniverse();
      renderSelectors();
      render();
    }
    async function refreshAndRender() {
      await loadEloUniverse();
      renderSelectors();
      render();
    }

    el("engineSelect").onchange = function () {
      selectedEngine = String(el("engineSelect").value || "");
      selectedModel = "__all__";
      selectedModels = [];
      selectedModelsInitialized = false;
      refreshAndRender().catch(() => {});
    };
    el("modelSelect").onchange = function () {
      selectedModel = String(el("modelSelect").value || "__all__");
      if (selectedModel && selectedModel !== "__all__") selectedModels = [selectedModel];
      renderSelectors();
      render();
    };
    el("modelMultiSelect").onchange = function () {
      const node = el("modelMultiSelect");
      if (!node) return;
      selectedModels = Array.from(node.selectedOptions || []).map(opt => String(opt.value || "")).filter(Boolean);
      if (selectedModels.length === 1) selectedModel = selectedModels[0];
      else if (selectedModels.length > 1) selectedModel = "__all__";
      render();
    };
    el("modelMultiAllBtn").onclick = function () {
      const node = el("modelMultiSelect");
      if (!node) return;
      for (const opt of Array.from(node.options || [])) opt.selected = true;
      selectedModels = Array.from(node.options || []).map(opt => String(opt.value || "")).filter(Boolean);
      selectedModel = "__all__";
      render();
    };
    el("modelMultiNoneBtn").onclick = function () {
      const node = el("modelMultiSelect");
      if (!node) return;
      for (const opt of Array.from(node.options || [])) opt.selected = false;
      selectedModels = [];
      selectedModel = "__all__";
      render();
    };
    el("sideSelect").onchange = function () { selectedSide = String(el("sideSelect").value || "__all__"); render(); };
    el("controllerSelect").onchange = function () { selectedController = String(el("controllerSelect").value || "__all__"); render(); };
    el("scenarioFilter").onchange = function () { scenarioFilter = String(el("scenarioFilter").value || "__all__"); render(); };
    el("profileFilter").onchange = function () { profileFilter = String(el("profileFilter").value || "__all__"); render(); };
    el("curriculumPhaseFilter").onchange = function () { curriculumPhaseFilter = String(el("curriculumPhaseFilter").value || "__all__"); render(); };
    el("chartGranularitySelect").onchange = function () { chartGranularity = String(el("chartGranularitySelect").value || "eval"); render(); };
    el("eloScoringSelect").onchange = function () { eloScoringMode = String(el("eloScoringSelect").value || "classic"); render(); };
    el("secondaryMetricSelect").onchange = function () { secondaryMetric = String(el("secondaryMetricSelect").value || "tracked_captured_avg"); render(); };
    el("createdAtFilter").oninput = function () { createdAtFilter = String(el("createdAtFilter").value || ""); render(); };
    el("evalIdFilter").oninput = function () { evalIdFilter = String(el("evalIdFilter").value || ""); render(); };
    el("tabSummaryBtn").onclick = function () { switchTab("summary"); };
    el("tabChartBtn").onclick = function () { switchTab("chart"); };
    el("reloadBtn").onclick = function () { loadCatalog().catch(() => {}); };
    el("openModelBtn").onclick = function () {
      if (!selectedEngine || !selectedModel || selectedModel === "__all__") return;
      window.open("/model?engine=" + encodeURIComponent(selectedEngine) + "&model=" + encodeURIComponent(selectedModel), "_blank", "noopener,noreferrer");
    };
    window.addEventListener("resize", function () { render(); });
    loadCatalog().catch((e) => {
      const host = el("tabSummary");
      if (host) host.innerHTML = "<div class='muted'>Load failed: " + esc(String((e && e.message) || e || "unknown")) + "</div>";
    });
  </script>
</body>
</html>
"""
