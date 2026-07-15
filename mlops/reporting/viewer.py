from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


def _read_catalog(path: Path) -> dict:
    if not path.exists():
        return {
            "schema_version": "reporting_v2",
            "engines": [],
            "error": f"catalog not found: {path}",
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema_version": "reporting_v2",
            "engines": [],
            "error": f"failed to parse catalog: {exc}",
        }


def _resolve_replay_path(eval_source_path: str, explicit_replay_path: str = "") -> Path | None:
    replay_raw = str(explicit_replay_path or "").strip()
    if replay_raw:
        p = Path(replay_raw).expanduser().resolve()
        return p if p.exists() else None
    src_raw = str(eval_source_path or "").strip()
    if not src_raw:
        return None
    src = Path(src_raw).expanduser().resolve()
    if not src.exists():
        return None
    parent = src.parent
    name = src.name
    candidates: list[Path] = []
    if name.startswith("bench_eval_"):
        candidates.append(parent / name.replace("bench_eval_", "bench_replay_", 1))
    candidates.append(parent / "bench_replay_latest.json")
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def _load_scenario_overlay(repo_root: Path, scenario_id: str) -> dict:
    sid = str(scenario_id or "").strip()
    if not sid:
        return {}
    scenarios_dir = (repo_root / "assault_sim" / "assets" / "scenarios").resolve()
    if not scenarios_dir.exists():
        return {}
    catalogs_dir = (repo_root / "assault_sim" / "assets" / "catalogs").resolve()
    map_piece_catalog_path = catalogs_dir / "map_piece_catalog.json"
    map_piece_catalog: dict = {}
    if map_piece_catalog_path.exists():
        try:
            map_piece_catalog = json.loads(map_piece_catalog_path.read_text(encoding="utf-8"))
        except Exception:
            map_piece_catalog = {}

    def _rot_quarters(deg: int) -> int:
        if deg % 90 != 0:
            return 0
        return (deg // 90) % 4

    def _rotate_local(q: int, r: int, width: int, height: int, qturns: int) -> tuple[int, int]:
        if qturns == 0:
            return q, r
        if qturns == 1:
            return (height - 1 - r), q
        if qturns == 2:
            return (width - 1 - q), (height - 1 - r)
        return r, (width - 1 - q)

    def _build_map_cells(raw_scenario: dict) -> list[dict]:
        pieces = list((raw_scenario.get("map", {}) or {}).get("pieces", []) or [])
        cat_pieces = dict((map_piece_catalog.get("pieces", {}) or {}))
        cells: set[tuple[int, int]] = set()
        for entry in pieces:
            if not isinstance(entry, dict):
                continue
            piece_id = str(entry.get("id", "") or "")
            piece = dict(cat_pieces.get(piece_id, {}) or {})
            shape = list(piece.get("shape", []) or [])
            if len(shape) < 2:
                continue
            width = int(shape[0] or 0)
            height = int(shape[1] or 0)
            if width <= 0 or height <= 0:
                continue
            origin = list(entry.get("origin", []) or [])
            if len(origin) < 2:
                continue
            oq = int(origin[0] or 0)
            orr = int(origin[1] or 0)
            qturns = _rot_quarters(int(entry.get("rotation", 0) or 0))
            for lq in range(width):
                for lr in range(height):
                    rq, rr = _rotate_local(lq, lr, width, height, qturns)
                    cells.add((int(rq + oq), int(rr + orr)))
        return [{"q": int(q), "r": int(r)} for q, r in sorted(cells, key=lambda x: (x[1], x[0]))]

    candidates = [scenarios_dir / f"{sid}.json"]
    for c in candidates:
        if c.exists():
            try:
                raw = json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            vp = dict(raw.get("vp", {}) or {})
            hexes = list(vp.get("hexes", []) or [])
            shape = list(raw.get("shape", []) or [])
            map_cells = _build_map_cells(raw)
            return {
                "path": str(c),
                "shape": shape if len(shape) >= 2 else [],
                "map_cells": map_cells,
                "vp_hexes": [
                    {
                        "q": int(h.get("q", 0) or 0),
                        "r": int(h.get("r", 0) or 0),
                        "initial_owner": str(h.get("initial_owner", "") or ""),
                        "value": float(h.get("value", vp.get("value_per_hex", 1)) or 1),
                    }
                    for h in hexes
                    if isinstance(h, dict)
                ],
            }
    # Fallback: scan scenario files by internal id.
    for p in list(scenarios_dir.glob("*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        internal_id = str(raw.get("id", "") or "").strip()
        if internal_id != sid:
            continue
        vp = dict(raw.get("vp", {}) or {})
        hexes = list(vp.get("hexes", []) or [])
        shape = list(raw.get("shape", []) or [])
        map_cells = _build_map_cells(raw)
        return {
            "path": str(p),
            "shape": shape if len(shape) >= 2 else [],
            "map_cells": map_cells,
            "vp_hexes": [
                {
                    "q": int(h.get("q", 0) or 0),
                    "r": int(h.get("r", 0) or 0),
                    "initial_owner": str(h.get("initial_owner", "") or ""),
                    "value": float(h.get("value", vp.get("value_per_hex", 1)) or 1),
                }
                for h in hexes
                if isinstance(h, dict)
            ],
        }
    return {}


def _index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Curriculum Reporting Viewer</title>
  <style>
    html, body { height: 100%; }
    body { font-family: Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    .wrap { box-sizing: border-box; padding: 12px; width: 100vw; height: 100vh; display: flex; flex-direction: column; }
    h1 { margin: 0 0 12px 0; font-size: 20px; }
    .bar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
    button { background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; cursor: pointer; }
    button:hover { background: #475569; }
    .grid { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(220px, 22vw) minmax(260px, 28vw) minmax(0, 1fr); gap: 10px; }
    .panel { border: 1px solid #334155; border-radius: 8px; background: #111827; min-height: 0; display: flex; flex-direction: column; }
    .panel h2 { margin: 0; padding: 10px; font-size: 14px; border-bottom: 1px solid #334155; }
    .list { padding: 8px; display: flex; flex-direction: column; gap: 6px; overflow: auto; min-height: 0; }
    .item { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; cursor: pointer; }
    .item.active { border-color: #22d3ee; }
    .muted { color: #94a3b8; font-size: 12px; }
    .tabs { display: flex; gap: 6px; margin: 8px; }
    .tab { padding: 6px 10px; border: 1px solid #334155; border-radius: 6px; cursor: pointer; }
    .tab.active { background: #0ea5e9; color: #0f172a; border-color: #0ea5e9; font-weight: 700; }
    .content { padding: 8px; overflow: auto; min-height: 0; flex: 1; }
    table { border-collapse: collapse; width: 100%; font-size: 12px; }
    th, td { border: 1px solid #334155; padding: 6px; text-align: left; vertical-align: top; }
    th { background: #1f2937; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Curriculum Reporting Viewer (Base UI)</h1>
    <div class="bar">
      <button id="reloadBtn">Reload</button>
      <label class="muted" style="display:flex;align-items:center;gap:6px;">
        <input id="autoRefresh" type="checkbox" checked />
        auto-refresh
      </label>
      <label class="muted" style="display:flex;align-items:center;gap:6px;">
        interval
        <input id="refreshSec" type="number" min="2" max="120" value="5" style="width:64px;background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:4px;padding:2px 4px;" />
        s
      </label>
      <span id="meta" class="muted">loading...</span>
    </div>
    <div class="grid">
      <section class="panel">
        <h2>Engines</h2>
        <div id="engines" class="list"></div>
      </section>
      <section class="panel">
        <h2>Models</h2>
        <div id="models" class="list"></div>
      </section>
      <section class="panel">
        <h2>Model Detail + History</h2>
        <div id="modelDetail" class="content" style="flex:0 0 auto; max-height: 38%; border-bottom:1px solid #334155;"></div>
        <div class="tabs">
          <div id="trainTab" class="tab active">Train History</div>
          <div id="evalTab" class="tab">Eval History</div>
        </div>
        <div id="history" class="content"></div>
      </section>
    </div>
  </div>
  <script>
    let catalog = null;
    let selectedEngine = "";
    let selectedModel = "";
    let activeTab = "train";
    let refreshTimer = null;
    let lastCatalogDigest = "";
    let selectedTrainIdx = 0;

    const el = (id) => document.getElementById(id);
    const escapeHtml = (v) => String((v === undefined || v === null) ? "" : v).replace(/[&<>"']/g, c => ({
      "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
    }[c]));

    async function loadCatalog() {
      const r = await fetch("/api/catalog");
      catalog = await r.json();
      const digest = JSON.stringify(catalog);
      const changed = digest !== lastCatalogDigest;
      lastCatalogDigest = digest;
      el("meta").textContent = `schema=${catalog.schema_version || "?"} generated=${catalog.generated_at_utc || "?"}`;
      if (changed) {
        renderEngines();
      }
    }

    function setAutoRefresh() {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      const enabled = !!el("autoRefresh").checked;
      const sec = Math.max(2, Math.min(120, Number(el("refreshSec").value || 5)));
      el("refreshSec").value = String(sec);
      if (!enabled) return;
      refreshTimer = setInterval(() => {
        loadCatalog().catch(() => {});
      }, sec * 1000);
    }

    function renderEngines() {
      const box = el("engines");
      const engines = catalog.engines || [];
      if (!selectedEngine && engines.length) {
        const preferred = engines.find(e => String((e && e.engine) || "") === "efficientzero_v2");
        selectedEngine = (preferred && preferred.engine) ? preferred.engine : (engines[0].engine || "");
      }
      box.innerHTML = engines.map(e => {
        const active = selectedEngine === e.engine ? "active" : "";
        const count = (e.models || []).length;
        return `<div class="item ${active}" data-engine="${escapeHtml(e.engine)}">
          <div><b>${escapeHtml(e.engine)}</b></div>
          <div class="muted">${count} models</div>
        </div>`;
      }).join("");
      [...box.querySelectorAll(".item")].forEach(n => n.onclick = () => {
        selectedEngine = n.dataset.engine || "";
        selectedModel = "";
        selectedTrainIdx = 0;
        renderEngines();
        renderModels();
      });
      renderModels();
    }

    function currentEngine() {
      return (catalog.engines || []).find(e => e.engine === selectedEngine) || { models: [] };
    }

    function modelLatestTimestampMs(model) {
      const trains = Array.isArray(model && model.train_history) ? model.train_history : [];
      const evals = Array.isArray(model && model.eval_history) ? model.eval_history : [];
      const timestamps = [];
      for (const r of trains) {
        const t = Date.parse(String((r && r.created_at_utc) || ""));
        if (Number.isFinite(t)) timestamps.push(t);
      }
      for (const r of evals) {
        const t = Date.parse(String((r && r.created_at_utc) || ""));
        if (Number.isFinite(t)) timestamps.push(t);
      }
      if (!timestamps.length) return 0;
      return Math.max(...timestamps);
    }

    function renderModels() {
      const box = el("models");
      const models = currentEngine().models || [];
      const sortedModels = [...models].sort((a, b) => {
        const ta = modelLatestTimestampMs(a);
        const tb = modelLatestTimestampMs(b);
        if (tb !== ta) return tb - ta; // newest first
        return String((a && a.model_id) || "").localeCompare(String((b && b.model_id) || ""));
      });
      if (!selectedModel && sortedModels.length) selectedModel = sortedModels[0].model_id || "";
      box.innerHTML = sortedModels.map(m => {
        const active = selectedModel === m.model_id ? "active" : "";
        return `<div class="item ${active}" data-model="${escapeHtml(m.model_id)}">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
            <div><b>${escapeHtml(m.model_id)}</b></div>
            <button data-open-model="${escapeHtml(m.model_id)}" style="padding:4px 8px;font-size:11px;">Open</button>
          </div>
          <div class="muted">train=${(m.train_history || []).length} eval=${(m.eval_history || []).length}</div>
        </div>`;
      }).join("");
      [...box.querySelectorAll(".item")].forEach(n => n.onclick = () => {
        selectedModel = n.dataset.model || "";
        selectedTrainIdx = 0;
        renderModels();
        renderHistory();
      });
      [...box.querySelectorAll("button[data-open-model]")].forEach(btn => {
        btn.onclick = (ev) => {
          ev.stopPropagation();
          const modelId = btn.getAttribute("data-open-model") || "";
          const url = `/model?engine=${encodeURIComponent(selectedEngine)}&model=${encodeURIComponent(modelId)}`;
          window.open(url, "_blank", "noopener,noreferrer");
        };
      });
      renderHistory();
    }

    function currentModel() {
      const models = currentEngine().models || [];
      return models.find(m => m.model_id === selectedModel) || { train_history: [], eval_history: [] };
    }

    function renderModelDetail() {
      const m = currentModel();
      const root = el("modelDetail");
      const trains = m.train_history || [];
      const evals = m.eval_history || [];
      const scenarios = m.scenarios_seen || [];
      const scenarioTrainCounts = m.scenario_train_counts || {};
      const scenarioEvalCounts = m.scenario_eval_counts || {};
      const latest = trains.length ? trains[0] : null;
      const retrainCount = trains.filter(t => !!t.is_retrain).length;
      const latestCfg = latest && latest.config ? latest.config : {};
      root.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:8px;">
          <div class="item"><div class="muted">model_id</div><div><b>${escapeHtml(m.model_id || "")}</b></div></div>
          <div class="item"><div class="muted">engine</div><div><b>${escapeHtml(m.engine || "")}</b></div></div>
          <div class="item"><div class="muted">algorithm</div><div><b>${escapeHtml(m.algorithm || "")}</b></div></div>
          <div class="item"><div class="muted">config_fingerprint</div><div>${escapeHtml(m.config_fingerprint || "")}</div></div>
          <div class="item"><div class="muted">train_count</div><div><b>${trains.length}</b></div></div>
          <div class="item"><div class="muted">eval_count</div><div><b>${evals.length}</b></div></div>
          <div class="item"><div class="muted">retrain_count</div><div><b>${retrainCount}</b></div></div>
          <div class="item"><div class="muted">latest_run_id</div><div>${escapeHtml((latest && latest.run_id) || "")}</div></div>
          <div class="item"><div class="muted">latest_commit</div><div>${escapeHtml((latest && latest.git_commit) || "")}</div></div>
        </div>
        <h3 style="margin:0 0 8px 0;font-size:13px;">Scenarios (multi-scenario ready)</h3>
        ${scenarios.length ? `
          <table style="margin-bottom:8px;">
            <thead><tr><th>scenario_id</th><th>train_count</th><th>eval_count</th></tr></thead>
            <tbody>
              ${scenarios.map(s => `<tr>
                <td>${escapeHtml(s)}</td>
                <td>${escapeHtml(scenarioTrainCounts[s] || 0)}</td>
                <td>${escapeHtml(scenarioEvalCounts[s] || 0)}</td>
              </tr>`).join("")}
            </tbody>
          </table>
        ` : `<div class="muted" style="margin-bottom:8px;">No scenarios registered yet.</div>`}
        <details>
          <summary style="cursor:pointer;">Latest Train Config</summary>
          <pre style="white-space:pre-wrap;word-break:break-word;background:#0b1220;border:1px solid #334155;border-radius:6px;padding:8px;margin-top:8px;">${escapeHtml(JSON.stringify(latestCfg, null, 2))}</pre>
        </details>
      `;
    }

    function trainTable(rows) {
      return `<table>
        <thead><tr><th>run_id</th><th>created_at</th><th>scenario</th><th>retrain</th><th>parent_run</th><th>commit</th><th>checkpoint</th></tr></thead>
        <tbody>
          ${rows.map((r, idx) => `<tr data-train-idx="${idx}" style="${idx===selectedTrainIdx ? "background:#0b2536;" : ""}">
            <td><b>${escapeHtml(r.run_id)}</b></td>
            <td>${escapeHtml(r.created_at_utc)}</td>
            <td>${escapeHtml(r.scenario_id)}</td>
            <td>${r.is_retrain ? "yes" : "no"}</td>
            <td>${escapeHtml(r.parent_run_id || "")}</td>
            <td>${escapeHtml(r.git_commit || "")}</td>
            <td class="muted">${escapeHtml(r.latest_checkpoint || "")}</td>
          </tr>`).join("")}
        </tbody>
      </table>`;
    }

    function evalTable(rows) {
      return `<table>
        <thead><tr><th>eval_id</th><th>train_run_id</th><th>created_at</th><th>scenario</th><th>gate_status</th><th>commit</th></tr></thead>
        <tbody>
          ${rows.map(r => `<tr>
            <td>${escapeHtml(r.eval_id)}</td>
            <td>${escapeHtml(r.train_run_id)}</td>
            <td>${escapeHtml(r.created_at_utc)}</td>
            <td>${escapeHtml(r.scenario_id)}</td>
            <td>${escapeHtml((r.phase_2_9_promotion_gate || {}).status || "")}</td>
            <td>${escapeHtml(r.git_commit || "")}</td>
          </tr>`).join("")}
        </tbody>
      </table>`;
    }

    function renderHistory() {
      const m = currentModel();
      renderModelDetail();
      const root = el("history");
      if (activeTab === "train") {
        const trainRows = m.train_history || [];
        if (selectedTrainIdx >= trainRows.length) selectedTrainIdx = Math.max(0, trainRows.length - 1);
        const selected = trainRows[selectedTrainIdx] || null;
        root.innerHTML = `
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
            <button id="prevTrainBtn" ${selectedTrainIdx <= 0 ? "disabled" : ""}>Prev train</button>
            <button id="nextTrainBtn" ${selectedTrainIdx >= Math.max(0, trainRows.length-1) ? "disabled" : ""}>Next train</button>
            <span class="muted">${trainRows.length ? `train ${selectedTrainIdx + 1}/${trainRows.length}` : "no trains"}</span>
          </div>
          ${trainTable(trainRows)}
          <div style="height:10px;"></div>
          <h3 style="margin:0 0 8px 0;font-size:13px;">Selected Train Detail</h3>
          ${selected ? `
            <div class="muted" style="margin-bottom:8px;">run_id=${escapeHtml(selected.run_id)} scenario=${escapeHtml(selected.scenario_id)} commit=${escapeHtml(selected.git_commit || "")}</div>
            <div class="muted">Engine-specific train detail only (no cross-engine mix).</div>
          ` : `<div class="muted">No train rows available.</div>`}
        `;
        const prevBtn = document.getElementById("prevTrainBtn");
        if (prevBtn) prevBtn.onclick = () => { selectedTrainIdx = Math.max(0, selectedTrainIdx - 1); renderHistory(); };
        const nextBtn = document.getElementById("nextTrainBtn");
        if (nextBtn) nextBtn.onclick = () => { selectedTrainIdx = Math.min(Math.max(0, trainRows.length - 1), selectedTrainIdx + 1); renderHistory(); };
        [...root.querySelectorAll("tr[data-train-idx]")].forEach(row => row.onclick = () => {
          selectedTrainIdx = Number(row.getAttribute("data-train-idx") || 0);
          renderHistory();
        });
      } else {
        root.innerHTML = evalTable(m.eval_history || []);
      }
    }

    el("reloadBtn").onclick = loadCatalog;
    el("autoRefresh").onchange = setAutoRefresh;
    el("refreshSec").onchange = setAutoRefresh;
    el("trainTab").onclick = () => { activeTab = "train"; el("trainTab").classList.add("active"); el("evalTab").classList.remove("active"); renderHistory(); };
    el("evalTab").onclick = () => { activeTab = "eval"; el("evalTab").classList.add("active"); el("trainTab").classList.remove("active"); renderHistory(); };
    loadCatalog();
    setAutoRefresh();
  </script>
</body>
</html>
"""


def _model_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Model Detail Viewer</title>
  <style>
    html, body { height: 100%; }
    body { font-family: Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    .wrap { box-sizing: border-box; padding: 12px; width: 100vw; height: 100vh; display: flex; flex-direction: column; gap: 10px; }
    .panel { border: 1px solid #334155; border-radius: 8px; background: #111827; padding: 10px; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
    .kpi { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; }
    .muted { color: #94a3b8; font-size: 12px; }
    .main { flex: 1; min-height: 0; display: grid; grid-template-columns: 320px minmax(0,1fr); gap: 10px; }
    .main.train-collapsed { grid-template-columns: 44px minmax(0,1fr); }
    .collapsed-body { display: none; }
    .main.train-collapsed .collapsed-body { display: none !important; }
    .main.train-collapsed #trainPanelTitle { display: none; }
    .main.train-collapsed #trainList { display: none; }
    .main.train-collapsed #collapseTrainBtn { width: 100%; padding: 10px 0; }
    .list { overflow: auto; min-height: 0; display: flex; flex-direction: column; gap: 6px; }
    .item { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; cursor: pointer; }
    .item.active { border-color: #22d3ee; }
    .tabs { display:flex; gap:8px; margin-top:10px; }
    .tab-btn { cursor:pointer; background:#1e293b; border:1px solid #475569; color:#e2e8f0; border-radius:6px; padding:6px 10px; }
    .tab-btn.active { background:#0ea5e9; color:#0f172a; border-color:#0ea5e9; font-weight:700; }
    .tab-pane { display:none; min-height:0; }
    .tab-pane.active { display:flex; flex-direction:column; min-height:0; }
    .analysis-toolbar { display:flex; align-items:flex-start; gap:10px; flex-wrap:wrap; margin-bottom:6px; }
    .tab-group { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
    .tab-level-label {
      font-size:11px; color:#93c5fd; border:1px solid #334155; background:#0b1220; border-radius:999px; padding:2px 8px;
      text-transform:uppercase; letter-spacing:.04em;
    }
    .toolbar-sep { width:1px; align-self:stretch; background:#334155; opacity:.9; min-height:30px; }
    .toolbar-filters { margin-left:auto; min-width:280px; flex:1 1 320px; }
    .replay-top { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px; }
    .replay-input, .replay-select {
      background:#1f2532; color:#e2e8f0; border:1px solid #334155; border-radius:8px; padding:6px 8px;
    }
    .replay-panel {
      margin-top:8px; background:#0f172a; border:1px solid #334155; border-radius:8px; padding:10px;
    }
    .replay-panel h3 { margin:0 0 8px 0; font-size:13px; }
    .replay-kv { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:8px; }
    .replay-kv .kpi { background:#111827; }
    .replay-canvas { width:100%; max-width:100%; height:auto; max-height:560px; aspect-ratio:16/9; background:#0b0f18; border:1px solid #334155; border-radius:8px; display:block; }
    .replay-grid { display:grid; grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.8fr) minmax(280px, 0.75fr); gap:10px; }
    @media (max-width: 1400px) { .replay-grid { grid-template-columns: minmax(0, 1fr); } }
    .replay-log {
      white-space: pre-wrap;
      word-break: break-word;
      background:#0b1220;
      border:1px solid #334155;
      border-radius:6px;
      padding:8px;
      font-size:12px;
      line-height:1.35;
      overflow:auto;
      max-height:520px;
      min-height:280px;
    }
    .dash-wrap { margin-top:10px; display:grid; grid-template-columns: 1fr; gap:10px; }
    .dash-section { border:1px solid #334155; border-radius:8px; background:#0b1220; padding:10px; }
    .dash-title { margin:0 0 8px 0; font-size:13px; color:#cbd5e1; }
    .dash-cards { display:grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap:8px; }
    .dash-card { border:1px solid #334155; border-radius:8px; background:#0f172a; padding:8px; }
    .dash-k { font-size:11px; color:#94a3b8; margin-bottom:4px; }
    .dash-v { font-size:12px; color:#e2e8f0; font-weight:700; word-break:break-word; }
    @media (max-width: 1600px) { .dash-cards { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    @media (max-width: 1100px) { .dash-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    .objective-reward-grid {
      display:grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap:10px;
      grid-auto-flow:dense;
      align-items:start;
      min-width:0;
    }
    .objective-reward-section {
      background:#0f172a;
      border:1px solid #334155;
      border-radius:8px;
      padding:8px;
      min-width:0;
    }
    .objective-reward-section--wide {
      grid-column: 1 / -1;
    }
    .objective-reward-section h3 {
      margin:0 0 8px 0;
      font-size:13px;
    }
    .objective-reward-table-wrap {
      width:100%;
      min-width:0;
      overflow-x:auto;
    }
    .objective-reward-table {
      border-collapse:collapse;
      width:100%;
      min-width:420px;
      font-size:12px;
    }
    @media (max-width: 1100px) {
      .objective-reward-grid { grid-template-columns: minmax(0, 1fr); }
      .objective-reward-section--wide { grid-column:auto; }
    }
    h1 { margin: 0; font-size: 18px; }
    h2 { margin: 0 0 8px 0; font-size: 14px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0b1220; border: 1px solid #334155; border-radius: 6px; padding: 8px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1 id="title">Model Detail</h1>
      <div id="modelMeta" class="grid" style="margin-top:8px;"></div>
      <div id="scenarioFilterHost"></div>
      <details style="margin-top:8px;">
        <summary style="cursor:pointer;">Latest Train Config</summary>
        <pre id="latestConfig">{}</pre>
      </details>
    </div>
    <div class="main">
      <section class="panel" id="trainPanel" style="display:flex;flex-direction:column;min-height:0;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <h2 id="trainPanelTitle">Train History</h2>
          <button id="collapseTrainBtn" style="padding:4px 8px;font-size:12px;">⟨</button>
        </div>
        <div id="trainList" class="list"></div>
      </section>
      <section class="panel" style="display:flex;flex-direction:column;min-height:0;">
        <h2>Train Analysis</h2>
        <div class="analysis-toolbar">
          <div class="tab-group">
            <span class="tab-level-label">Nivel 1</span>
            <div class="tabs" style="margin:0;">
              <button id="sectionTrainBtn" class="tab-btn">Train Metrics</button>
              <button id="sectionEvalBtn" class="tab-btn active">Eval Metrics</button>
              <button id="sectionMetaBtn" class="tab-btn">Meta</button>
            </div>
          </div>
          <div class="toolbar-sep"></div>
          <div class="tab-group">
            <span class="tab-level-label">Nivel 2</span>
            <div class="tabs" style="margin:0;">
              <button id="tabTrainDetailBtn" class="tab-btn" data-section="train">Train Detail</button>
              <button id="tabTrainHeadDiagnosticsBtn" class="tab-btn" data-section="train">Train Head Diagnostics</button>
              <button id="tabObjectiveRewardConfigBtn" class="tab-btn" data-section="train">Objective/Reward Config</button>
              <button id="tabMuzeroVpsBtn" class="tab-btn active" data-section="eval">VP Summary</button>
              <button id="tabHeadDiagnosticsBtn" class="tab-btn" data-section="eval">Eval Head Diagnostics</button>
              <button id="tabUnifiedBtn" class="tab-btn" data-section="eval">Unified Actions + Attack Effectiveness</button>
              <button id="tabEvalDecisionsBtn" class="tab-btn" data-section="eval">Eval KBI Decisions</button>
              <button id="tabReplayBtn" class="tab-btn" data-section="eval">Match Replay</button>
              <button id="tabOverviewBtn" class="tab-btn" data-section="meta">Overview</button>
            </div>
          </div>
          <div class="toolbar-sep"></div>
          <div id="analysisFiltersHost" class="toolbar-filters"></div>
        </div>
        <div id="tabTrainDetail" class="tab-pane">
          <h2 style="margin-top:8px;">Selected Train Metrics</h2>
          <div id="trainDashboard" class="dash-wrap" style="margin-bottom:8px;"></div>
          <div id="trainArchitectureHost" style="margin-bottom:8px;"></div>
          <pre id="trainMetricsPre">{}</pre>
        </div>
        <div id="tabTrainHeadDiagnostics" class="tab-pane">
          <h2 style="margin-top:8px;">Train Head Diagnostics</h2>
          <div id="trainHeadDiagnosticsRoot" class="list"></div>
        </div>
        <div id="tabObjectiveRewardConfig" class="tab-pane">
          <h2 style="margin-top:8px;">Objective/Reward Config</h2>
          <div id="objectiveRewardConfigRoot" class="list"></div>
        </div>
        <div id="tabOverview" class="tab-pane">
          <h2 style="margin-top:8px;">Evals for Selected Train</h2>
          <div id="evalList" class="list"></div>
        </div>
        <div id="tabMuzeroVps" class="tab-pane active">
          <h2 style="margin-top:8px;">VP Summary</h2>
          <div id="muzeroVpsRoot" class="list"></div>
        </div>
        <div id="tabHeadDiagnostics" class="tab-pane">
          <h2 style="margin-top:8px;">Eval Head Diagnostics</h2>
          <div id="headDiagnosticsRoot" class="list"></div>
        </div>
        <div id="tabUnified" class="tab-pane">
          <h2 style="margin-top:8px;">Unified Actions + Attack Effectiveness</h2>
          <div id="unifiedRoot" class="list"></div>
        </div>
        <div id="tabEvalDecisions" class="tab-pane">
          <h2 style="margin-top:8px;">Eval KBI Decisions</h2>
          <div id="evalDecisionsRoot" class="list"></div>
        </div>
        <div id="tabReplay" class="tab-pane">
          <h2 style="margin-top:8px;">Match Replay</h2>
          <div id="replayRoot" class="list"></div>
        </div>
      </section>
    </div>
  </div>
  <script>
    window.__VIEWER_BUILD__ = "viewer-fix-2026-07-06-turn-closed-label";
    function el(id) { return document.getElementById(id); }
    function esc(v) {
      return String((v === undefined || v === null) ? "" : v).replace(/[&<>"']/g, function (c) {
        return ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" })[c];
      });
    }
    const q = new URLSearchParams(window.location.search);
    const engine = q.get("engine") || "";
    const modelId = q.get("model") || "";
    let model = null;
    let selectedTrainRun = "";
    let selectedScenario = "__all__";
    let activeTab = "vps";
    let activeSection = "eval";
    let selectedTrainSummary = null;
    const trainSummaryCache = {};
    let trainCollapsed = false;
    const objectiveRewardDefaults = {
      objective_loss_weight: 0.12,
      objective_target_mode: "progress",
      objective_pos_weight: 5.0,
      objective_opportunity_max_dist: 2.0,
      objective_progress_positive_threshold: 0.0,
      objective_opportunity_near_vp_max_dist: 2.0,
      assault_advantage_prob_threshold: 0.55,
      assault_advantage_margin_threshold: 0.20,
      assault_advantage_legal_count_threshold: 6,
      assault_advantage_cover_max: 0.35,
      assault_advantage_min_score: 2,
      high_confidence_prob_threshold: 0.60,
      high_confidence_margin_threshold: 0.25,
      near_vp_max_dist: 2.0,
      strong_progress_delta_threshold: 2.0,
      conversion_window_steps_after_progress: 2,
      decision_flip_legal_count_tolerance: 2,
    };

    async function loadModel() {
      const r = await fetch("/api/model?engine=" + encodeURIComponent(engine) + "&model=" + encodeURIComponent(modelId));
      model = await r.json();
      renderModel();
      renderTrains();
    }

    function renderModel() {
      el("title").textContent = "Model Detail - " + String((model && model.model_id) || modelId || "");
      const trains = model.train_history || [];
      const evals = model.eval_history || [];
      const retrains = trains.filter(function (t) { return !!t.is_retrain; }).length;
      const latest = trains.length ? trains[0] : null;
      const scenarios = model.scenarios_seen || [];
      if (selectedScenario !== "__all__" && !scenarios.includes(selectedScenario)) selectedScenario = "__all__";
      el("modelMeta").innerHTML = [
        ["engine", model.engine || engine],
        ["algorithm", model.algorithm || ""],
        ["fingerprint", model.config_fingerprint || ""],
        ["train_count", trains.length],
        ["eval_count", evals.length],
        ["retrain_count", retrains],
        ["latest_run", latest ? latest.run_id : ""],
        ["latest_commit", latest ? (latest.git_commit || "") : ""],
      ].map(function (pair) { return "<div class='kpi'><div class='muted'>" + esc(pair[0]) + "</div><div><b>" + esc(pair[1]) + "</b></div></div>"; }).join("");
      el("latestConfig").textContent = JSON.stringify((latest && latest.config) || {}, null, 2);
      renderTrainDashboard(trains, evals);
      const options = (scenarios || []).map(function (s) { return "<option value='" + esc(s) + "' " + (selectedScenario===s ? "selected" : "") + ">" + esc(s) + "</option>"; }).join("");
      const scenarioFilterHtml =
        "<div class='panel' style='margin-top:8px;'>" +
          "<div class='muted'>Scenario filter</div>" +
          "<select id='scenarioFilter' style='margin-top:6px;background:#1e293b;color:#e2e8f0;border:1px solid #475569;border-radius:4px;padding:4px 6px;'>" +
            "<option value='__all__'>all scenarios</option>" +
            options +
          "</select>" +
        "</div>";
      const filterHost = el("scenarioFilterHost");
      filterHost.innerHTML = scenarioFilterHtml;
      const sf = document.getElementById("scenarioFilter");
      if (sf) sf.onchange = function () {
        selectedScenario = sf.value || "__all__";
        renderTrains();
      };
    }

    function fmtDashNum(v, digits) {
      if (v === null || v === undefined || v === "") return "-";
      const n = Number(v);
      if (!Number.isFinite(n)) return "-";
      return n.toFixed(digits);
    }

    function fmtDashPct(v) {
      if (v === null || v === undefined || v === "") return "-";
      const n = Number(v);
      if (!Number.isFinite(n)) return "-";
      return (n * 100).toFixed(1) + "%";
    }

    function dashCards(items) {
      return (items || []).map(function (it) {
        return "<div class='dash-card'><div class='dash-k'>" + esc(it[0]) + "</div><div class='dash-v'>" + esc(it[1]) + "</div></div>";
      }).join("");
    }

    function aggregateBenchmarkKpis(results) {
      const rows = Array.isArray(results) ? results : [];
      const muRows = rows.filter(function (r) { return String(r.agent_name || "").toLowerCase().indexOf("muzero") >= 0; });
      const den = Math.max(1, muRows.length);
      let episodes = 0;
      let avgReturn = 0;
      let avgSteps = 0;
      let timeoutRate = 0;
      let winRate = 0;
      let trackedCaptured = 0;
      let vpNet = 0;
      let decisionSteps = 0;
      let capOpp = 0;
      let capTaken = 0;
      let capTakeRate = 0;
      for (const r of muRows) {
        const k = r.phase_2_9_eval_kpis || {};
        episodes += Number(r.episodes || 0);
        avgReturn += Number(r.avg_return || 0);
        avgSteps += Number(r.avg_steps || 0);
        timeoutRate += Number(r.timeout_rate || 0);
        winRate += Number(r.win_rate || 0);
        trackedCaptured += Number(r.tracked_captured_avg || 0);
        vpNet += Number(((r.vp_net_avg_by_side || {}).GE || 0)) + Number(((r.vp_net_avg_by_side || {}).IT || 0));
        decisionSteps += Number(k.xai_decision_steps || 0);
        capOpp += Number(k.xai_vp_capture_opportunity_steps || 0);
        capTaken += Number(k.xai_vp_capture_taken_steps || 0);
        capTakeRate += Number(k.xai_vp_capture_take_rate || 0);
      }
      return {
        profiles: rows.length,
        episodes: episodes,
        avg_return: avgReturn / den,
        avg_steps: avgSteps / den,
        timeout_rate: timeoutRate / den,
        win_rate: winRate / den,
        tracked_captured_avg: trackedCaptured / den,
        vp_net_proxy: vpNet / den,
        xai_decision_steps: decisionSteps,
        xai_vp_capture_opportunities: capOpp,
        xai_vp_capture_taken: capTaken,
        xai_vp_capture_take_rate: capTakeRate / den,
      };
    }

    function renderTrainDashboard(trains, evals) {
      const host = el("trainDashboard");
      if (!host) return;
      const latestTrain = (trains && trains.length) ? trains[0] : null;
      const latestEval = (evals && evals.length) ? evals[0] : null;
      const bench = aggregateBenchmarkKpis((latestEval && latestEval.results) || []);
      const trainCfg = (latestTrain && latestTrain.config) || {};
      const trainModel = trainCfg.model || {};
      const trainSelf = trainCfg.selfplay || {};
      const runCards = [
        ["Run ID", latestTrain ? (latestTrain.run_id || "-") : "-"],
        ["Scenario", latestTrain ? (latestTrain.scenario_id || "-") : "-"],
        ["Eval", latestEval ? (latestEval.eval_id || "-") : "-"],
        ["Config", model ? (model.config_fingerprint || "-") : "-"],
        ["Train Date (UTC)", latestTrain ? (latestTrain.created_at_utc || "-") : "-"],
        ["Model", model ? (model.model_id || "-") : "-"],
        ["Engine", model ? (model.engine || "-") : "-"],
        ["Device", trainModel.device || "-"],
        ["Run Root", (latestEval && latestEval.source_path) ? String(latestEval.source_path).split("\\\\")[2] || "-" : "-"],
        ["Hidden Dim", trainModel.hidden_dim || "-"],
        ["Obs HxW", (trainModel.observation_height && trainModel.observation_width) ? (String(trainModel.observation_height) + "x" + String(trainModel.observation_width)) : "-"],
        ["MCTS Sims", trainSelf.mcts_simulations || "-"],
      ];
      const latestBenchCards = [
        ["Scenario", latestEval ? (latestEval.scenario_id || "-") : "-"],
        ["Profiles", String(Math.round(Number(bench.profiles || 0)))],
        ["Episodes", String(Math.round(Number(bench.episodes || 0)))],
        ["Avg Return", fmtDashNum(bench.avg_return, 3)],
        ["Avg Steps", fmtDashNum(bench.avg_steps, 1)],
        ["Timeout Rate", fmtDashPct(bench.timeout_rate)],
        ["Win Rate", fmtDashPct(bench.win_rate)],
        ["Tracked Captured Avg", fmtDashNum(bench.tracked_captured_avg, 3)],
        ["VP Net (proxy)", fmtDashNum(bench.vp_net_proxy, 3)],
        ["Decision Steps", String(Math.round(Number(bench.xai_decision_steps || 0)))],
        ["Capture Opp", String(Math.round(Number(bench.xai_vp_capture_opportunities || 0)))],
        ["Capture Taken", String(Math.round(Number(bench.xai_vp_capture_taken || 0)))],
      ];
      const metricCards = [
        ["VP Capture Take Rate", fmtDashPct(bench.xai_vp_capture_take_rate)],
        ["Objective Target Mode", trainCfg.objective_target_mode || "-"],
        ["Objective Loss Weight", fmtDashNum(trainCfg.objective_loss_weight, 3)],
        ["Replay Capacity", trainCfg.replay_capacity || "-"],
        ["Train Updates/Iter", trainCfg.train_updates_per_iter || "-"],
        ["Iterations", trainCfg.iterations || "-"],
        ["Episodes/Iter", trainCfg.episodes_per_iter || "-"],
        ["Temperature", fmtDashNum(trainSelf.mcts_temperature, 3)],
        ["Dirichlet Epsilon", fmtDashNum(trainSelf.mcts_dirichlet_epsilon, 3)],
        ["Progress Bonus/Hex", fmtDashNum(((trainSelf.reward_shaping || {}).objective_progress_bonus_per_hex), 3)],
        ["Capture Bonus", fmtDashNum(((trainSelf.reward_shaping || {}).capture_bonus), 3)],
        ["VP Capture Bonus/Hex", fmtDashNum(((trainSelf.reward_shaping || {}).vp_capture_bonus_per_hex), 3)],
      ];
      host.innerHTML =
        "<section class='dash-section'><h3 class='dash-title'>Run Details</h3><div class='dash-cards'>" + dashCards(runCards) + "</div></section>" +
        "<section class='dash-section'><h3 class='dash-title'>Latest Benchmark</h3><div class='dash-cards'>" + dashCards(latestBenchCards) + "</div></section>" +
        "<section class='dash-section'><h3 class='dash-title'>Benchmark Metrics</h3><div class='dash-cards'>" + dashCards(metricCards) + "</div></section>";
    }

    function fmtTrainMetric(v, digits) {
      if (v === null || v === undefined || v === "") return "";
      const n = Number(v);
      if (!Number.isFinite(n)) return "";
      return n.toFixed(digits);
    }

    function fmtDiagNum(v, digits) {
      if (v === null || v === undefined || v === "") return "-";
      const n = Number(v);
      if (!Number.isFinite(n)) return "-";
      return n.toFixed(digits || 3);
    }

    function fmtDiagPct(v) {
      if (v === null || v === undefined || v === "") return "-";
      const n = Number(v);
      if (!Number.isFinite(n)) return "-";
      return (n * 100).toFixed(1) + "%";
    }

    async function fetchTrainSummary(runId) {
      const key = String(runId || "");
      if (!key) return {};
      if (Object.prototype.hasOwnProperty.call(trainSummaryCache, key)) {
        return trainSummaryCache[key] || {};
      }
      try {
        const r = await fetch("/api/train-summary?run_id=" + encodeURIComponent(key));
        const payload = await r.json();
        trainSummaryCache[key] = payload || {};
        return trainSummaryCache[key];
      } catch (_e) {
        trainSummaryCache[key] = {};
        return {};
      }
    }

    async function loadTrainSummary(runId) {
      if (!runId) {
        selectedTrainSummary = null;
        const trainPre = el("trainMetricsPre");
        if (trainPre) trainPre.textContent = "{}";
        const archHost = el("trainArchitectureHost");
        if (archHost) archHost.innerHTML = "";
        renderObjectiveRewardConfig();
        renderTrainHeadDiagnostics();
        return;
      }
      selectedTrainSummary = await fetchTrainSummary(runId);
      const trainPre = el("trainMetricsPre");
      if (trainPre) trainPre.textContent = JSON.stringify(selectedTrainSummary || {}, null, 2);
      renderTrainArchitecture();
      renderObjectiveRewardConfig();
      renderTrainHeadDiagnostics();
    }

    function renderTrainArchitecture() {
      const host = el("trainArchitectureHost");
      if (!host) return;
      const trains = (model && model.train_history) || [];
      const tr = trains.find(function (t) { return String(t.run_id || "") === String(selectedTrainRun || ""); }) || {};
      const m = selectedTrainSummary || {};
      const kpis = [
        ["loss", fmtTrainMetric(m.loss, 4)],
        ["consistency_loss", fmtTrainMetric(m.consistency_loss, 6)],
        ["consistency_pairs", fmtTrainMetric(m.consistency_pairs, 1)],
        ["reanalysis_coverage", fmtTrainMetric(m.reanalysis_coverage, 3)],
        ["reanalysis_target_drift", fmtTrainMetric(m.reanalysis_target_drift, 6)],
        ["reanalysis_policy_drift", fmtTrainMetric(m.reanalysis_policy_drift, 6)],
      ];
      const kpiHtml = kpis
        .filter(function (pair) { return String(pair[1] || "") !== ""; })
        .map(function (pair) {
          return "<div class='kpi'><div class='muted'>" + esc(pair[0]) + "</div><div><b>" + esc(pair[1]) + "</b></div></div>";
        })
        .join("");
      host.innerHTML =
        '<div class="muted" style="margin-bottom:6px;">Selected train: ' + esc(String(tr.run_id || "")) + '</div>' +
        (kpiHtml ? '<div class="grid">' + kpiHtml + '</div>' : '<div class="muted">No train KPIs available yet.</div>');
    }

    function renderObjectiveRewardConfig() {
      const host = el("objectiveRewardConfigRoot");
      if (!host) return;
      const trains = (model && model.train_history) || [];
      const tr = trains.find(function (t) { return String(t.run_id || "") === String(selectedTrainRun || ""); }) || {};
      const cfg = (tr && tr.config) || {};
      const trainBlocks = (tr && tr.objective_reward_config && typeof tr.objective_reward_config === "object")
        ? tr.objective_reward_config
        : {};
      const trainCfg = (cfg && typeof cfg === "object") ? cfg : {};
      const selfCfg = (trainCfg.selfplay && typeof trainCfg.selfplay === "object") ? trainCfg.selfplay : {};
      const rewardCfgRun = (selfCfg.reward_shaping && typeof selfCfg.reward_shaping === "object") ? selfCfg.reward_shaping : {};
      const signalCfgRun = (trainCfg.objective_signal && typeof trainCfg.objective_signal === "object") ? trainCfg.objective_signal : {};
      const headCfgRun = (trainCfg.objective_head && typeof trainCfg.objective_head === "object") ? trainCfg.objective_head : {};
      const reportCfgRun = (trainCfg.objective_reporting && typeof trainCfg.objective_reporting === "object") ? trainCfg.objective_reporting : {};
      const rewardCfg = Object.keys(rewardCfgRun).length ? rewardCfgRun : ((trainBlocks.reward_shaping && typeof trainBlocks.reward_shaping === "object") ? trainBlocks.reward_shaping : {});
      const signalCfg = Object.keys(signalCfgRun).length ? signalCfgRun : ((trainBlocks.objective_signal && typeof trainBlocks.objective_signal === "object") ? trainBlocks.objective_signal : {});
      const headCfg = Object.keys(headCfgRun).length ? headCfgRun : ((trainBlocks.objective_head && typeof trainBlocks.objective_head === "object") ? trainBlocks.objective_head : {});
      const reportCfg = Object.keys(reportCfgRun).length ? reportCfgRun : ((trainBlocks.objective_reporting && typeof trainBlocks.objective_reporting === "object") ? trainBlocks.objective_reporting : {});
      const preflightWarnings = Array.isArray(trainBlocks.preflight_warnings) ? trainBlocks.preflight_warnings : [];
      function pull(label, explicitValue, fallbackKey) {
        if (explicitValue !== undefined && explicitValue !== null && explicitValue !== "") {
          return { label: label, value: explicitValue, source: "run_config" };
        }
        if (Object.prototype.hasOwnProperty.call(objectiveRewardDefaults, fallbackKey || label)) {
          return {
            label: label,
            value: objectiveRewardDefaults[fallbackKey || label],
            source: "fallback_default",
          };
        }
        return { label: label, value: "N/A", source: "legacy_missing" };
      }
      const rows = [
        { section: "Objective Head Runtime", row: pull("objective_loss_weight", trainCfg.objective_loss_weight) },
        { section: "Objective Head Runtime", row: pull("objective_target_mode", trainCfg.objective_target_mode) },
        { section: "Objective Head Runtime", row: pull("objective_pos_weight", trainCfg.objective_pos_weight) },
        { section: "Objective Head Runtime", row: pull("objective_opportunity_max_dist", trainCfg.objective_opportunity_max_dist) },
        { section: "Objective Head Runtime", row: pull("objective_progress_positive_threshold", headCfg.progress_positive_threshold) },
        { section: "Objective Head Runtime", row: pull("objective_opportunity_near_vp_max_dist", signalCfg.opportunity_near_vp_max_dist) },
        { section: "Reward Shaping", row: pull("terminal_scale", rewardCfg.terminal_scale) },
        { section: "Reward Shaping", row: pull("damage_weight", rewardCfg.damage_weight) },
        { section: "Reward Shaping", row: pull("kill_weight", rewardCfg.kill_weight) },
        { section: "Reward Shaping", row: pull("vp_action_bonus", rewardCfg.vp_action_bonus) },
        { section: "Reward Shaping", row: pull("capture_bonus", rewardCfg.capture_bonus) },
        { section: "Reward Shaping", row: pull("vp_capture_bonus_per_hex", rewardCfg.vp_capture_bonus_per_hex) },
        { section: "Reward Shaping", row: pull("vp_net_gain_bonus", rewardCfg.vp_net_gain_bonus) },
        { section: "Reward Shaping", row: pull("vp_net_loss_penalty", rewardCfg.vp_net_loss_penalty) },
        { section: "Reward Shaping", row: pull("objective_progress_bonus_per_hex", rewardCfg.objective_progress_bonus_per_hex) },
        { section: "Reward Shaping", row: pull("objective_no_progress_penalty", rewardCfg.objective_no_progress_penalty) },
        { section: "Reward Shaping", row: pull("objective_no_progress_attack_penalty", rewardCfg.objective_no_progress_attack_penalty) },
        { section: "Reward Shaping", row: pull("reaction_fire_miss_penalty", rewardCfg.reaction_fire_miss_penalty) },
        { section: "Reward Shaping", row: pull("idle_penalty", rewardCfg.idle_penalty) },
        { section: "Reward Shaping", row: pull("idle_with_options_multiplier", rewardCfg.idle_with_options_multiplier) },
        { section: "Reward Shaping", row: pull("terminal_win_bonus", rewardCfg.terminal_win_bonus) },
        { section: "Reward Shaping", row: pull("terminal_draw_bonus", rewardCfg.terminal_draw_bonus) },
        { section: "Reward Shaping", row: pull("terminal_loss_penalty", rewardCfg.terminal_loss_penalty) },
        { section: "Objective Opportunity & Thresholds", row: pull("conversion_window_steps_after_progress", reportCfg.conversion_window_steps_after_progress) },
        { section: "Objective Opportunity & Thresholds", row: pull("assault_advantage_prob_threshold", reportCfg.assault_advantage_prob_threshold) },
        { section: "Objective Opportunity & Thresholds", row: pull("assault_advantage_margin_threshold", reportCfg.assault_advantage_margin_threshold) },
        { section: "Objective Opportunity & Thresholds", row: pull("assault_advantage_legal_count_threshold", reportCfg.assault_advantage_legal_count_threshold) },
        { section: "Objective Opportunity & Thresholds", row: pull("assault_advantage_min_score", reportCfg.assault_advantage_min_score) },
        { section: "Objective Opportunity & Thresholds", row: pull("near_vp_max_dist", reportCfg.near_vp_max_dist) },
        { section: "Objective Opportunity & Thresholds", row: pull("strong_progress_delta_threshold", reportCfg.strong_progress_delta_threshold) },
        { section: "Objective Opportunity & Thresholds", row: pull("high_confidence_prob_threshold", reportCfg.high_confidence_prob_threshold) },
        { section: "Objective Opportunity & Thresholds", row: pull("high_confidence_margin_threshold", reportCfg.high_confidence_margin_threshold) },
        { section: "Objective Opportunity & Thresholds", row: pull("assault_advantage_cover_max", reportCfg.assault_advantage_cover_max) },
        { section: "Objective Opportunity & Thresholds", row: pull("decision_flip_legal_count_tolerance", reportCfg.decision_flip_legal_count_tolerance) },
      ];
      const sectionLayout = [
        { name: "Reward Shaping", wide: true },
        { name: "Objective Head Runtime", wide: false },
        { name: "Objective Opportunity & Thresholds", wide: false },
      ];
      function renderSectionTable(sectionDef) {
        const sectionName = sectionDef.name;
        const sectionClass = sectionDef.wide
          ? "objective-reward-section objective-reward-section--wide"
          : "objective-reward-section";
        const sectionRows = rows
          .filter(function (entry) { return entry.section === sectionName; })
          .map(function (entry) { return entry.row; });
        const body = sectionRows.map(function (r) {
          return "<tr>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(r.label) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(r.value) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(r.source) + "</td>" +
            "</tr>";
        }).join("");
        return "<div class='" + sectionClass + "'>" +
          "<h3>" + esc(sectionName) + "</h3>" +
          "<div class='objective-reward-table-wrap'>" +
            "<table class='objective-reward-table'>" +
              "<thead><tr>" +
                "<th style='text-align:left;border:1px solid #334155;padding:6px;'>parameter</th>" +
                "<th style='text-align:left;border:1px solid #334155;padding:6px;'>active_value</th>" +
                "<th style='text-align:left;border:1px solid #334155;padding:6px;'>source</th>" +
              "</tr></thead>" +
              "<tbody>" + body + "</tbody>" +
            "</table>" +
          "</div>" +
        "</div>";
      }
      const sectionTables = sectionLayout.map(renderSectionTable).join("");
      host.innerHTML =
        '<div class="muted" style="margin-bottom:6px;">Selected train: ' + esc(String(tr.run_id || "N/A")) + '</div>' +
        (preflightWarnings.length
          ? ('<div class="muted" style="margin-bottom:8px;color:#fbbf24;">Config preflight warnings: ' + esc(preflightWarnings.join(", ")) + '</div>')
          : "") +
        '<div class="muted" style="margin-bottom:8px;">Source precedence: <b>run_config</b> -> <b>fallback_default</b> -> <b>legacy_missing (N/A)</b>.</div>' +
        "<div class='objective-reward-grid'>" + sectionTables + "</div>" +
        "<div class='muted' style='margin-top:8px;'>Legacy runs without objective/reward blocks show N/A where no default/fallback is declared.</div>";
    }

    function renderTrainHeadDiagnostics() {
      const root = el("trainHeadDiagnosticsRoot");
      if (!root) return;
      const m = (selectedTrainSummary && typeof selectedTrainSummary === "object") ? selectedTrainSummary : {};
      const expected = {
        policy: ["policy_loss"],
        value: ["value_loss"],
        reward: ["reward_loss"],
        objective: ["objective_loss"],
        consistency: [
          "consistency_loss",
          "consistency_pairs",
          "reanalysis_coverage",
          "reanalysis_target_drift",
          "reanalysis_policy_drift",
        ],
      };
      function metricState(v) {
        if (v === null || v === undefined || v === "") return { hasValue: false, text: "-" };
        const n = Number(v);
        if (!Number.isFinite(n)) return { hasValue: false, text: "-" };
        return { hasValue: true, text: fmtDiagNum(n) };
      }
      function headTable(title, rows) {
        const body = rows.map(function (r) {
          return '<tr>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(r[0]) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(r[1]) + '</td>' +
            '</tr>';
        }).join("");
        return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
          '<h3 style="margin:0 0 6px 0;">' + esc(title) + '</h3>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;width:40%;">metric</th>' +
          '<th style="border:1px solid #334155;padding:6px;">value</th>' +
          '</tr></thead><tbody>' + body + '</tbody></table></div>';
      }
      const statusRows = [];
      let available = 0;
      let expectedCount = 0;
      const sections = [];
      function pushSection(name, title) {
        const keys = expected[name] || [];
        const rows = [];
        for (const key of keys) {
          expectedCount += 1;
          const st = metricState(m[key]);
          if (st.hasValue) available += 1;
          rows.push([key, st.text]);
        }
        sections.push(headTable(title, rows));
      }
      pushSection("policy", "Policy Head (train)");
      pushSection("value", "Value Head (train)");
      pushSection("reward", "Reward Head (train)");
      pushSection("objective", "Objective Head (train)");
      pushSection("consistency", "Consistency Head (train)");
      let status = "ok";
      if (available === 0) status = "no data";
      else if (available < expectedCount) status = "partial";
      statusRows.push('status=' + status);
      statusRows.push('available=' + String(available) + '/' + String(expectedCount));
      let html = '<div class="muted" style="margin-bottom:8px;">' + esc(statusRows.join(" | ")) + '</div>';
      if (status === "no data") {
        html += '<div class="muted">No train head diagnostics found for selected train.</div>';
      } else {
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;align-items:start;">';
        html += sections.join("");
        html += '</div>';
      }
      root.innerHTML = html;
    }

    async function renderTrains() {
      const allTrains = model.train_history || [];
      const trains = selectedScenario === "__all__"
        ? allTrains
        : allTrains.filter(function (t) { return (t.scenario_id || "") === selectedScenario; });
      if (!selectedTrainRun && trains.length) selectedTrainRun = trains[0].run_id || "";
      if (selectedTrainRun && !trains.some(function (t) { return t.run_id === selectedTrainRun; })) {
        selectedTrainRun = trains.length ? trains[0].run_id : "";
      }
      const missing = trains
        .map(function (t) { return String(t.run_id || ""); })
        .filter(function (id) { return id && !Object.prototype.hasOwnProperty.call(trainSummaryCache, id); });
      if (missing.length) {
        await Promise.all(missing.map(function (id) { return fetchTrainSummary(id); }));
      }
      const root = el("trainList");
      let trainsHtml = "";
      for (const t of trains) {
        const activeClass = (selectedTrainRun === t.run_id) ? "active" : "";
        const tm = trainSummaryCache[String(t.run_id || "")] || {};
        const kpiLine = [
          "cov=" + (fmtTrainMetric(tm.reanalysis_coverage, 3) || "-"),
          "v_drift=" + (fmtTrainMetric(tm.reanalysis_target_drift, 6) || "-"),
          "p_drift=" + (fmtTrainMetric(tm.reanalysis_policy_drift, 6) || "-"),
          "k_pairs=" + (fmtTrainMetric(tm.consistency_pairs, 1) || "-"),
        ].join(" | ");
        trainsHtml +=
          '<div class="item ' + activeClass + '" data-run-id="' + esc(t.run_id) + '">' +
            '<div><b>' + esc(t.run_id) + '</b></div>' +
            '<div class="muted">' + esc(t.created_at_utc) + ' | scenario=' + esc(t.scenario_id) + ' | commit=' + esc(t.git_commit || "") + '</div>' +
            '<div class="muted">retrain=' + (t.is_retrain ? "yes" : "no") + ' parent=' + esc(t.parent_run_id || "") + '</div>' +
            '<div class="muted">ez_metrics: ' + esc(kpiLine) + '</div>' +
          '</div>';
      }
      root.innerHTML = trainsHtml;
      const nodes = root.querySelectorAll(".item");
      for (const node of nodes) {
        node.onclick = function () {
          selectedTrainRun = node.getAttribute("data-run-id") || "";
          renderTrains();
          renderEvals();
        };
      }
      await loadTrainSummary(selectedTrainRun);
      renderEvals();
    }

    function renderEvals() {
      const all = model.eval_history || [];
      const rowsBase = all.filter(function (r) { return (r.train_run_id || "") === selectedTrainRun; });
      const rows = selectedScenario === "__all__"
        ? rowsBase
        : rowsBase.filter(function (r) { return (r.scenario_id || "") === selectedScenario; });
      const root = el("evalList");
      if (!rows.length) {
        root.innerHTML = '<div class="muted">No evals for selected train.</div>';
        return;
      }
      let html = '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
        '<th style="border:1px solid #334155;padding:6px;">eval_id</th>' +
        '<th style="border:1px solid #334155;padding:6px;">created_at</th>' +
        '<th style="border:1px solid #334155;padding:6px;">scenario</th>' +
        '<th style="border:1px solid #334155;padding:6px;">results</th>' +
        '</tr></thead><tbody>';
      for (const r of rows) {
        const nres = Array.isArray(r.results) ? r.results.length : 0;
        html += '<tr>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.eval_id || "")) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.created_at_utc || "")) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.scenario_id || "")) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(nres)) + '</td>' +
          '</tr>';
      }
      html += '</tbody></table>';
      root.innerHTML = html;
      // Ensure downstream tabs always render for current eval rows.
      renderUnifiedActions(rows);
      renderEvalDecisions(rows);
      renderMatchReplay(rows);
      renderMuzeroVps(rows);
    }

    function normalizeControllerLabel(raw) {
      const p = String(raw || "").trim().toLowerCase();
      if (p === "mcts") return "MuZero";
      if (p === "random") return "Random";
      if (p === "legacy/unlabeled") return "Legacy/Unlabeled";
      return "Unknown";
    }

    function controllerFor(resultRow, side) {
      const s = String(side || "").trim().toUpperCase();
      const cb = (resultRow && resultRow.controller_by_side) || {};
      const explicit = String(cb[s] || cb[side] || "").trim();
      if (explicit) return explicit;
      const pb = (resultRow && resultRow.policy_by_side) || {};
      const p = String(pb[s] || pb[side] || "").toLowerCase();
      if (!p) return "Legacy/Unlabeled";
      return normalizeControllerLabel(p);
    }

    function aggregateHeadDiagnostics(evalRows) {
      const rows = Array.isArray(evalRows) ? evalRows : [];
      const out = {
        policy: { eval_decision_steps: 0, eval_confidence_mean: 0, eval_margin_mean: 0, eval_latent_signal_coverage: 0, train_policy_loss: 0 },
        value: { train_value_loss: 0, eval_win_rate_proxy: 0, eval_avg_return_proxy: 0 },
        reward: { train_reward_loss: 0, eval_avg_return_proxy: 0, eval_avg_steps_proxy: 0 },
        objective: {
          train_objective_loss: 0,
          eval_vp_capture_opportunity_steps: 0,
          eval_vp_capture_taken_steps: 0,
          eval_vp_immediate_capture_opportunity_steps: 0,
          eval_vp_immediate_capture_taken_steps: 0,
          eval_vp_capture_take_rate: 0,
          eval_vp_immediate_capture_take_rate: 0,
          eval_vp_conversion_efficiency: 0,
          eval_vp_immediate_conversion_efficiency: 0,
          eval_vp_capture_take_rate_denominator_steps: 0,
          eval_vp_conversion_efficiency_denominator_steps: 0
        },
        consistency: {
          train_consistency_loss: 0,
          train_consistency_pairs: 0,
          train_reanalysis_coverage: 0,
          train_reanalysis_target_drift: 0,
          train_reanalysis_policy_drift: 0
        },
        mcts: {
          eval_decision_steps: 0,
          eval_policy_confidence_mean: 0,
          eval_policy_margin_mean: 0,
          eval_latent_signal_coverage: 0,
          eval_reaction_window_count: 0,
          eval_melee_attempts: 0
        },
      };
      let n = 0;
      for (const r of rows) {
        const h = (r && r.head_diagnostics_eval) || {};
        if (!h || Object.keys(h).length === 0) continue;
        n += 1;
        for (const head of ["policy", "value", "reward", "objective", "consistency", "mcts"]) {
          const src = h[head] || {};
          const dst = out[head] || {};
          for (const k of Object.keys(dst)) {
            dst[k] += Number(src[k] || 0);
          }
        }
      }
      const den = Math.max(1, n);
      for (const head of ["policy", "value", "reward", "objective", "consistency", "mcts"]) {
        const dst = out[head] || {};
        for (const k of Object.keys(dst)) {
          dst[k] = Number(dst[k] || 0) / den;
        }
      }
      return { n: n, heads: out };
    }

    function renderMuzeroVps(rows) {
      const root = el("muzeroVpsRoot");
      if (!root) return;
      function sideAllowed(resultRow, side, selectedSide, selectedController) {
        const s = String(side || "").toUpperCase();
        if (selectedSide !== "__all__" && s !== selectedSide) return false;
        const c = controllerFor(resultRow, s);
        if (selectedController !== "__all__" && c !== selectedController) return false;
        return true;
      }
      const muzeroRows = rows.flatMap(function (r) {
        const res = Array.isArray(r.results) ? r.results : [];
        return res.filter(function (x) {
          return String(x.agent_name || "").indexOf("muzero") === 0;
        }).map(function (x) {
          const out = {};
          Object.assign(out, x);
          out.eval_id = r.eval_id;
          out.created_at_utc = r.created_at_utc;
          out.scenario_id = r.scenario_id;
          out.eval_source_path = r.source_path || "";
          out.train_run_id = r.train_run_id || "";
          return out;
        });
      });
      const filtersHost = el("analysisFiltersHost");
      function trackedRates(resultRow) {
        const cls = (resultRow && resultRow.scenario_outcome_class_rates) || {};
        const victory = Number(cls.victory || 0);
        const totalVictory = Number(cls.total_victory || 0);
        const draw = Number(cls.draw || 0);
        const defeat = Number(cls.defeat || 0) + Number(cls.total_defeat || 0);
        return {
          win: victory + totalVictory,
          victory: victory,
          total_victory: totalVictory,
          draw: draw,
          loss: defeat,
        };
      }
      function sideStatsFromRows(resultRows, selectedSide, selectedController) {
        const agg = {};
        for (const r of resultRows) {
          const initBy = r.vp_initial_avg_by_side || {};
          const finalBy = r.vp_final_avg_by_side || {};
          const netBy = r.vp_net_avg_by_side || {};
          const gainBy = r.vp_gained_avg_by_side || {};
          const lostBy = r.vp_lost_avg_by_side || {};
          const sidesLocal = Array.from(new Set(
            Object.keys(initBy).concat(Object.keys(finalBy), Object.keys(netBy), Object.keys(gainBy), Object.keys(lostBy))
          ));
          for (const side of sidesLocal) {
            if (!sideAllowed(r, side, selectedSide, selectedController)) continue;
            const k = String(r.eval_id || "") + "|" + String(r.matchup_profile || "") + "|" + String(side || "");
            if (!agg[k]) {
              agg[k] = {
                eval_id: String(r.eval_id || ""),
                matchup_profile: String(r.matchup_profile || ""),
                side: String(side || ""),
                controller: controllerFor(r, side),
                games: 0,
                vp_initial: 0,
                vp_final: 0,
                vp_net: 0,
                vp_gained: 0,
                vp_lost: 0,
                n_initial: 0,
                n_final: 0,
                n_net: 0,
                n_gained: 0,
                n_lost: 0,
                win_rate_sum: 0,
                draw_rate_sum: 0,
                loss_rate_sum: 0,
                rate_n: 0,
              };
            }
            const a = agg[k];
            const eps = Math.max(1, Number(r.episodes || 1));
            a.games += eps;
            if (Object.prototype.hasOwnProperty.call(initBy, side)) { a.vp_initial += Number(initBy[side] || 0); a.n_initial += 1; }
            if (Object.prototype.hasOwnProperty.call(finalBy, side)) { a.vp_final += Number(finalBy[side] || 0); a.n_final += 1; }
            if (Object.prototype.hasOwnProperty.call(netBy, side)) { a.vp_net += Number(netBy[side] || 0); a.n_net += 1; }
            if (Object.prototype.hasOwnProperty.call(gainBy, side)) { a.vp_gained += Number(gainBy[side] || 0); a.n_gained += 1; }
            if (Object.prototype.hasOwnProperty.call(lostBy, side)) { a.vp_lost += Number(lostBy[side] || 0); a.n_lost += 1; }
            const tr = trackedRates(r);
            a.win_rate_sum += Number(tr.win || 0) * eps;
            a.draw_rate_sum += Number(tr.draw || 0) * eps;
            a.loss_rate_sum += Number(tr.loss || 0) * eps;
            a.rate_n += eps;
          }
        }
        return Object.values(agg).map(function (x) {
          return {
            eval_id: x.eval_id,
            matchup_profile: x.matchup_profile,
            side: x.side,
            controller: x.controller,
            games: x.games,
            vp_initial_avg: x.n_initial ? (x.vp_initial / x.n_initial) : null,
            vp_final_avg: x.n_final ? (x.vp_final / x.n_final) : null,
            vp_net_avg: x.n_net ? (x.vp_net / x.n_net) : null,
            vp_gained_avg: x.n_gained ? (x.vp_gained / x.n_gained) : null,
            vp_lost_avg: x.n_lost ? (x.vp_lost / x.n_lost) : null,
            win_rate: x.rate_n ? (x.win_rate_sum / x.rate_n) : null,
            draw_rate: x.rate_n ? (x.draw_rate_sum / x.rate_n) : null,
            loss_rate: x.rate_n ? (x.loss_rate_sum / x.rate_n) : null,
          };
        }).sort(function (a, b) { return Number(b.games || 0) - Number(a.games || 0); });
      }
      function fmtNum(v) { return (v === null || v === undefined) ? "-" : Number(v).toFixed(3); }
      function fmtPct(v) { return (v === null || v === undefined) ? "-" : (Number(v) * 100).toFixed(1) + "%"; }
      function aggregateXaiVpKpis(resultRows, selectedSide, selectedController) {
        const totals = {
          episodes: 0,
          xai_decision_steps: 0,
          xai_vp_capture_opportunity_steps: 0,
          xai_vp_capture_taken_steps: 0,
          xai_vp_immediate_capture_opportunity_steps: 0,
          xai_vp_immediate_capture_taken_steps: 0,
          xai_policy_confidence_mean: 0,
          xai_policy_margin_mean: 0,
          xai_latent_signal_coverage: 0,
          xai_vp_capture_take_rate: 0,
          xai_vp_immediate_capture_take_rate: 0,
          tracked_captured_avg: 0,
          avg_steps: 0,
          timeout_rate: 0,
          terminal_rate: 0,
          reaction_fire_activation_rate: 0,
          melee_success_rate: 0,
          weight_n: 0,
        };
        for (const row of (resultRows || [])) {
          const eps = Math.max(1, Number(row.episodes || 1));
          let k = row.phase_2_9_eval_kpis || {};
          const bySide = row.phase_2_9_eval_kpis_by_side || {};
          if (selectedSide !== "__all__" && bySide && bySide[selectedSide]) {
            if (!sideAllowed(row, selectedSide, selectedSide, selectedController)) continue;
            k = bySide[selectedSide] || {};
          } else if (selectedSide !== "__all__") {
            continue;
          } else if (selectedController !== "__all__" && bySide && Object.keys(bySide).length > 0) {
            const sides = Object.keys(bySide).filter(side => sideAllowed(row, side, "__all__", selectedController));
            if (!sides.length) continue;
            const merged = {
              xai_decision_steps: 0,
              xai_vp_capture_opportunity_steps: 0,
              xai_vp_capture_taken_steps: 0,
              xai_vp_immediate_capture_opportunity_steps: 0,
              xai_vp_immediate_capture_taken_steps: 0,
              xai_policy_confidence_mean: 0,
              xai_policy_margin_mean: 0,
              xai_latent_signal_coverage: 0,
              xai_vp_capture_take_rate: 0,
              xai_vp_immediate_capture_take_rate: 0,
            };
            for (const side of sides) {
              const ks = bySide[side] || {};
              merged.xai_decision_steps += Number(ks.xai_decision_steps || 0);
              merged.xai_vp_capture_opportunity_steps += Number(ks.xai_vp_capture_opportunity_steps || 0);
              merged.xai_vp_capture_taken_steps += Number(ks.xai_vp_capture_taken_steps || 0);
              merged.xai_vp_immediate_capture_opportunity_steps += Number(ks.xai_vp_immediate_capture_opportunity_steps || 0);
              merged.xai_vp_immediate_capture_taken_steps += Number(ks.xai_vp_immediate_capture_taken_steps || 0);
              merged.xai_policy_confidence_mean += Number(ks.xai_policy_confidence_mean || 0);
              merged.xai_policy_margin_mean += Number(ks.xai_policy_margin_mean || 0);
              merged.xai_latent_signal_coverage += Number(ks.xai_latent_signal_coverage || 0);
              merged.xai_vp_capture_take_rate += Number(ks.xai_vp_capture_take_rate || 0);
              merged.xai_vp_immediate_capture_take_rate += Number(ks.xai_vp_immediate_capture_take_rate || 0);
            }
            const nSides = Math.max(1, sides.length);
            merged.xai_policy_confidence_mean /= nSides;
            merged.xai_policy_margin_mean /= nSides;
            merged.xai_latent_signal_coverage /= nSides;
            merged.xai_vp_capture_take_rate /= nSides;
            merged.xai_vp_immediate_capture_take_rate /= nSides;
            k = merged;
          }
          totals.episodes += eps;
          totals.xai_decision_steps += Number(k.xai_decision_steps || 0);
          totals.xai_vp_capture_opportunity_steps += Number(k.xai_vp_capture_opportunity_steps || 0);
          totals.xai_vp_capture_taken_steps += Number(k.xai_vp_capture_taken_steps || 0);
          totals.xai_vp_immediate_capture_opportunity_steps += Number(k.xai_vp_immediate_capture_opportunity_steps || 0);
          totals.xai_vp_immediate_capture_taken_steps += Number(k.xai_vp_immediate_capture_taken_steps || 0);
          totals.xai_policy_confidence_mean += Number(k.xai_policy_confidence_mean || 0) * eps;
          totals.xai_policy_margin_mean += Number(k.xai_policy_margin_mean || 0) * eps;
          totals.xai_latent_signal_coverage += Number(k.xai_latent_signal_coverage || 0) * eps;
          totals.xai_vp_capture_take_rate += Number(k.xai_vp_capture_take_rate || 0) * eps;
          totals.xai_vp_immediate_capture_take_rate += Number(k.xai_vp_immediate_capture_take_rate || 0) * eps;
          totals.tracked_captured_avg += Number(row.tracked_captured_avg || 0) * eps;
          totals.avg_steps += Number(row.avg_steps || 0) * eps;
          totals.timeout_rate += Number(row.timeout_rate || 0) * eps;
          totals.terminal_rate += Number(row.terminal_rate || 0) * eps;
          totals.reaction_fire_activation_rate += Number(k.reaction_fire_activation_rate || 0) * eps;
          totals.melee_success_rate += Number(k.melee_success_rate || 0) * eps;
          totals.weight_n += eps;
        }
        const den = Math.max(1, Number(totals.weight_n || 0));
        const decisions = Math.max(1, Number(totals.xai_decision_steps || 0));
        return {
          episodes: totals.episodes,
          xai_decision_steps: totals.xai_decision_steps,
          xai_vp_capture_opportunity_steps: totals.xai_vp_capture_opportunity_steps,
          xai_vp_capture_taken_steps: totals.xai_vp_capture_taken_steps,
          xai_vp_immediate_capture_opportunity_steps: totals.xai_vp_immediate_capture_opportunity_steps,
          xai_vp_immediate_capture_taken_steps: totals.xai_vp_immediate_capture_taken_steps,
          xai_policy_confidence_mean: totals.xai_policy_confidence_mean / den,
          xai_policy_margin_mean: totals.xai_policy_margin_mean / den,
          xai_latent_signal_coverage: totals.xai_latent_signal_coverage / den,
          xai_vp_capture_take_rate: totals.xai_vp_capture_take_rate / den,
          xai_vp_immediate_capture_take_rate: totals.xai_vp_immediate_capture_take_rate / den,
          vp_conversion_efficiency: Number(totals.xai_vp_capture_taken_steps || 0) / decisions,
          vp_immediate_conversion_efficiency: Number(totals.xai_vp_immediate_capture_taken_steps || 0) / decisions,
          tracked_captured_avg: totals.tracked_captured_avg / den,
          avg_steps: totals.avg_steps / den,
          timeout_rate: totals.timeout_rate / den,
          terminal_rate: totals.terminal_rate / den,
          reaction_fire_activation_rate: totals.reaction_fire_activation_rate / den,
          melee_success_rate: totals.melee_success_rate / den,
        };
      }
      function aggregateHeadDiagnostics(evalRows) {
        const rows = Array.isArray(evalRows) ? evalRows : [];
        const out = {
          policy: { eval_decision_steps: 0, eval_confidence_mean: 0, eval_margin_mean: 0, eval_latent_signal_coverage: 0, train_policy_loss: 0 },
          value: { train_value_loss: 0, eval_win_rate_proxy: 0, eval_avg_return_proxy: 0 },
          reward: { train_reward_loss: 0, eval_avg_return_proxy: 0, eval_avg_steps_proxy: 0 },
          objective: {
            train_objective_loss: 0,
            eval_vp_capture_opportunity_steps: 0,
            eval_vp_capture_taken_steps: 0,
          eval_vp_immediate_capture_opportunity_steps: 0,
          eval_vp_immediate_capture_taken_steps: 0,
            eval_vp_capture_take_rate: 0,
          eval_vp_immediate_capture_take_rate: 0,
          eval_vp_conversion_efficiency: 0,
          eval_vp_immediate_conversion_efficiency: 0,
          eval_vp_capture_take_rate_denominator_steps: 0,
          eval_vp_conversion_efficiency_denominator_steps: 0
          },
          consistency: {
            train_consistency_loss: 0,
            train_consistency_pairs: 0,
            train_reanalysis_coverage: 0,
            train_reanalysis_target_drift: 0,
            train_reanalysis_policy_drift: 0
          },
          mcts: {
            eval_decision_steps: 0,
            eval_policy_confidence_mean: 0,
            eval_policy_margin_mean: 0,
            eval_latent_signal_coverage: 0,
            eval_reaction_window_count: 0,
            eval_melee_attempts: 0
          },
        };
        let n = 0;
        for (const r of rows) {
          const h = (r && r.head_diagnostics_eval) || {};
          if (!h || Object.keys(h).length === 0) continue;
          n += 1;
          for (const head of ["policy", "value", "reward", "objective", "consistency", "mcts"]) {
            const src = h[head] || {};
            const dst = out[head] || {};
            for (const k of Object.keys(dst)) {
              dst[k] += Number(src[k] || 0);
            }
          }
        }
        const den = Math.max(1, n);
        for (const head of ["policy", "value", "reward", "objective", "consistency", "mcts"]) {
          const dst = out[head] || {};
          for (const k of Object.keys(dst)) {
            dst[k] = Number(dst[k] || 0) / den;
          }
        }
        return { n: n, heads: out };
      }
      const evalIds = Array.from(new Set(rows.map(r => String(r.eval_id || "")).filter(Boolean))).sort();
      const profiles = Array.from(new Set(rows.flatMap(r => (Array.isArray(r.results) ? r.results : []).map(x => String(x.matchup_profile || "")).filter(Boolean)))).sort();
      function resultController(resultRow, side) {
        return controllerFor(resultRow, side);
      }
      function collectSidesFromResult(resultRow) {
        const out = [];
        const summary = (resultRow && resultRow.eval_decision_summary) || {};
        const by = summary.by_action_kind_and_side || {};
        for (const k of Object.keys(by || {})) {
          const row = by[k] || {};
          const s = String(row.unit_side || "").toUpperCase();
          if (s) out.push(s);
        }
        return out;
      }
      const sides = Array.from(new Set(rows.flatMap(r => (Array.isArray(r.results) ? r.results : []).flatMap(x => collectSidesFromResult(x))))).sort();
      const controllers = ["MuZero", "Random", "Legacy/Unlabeled", "Unknown"];
      if (filtersHost) {
        filtersHost.innerHTML =
          '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0;">' +
            '<label class="muted">eval <select id="vpFilterEvalId"><option value="__all__">all</option>' +
            evalIds.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join("") +
            '</select></label>' +
            '<label class="muted">profile <select id="vpFilterProfile"><option value="__all__">all</option>' +
            profiles.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join("") +
            '</select></label>' +
            '<label class="muted">side <select id="vpFilterSide"><option value="__all__">all</option>' +
            sides.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join("") +
            '</select></label>' +
            '<label class="muted">controller <select id="vpFilterController"><option value="__all__">all</option>' +
            controllers.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join("") +
            '</select></label>' +
            '<span id="vpFilterCount" class="muted"></span>' +
            '<span id="vpFilterControllerWarning" class="muted"></span>' +
          '</div>';
      }
      function applySimpleFilters() {
        const e = (((document.getElementById("vpFilterEvalId") || {}).value)) || "__all__";
        const p = (((document.getElementById("vpFilterProfile") || {}).value)) || "__all__";
        const s = (((document.getElementById("vpFilterSide") || {}).value)) || "__all__";
        const c = (((document.getElementById("vpFilterController") || {}).value)) || "__all__";
        const evalRowsForTabs = rows.filter(r =>
          (e === "__all__" || String(r.eval_id || "") === String(e)) &&
          (p === "__all__" || (Array.isArray(r.results) && r.results.some(x => String(x.matchup_profile || "") === String(p)))) &&
          (s === "__all__" || (Array.isArray(r.results) && r.results.some(x => collectSidesFromResult(x).includes(s)))) &&
          (c === "__all__" || (Array.isArray(r.results) && r.results.some(x => collectSidesFromResult(x).some(side => resultController(x, side) === c))))
        );
        const countEl = document.getElementById("vpFilterCount");
        if (countEl) countEl.textContent = String(evalRowsForTabs.length) + "/" + String(rows.length) + " eval rows";
        const warningEl = document.getElementById("vpFilterControllerWarning");
        if (warningEl) {
          const legacyRows = evalRowsForTabs.reduce((acc, er) => {
            const results = Array.isArray(er.results) ? er.results : [];
            return acc + results.filter(rr =>
              Number((rr || {}).controller_legacy_unlabeled_count || 0) > 0
            ).length;
          }, 0);
          warningEl.textContent = legacyRows > 0 ? ("legacy unlabeled rows: " + String(legacyRows)) : "";
        }
        // Replay should stay available even if profile/side/controller narrow data too much.
        const replayRows = rows.filter(r =>
          (e === "__all__" || String(r.eval_id || "") === String(e))
        );
        const filteredMuzeroRows = muzeroRows.filter(r =>
          (e === "__all__" || String(r.eval_id || "") === String(e)) &&
          (p === "__all__" || String(r.matchup_profile || "") === String(p))
        );
        const sideRows = sideStatsFromRows(filteredMuzeroRows, s, c);
        let htmlVps = '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">eval_id</th>' +
          '<th style="border:1px solid #334155;padding:6px;">profile</th>' +
          '<th style="border:1px solid #334155;padding:6px;">side</th>' +
          '<th style="border:1px solid #334155;padding:6px;">controller</th>' +
          '<th style="border:1px solid #334155;padding:6px;">games</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_initial_avg</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_final_avg</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_gained_avg</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_lost_avg</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_net_avg</th>' +
          '<th style="border:1px solid #334155;padding:6px;">win_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">draw_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">loss_rate</th>' +
          '</tr></thead><tbody>';
        if (!sideRows.length) {
          htmlVps += '<tr><td colspan="13" style="border:1px solid #334155;padding:6px;" class="muted">No VP summary rows for current filters.</td></tr>';
        } else {
          const totals = {
            games: 0,
            vp_initial_avg: 0,
            vp_final_avg: 0,
            vp_gained_avg: 0,
            vp_lost_avg: 0,
            vp_net_avg: 0,
            win_rate: 0,
            draw_rate: 0,
            loss_rate: 0,
          };
          for (const r of sideRows) {
            const g = Number(r.games || 0);
            totals.games += g;
            totals.vp_initial_avg += g * Number(r.vp_initial_avg || 0);
            totals.vp_final_avg += g * Number(r.vp_final_avg || 0);
            totals.vp_gained_avg += g * Number(r.vp_gained_avg || 0);
            totals.vp_lost_avg += g * Number(r.vp_lost_avg || 0);
            totals.vp_net_avg += g * Number(r.vp_net_avg || 0);
            totals.win_rate += g * Number(r.win_rate || 0);
            totals.draw_rate += g * Number(r.draw_rate || 0);
            totals.loss_rate += g * Number(r.loss_rate || 0);
            htmlVps += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r.eval_id) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r.matchup_profile) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r.side) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r.controller) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.games || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(r.vp_initial_avg)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(r.vp_final_avg)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(r.vp_gained_avg)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(r.vp_lost_avg)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(r.vp_net_avg)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(r.win_rate)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(r.draw_rate)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(r.loss_rate)) + '</td>' +
              '</tr>';
          }
          const den = Math.max(1, Number(totals.games || 0));
          htmlVps += '<tr style="background:#0f172a;font-weight:700;">' +
            '<td style="border:1px solid #334155;padding:6px;">TOTAL</td>' +
            '<td style="border:1px solid #334155;padding:6px;">all</td>' +
            '<td style="border:1px solid #334155;padding:6px;">all</td>' +
            '<td style="border:1px solid #334155;padding:6px;">all</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(totals.games)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(totals.vp_initial_avg / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(totals.vp_final_avg / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(totals.vp_gained_avg / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(totals.vp_lost_avg / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(totals.vp_net_avg / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(totals.win_rate / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(totals.draw_rate / den)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(totals.loss_rate / den)) + '</td>' +
            '</tr>';
        }
        htmlVps += '</tbody></table>';
        const xai = aggregateXaiVpKpis(filteredMuzeroRows, s, c);
        htmlVps += '<div style="margin-top:12px;"><h3 style="margin:0 0 6px 0;">XAI VP diagnostics</h3>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">episodes</th>' +
          '<th style="border:1px solid #334155;padding:6px;">decision_steps</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_capture_opportunities</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_capture_taken</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_capture_take_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">policy_confidence_mean</th>' +
          '<th style="border:1px solid #334155;padding:6px;">policy_margin_mean</th>' +
          '<th style="border:1px solid #334155;padding:6px;">latent_signal_coverage</th>' +
          '</tr></thead><tbody><tr>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.episodes || 0)))) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.xai_decision_steps || 0)))) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.xai_vp_capture_opportunity_steps || 0)))) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.xai_vp_capture_taken_steps || 0)))) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.xai_vp_capture_take_rate)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(xai.xai_policy_confidence_mean)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(xai.xai_policy_margin_mean)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.xai_latent_signal_coverage)) + '</td>' +
          '</tr></tbody></table></div>';
        htmlVps += '<div style="margin-top:12px;"><h3 style="margin:0 0 6px 0;">Additional diagnostics</h3>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_conversion_efficiency</th>' +
          '<th style="border:1px solid #334155;padding:6px;">tracked_captured_avg</th>' +
          '<th style="border:1px solid #334155;padding:6px;">avg_steps</th>' +
          '<th style="border:1px solid #334155;padding:6px;">terminal_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">timeout_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">reaction_fire_activation_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">melee_success_rate</th>' +
          '</tr></thead><tbody><tr>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.vp_conversion_efficiency)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(xai.tracked_captured_avg)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNum(xai.avg_steps)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.terminal_rate)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.timeout_rate)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.reaction_fire_activation_rate)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPct(xai.melee_success_rate)) + '</td>' +
          '</tr></tbody></table></div>';
        root.innerHTML = htmlVps;
        renderHeadDiagnostics(evalRowsForTabs);
        renderUnifiedActions(evalRowsForTabs, { side: s, controller: c, sideAllowed: sideAllowed });
        renderEvalDecisions(evalRowsForTabs, { side: s, controller: c, sideAllowed: sideAllowed });
        renderMatchReplay(replayRows);
        // Flow graph: keep it alive and filtered by current selectors.
        if (typeof _buildFlowDataset === "function" && typeof _renderFlowGraph === "function") {
          const flowRows = muzeroRows.filter(r =>
            (e === "__all__" || String(r.eval_id || "") === String(e)) &&
            (p === "__all__" || String(r.matchup_profile || "") === String(p))
          );
          const flowSides = Array.from(new Set(flowRows.flatMap(r => collectSidesFromResult(r)))).sort();
          const flowSideNode = document.getElementById("flowSideFilter");
          if (flowSideNode) {
            const current = flowSideSelected;
            flowSideNode.innerHTML = "<option value='__all__'>all</option>" + flowSides.map(v => "<option value='" + esc(v) + "'>" + esc(v) + "</option>").join("");
            if (current !== "__all__" && flowSides.includes(current)) flowSideNode.value = current;
            else flowSideNode.value = "__all__";
            flowSideSelected = String(flowSideNode.value || "__all__");
            flowSideNode.onchange = function () {
              flowSideSelected = String(flowSideNode.value || "__all__");
              const dsLocal = _buildFlowDataset(flowRows, flowSideSelected, e, p, s, c);
              _renderFlowGraph(dsLocal);
            };
          }
          const ds = _buildFlowDataset(flowRows, flowSideSelected, e, p, s, c);
          _renderFlowGraph(ds);
        } else {
          const summaryEl = document.getElementById("flowSummary");
          if (summaryEl) summaryEl.textContent = "Flow graph temporarily unavailable while reloading.";
        }
      }
      const fe = document.getElementById("vpFilterEvalId");
      const fp = document.getElementById("vpFilterProfile");
      const fs = document.getElementById("vpFilterSide");
      const fc = document.getElementById("vpFilterController");
      if (fe) fe.onchange = applySimpleFilters;
      if (fp) fp.onchange = applySimpleFilters;
      if (fs) fs.onchange = applySimpleFilters;
      if (fc) fc.onchange = applySimpleFilters;
      applySimpleFilters();
    }
      function renderHeadDiagnostics(evalRowsForTabs) {
        const root = document.getElementById("headDiagnosticsRoot");
        if (!root) return;
        const rowsTotal = Array.isArray(evalRowsForTabs) ? evalRowsForTabs.length : 0;
        const headDiag = aggregateHeadDiagnostics(evalRowsForTabs);
        let status = "ok";
        if (rowsTotal === 0 || Number(headDiag.n || 0) <= 0) status = "no data";
        else if (Number(headDiag.n || 0) < rowsTotal) status = "partial";
        function hasFiniteNumber(v) {
          const n = Number(v);
          return Number.isFinite(n);
        }
        function getHeadMetric(headName, metricKey) {
          const rows = Array.isArray(evalRowsForTabs) ? evalRowsForTabs : [];
          let sum = 0;
          let count = 0;
          for (const row of rows) {
            const src = (((row || {}).head_diagnostics_eval || {})[headName] || {});
            if (!Object.prototype.hasOwnProperty.call(src, metricKey)) continue;
            const raw = src[metricKey];
            if (!hasFiniteNumber(raw)) continue;
            sum += Number(raw);
            count += 1;
          }
          if (!count) return null;
          return sum / count;
        }
        function fmtEvalNum(v, digits) {
          if (v === null || v === undefined) return "N/A";
          const n = Number(v);
          if (!Number.isFinite(n)) return "N/A";
          return n.toFixed(digits);
        }
        function fmtEvalPct(v) {
          if (v === null || v === undefined) return "N/A";
          const n = Number(v);
          if (!Number.isFinite(n)) return "N/A";
          return (n * 100).toFixed(1) + "%";
        }
        function coverageForHead(headName, metricKeys) {
          const keys = Array.isArray(metricKeys) ? metricKeys : [];
          const available = keys.filter(function (k) { return getHeadMetric(headName, k) !== null; }).length;
          let cov = "none";
          if (available === keys.length && keys.length > 0) cov = "complete";
          else if (available > 0) cov = "partial";
          let reason = "no eval telemetry for this head";
          if (cov === "complete") reason = String(available) + "/" + String(keys.length) + " metrics present";
          else if (cov === "partial") reason = String(available) + "/" + String(keys.length) + " metrics present";
          return { status: cov, reason: reason, available: available, total: keys.length };
        }
        function coverageBadge(cov) {
          const c = cov || { status: "none", reason: "no eval telemetry for this head" };
          let color = "#ef4444";
          if (c.status === "complete") color = "#22c55e";
          else if (c.status === "partial") color = "#f59e0b";
          return '<span style="display:inline-block;padding:1px 6px;border:1px solid #334155;border-radius:999px;color:' + color + ';font-size:11px;">' +
            esc(String(c.status || "none") + " (" + String(c.reason || "") + ")") +
            '</span>';
        }
        function collectIntentSignals() {
          const rows = Array.isArray(evalRowsForTabs) ? evalRowsForTabs : [];
          const actionMap = {};
          const ownershipBySide = {};
          const mismatchBySide = {};
          let overrideSignalRows = 0;
          let legacyFallbackRows = 0;
          let totalTopActionCount = 0;
          for (const evalRow of rows) {
            const results = Array.isArray(evalRow.results) ? evalRow.results : [];
            for (const r of results) {
              const tops = Array.isArray(r.eval_decisions_top) ? r.eval_decisions_top : [];
              for (const t of tops) {
                const aid = String(t.action_id || "UNKNOWN_ACTION");
                if (!actionMap[aid]) {
                  actionMap[aid] = {
                    action_id: aid,
                    action_kind: String(t.action_kind || "N/A"),
                    unit_side: String(t.unit_side || "N/A"),
                    count: 0,
                  };
                }
                const c = Number(t.count || 0);
                actionMap[aid].count += Number.isFinite(c) ? c : 0;
                totalTopActionCount += Number.isFinite(c) ? c : 0;
              }
              const own = ((r || {}).eval_decision_summary || {}).decision_ownership_by_side || {};
              for (const side of Object.keys(own || {})) {
                if (!ownershipBySide[side]) ownershipBySide[side] = { side: side, rows: 0, policy_kept: 0, overwritten: 0, override_signal_rows: 0, legacy_fallback_rows: 0 };
                const src = own[side] || {};
                ownershipBySide[side].rows += Number(src.rows || 0);
                ownershipBySide[side].policy_kept += Number(src.policy_kept || 0);
                ownershipBySide[side].overwritten += Number(src.overwritten || 0);
                ownershipBySide[side].override_signal_rows += Number(src.override_signal_rows || 0);
                ownershipBySide[side].legacy_fallback_rows += Number(src.legacy_fallback_rows || 0);
              }
              const ownSource = ((r || {}).eval_decision_summary || {}).decision_ownership_source || {};
              overrideSignalRows += Number(ownSource.override_signal_rows || 0);
              legacyFallbackRows += Number(ownSource.legacy_fallback_rows || 0);
              const mm = ((r || {}).eval_decision_summary || {}).execution_mismatch_by_side || {};
              for (const side of Object.keys(mm || {})) {
                if (!mismatchBySide[side]) mismatchBySide[side] = { side: side, rows: 0, execution_match: 0, execution_mismatch: 0 };
                const src = mm[side] || {};
                mismatchBySide[side].rows += Number(src.rows || 0);
                mismatchBySide[side].execution_match += Number(src.execution_match || 0);
                mismatchBySide[side].execution_mismatch += Number(src.execution_mismatch || 0);
              }
            }
          }
          const topPolicyActions = Object.values(actionMap)
            .sort(function (a, b) { return Number(b.count || 0) - Number(a.count || 0); })
            .slice(0, 5)
            .map(function (x) {
              const share = totalTopActionCount > 0 ? (Number(x.count || 0) / totalTopActionCount) : null;
              return [
                String(x.action_id || "N/A"),
                String(x.action_kind || "N/A"),
                String(x.unit_side || "N/A"),
                share === null ? "N/A" : ((share * 100).toFixed(1) + "%"),
              ];
            });
          const mctsOwnershipRows = Object.values(ownershipBySide)
            .sort(function (a, b) { return String(a.side || "").localeCompare(String(b.side || "")); })
            .map(function (x) {
              return [
                String(x.side || "N/A"),
                String(Math.round(Number(x.rows || 0))),
                String(Math.round(Number(x.policy_kept || 0))),
                String(Math.round(Number(x.overwritten || 0))),
                String(Math.round(Number(x.override_signal_rows || 0))),
                String(Math.round(Number(x.legacy_fallback_rows || 0))),
              ];
            });
          const executionMismatchRows = Object.values(mismatchBySide)
            .sort(function (a, b) { return String(a.side || "").localeCompare(String(b.side || "")); })
            .map(function (x) {
              return [
                String(x.side || "N/A"),
                String(Math.round(Number(x.rows || 0))),
                String(Math.round(Number(x.execution_match || 0))),
                String(Math.round(Number(x.execution_mismatch || 0))),
              ];
            });
          return {
            topPolicyActions: topPolicyActions,
            mctsOwnershipRows: mctsOwnershipRows,
            executionMismatchRows: executionMismatchRows,
            ownershipSourceSummary: {
              override_signal_rows: Math.round(overrideSignalRows),
              legacy_fallback_rows: Math.round(legacyFallbackRows),
            },
          };
        }
        function headTable(title, rows) {
          const body = (rows || []).map(function (r) {
            return '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r[0]) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r[1]) + '</td>' +
              '</tr>';
          }).join("");
          return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<h3 style="margin:0 0 6px 0;">' + esc(title) + '</h3>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
            '<th style="border:1px solid #334155;padding:6px;width:40%;">metric</th>' +
            '<th style="border:1px solid #334155;padding:6px;">value</th>' +
            '</tr></thead><tbody>' + body + '</tbody></table></div>';
        }
        function tableRows(rows, columns, emptyMsg) {
          const cols = Array.isArray(columns) ? columns : [];
          if (!Array.isArray(rows) || !rows.length) {
            return '<tr><td colspan="' + esc(String(Math.max(1, cols.length))) + '" style="border:1px solid #334155;padding:6px;" class="muted">' + esc(emptyMsg) + '</td></tr>';
          }
          return rows.map(function (r) {
            const cells = Array.isArray(r) ? r : [];
            return '<tr>' + cells.map(function (c) {
              return '<td style="border:1px solid #334155;padding:6px;">' + esc(String(c)) + '</td>';
            }).join("") + '</tr>';
          }).join("");
        }
        function intentTable(title, columns, rows, emptyMsg) {
          const cols = Array.isArray(columns) ? columns : [];
          return '<div style="margin-top:8px;">' +
            '<div class="muted" style="margin-bottom:4px;">' + esc(title) + '</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
            cols.map(function (c) { return '<th style="border:1px solid #334155;padding:6px;">' + esc(c) + '</th>'; }).join("") +
            '</tr></thead><tbody>' + tableRows(rows, cols, emptyMsg) + '</tbody></table>' +
            '</div>';
        }
        function headCard(title, coverage, summary, metricRows, intentHtml) {
          return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px;">' +
              '<h3 style="margin:0;">' + esc(title) + '</h3>' +
              coverageBadge(coverage) +
            '</div>' +
            '<div class="muted" style="margin-bottom:6px;">' + esc(summary) + '</div>' +
            headTable("Metrics", metricRows) +
            intentHtml +
          '</div>';
        }
        const headSpecRows = [
          { key: "policy", label: "Policy", metrics: ["eval_decision_steps", "eval_confidence_mean", "eval_margin_mean", "eval_latent_signal_coverage", "train_policy_loss"] },
          { key: "value", label: "Value", metrics: ["train_value_loss", "eval_win_rate_proxy", "eval_avg_return_proxy"] },
          { key: "reward", label: "Reward", metrics: ["train_reward_loss", "eval_avg_return_proxy", "eval_avg_steps_proxy"] },
          { key: "objective", label: "Objective", metrics: ["train_objective_loss", "eval_vp_capture_opportunity_steps", "eval_vp_capture_taken_steps", "eval_vp_immediate_capture_opportunity_steps", "eval_vp_immediate_capture_taken_steps", "eval_vp_capture_take_rate", "eval_vp_immediate_capture_take_rate", "eval_vp_conversion_efficiency", "eval_vp_immediate_conversion_efficiency"] },
          { key: "consistency", label: "Consistency", metrics: ["train_consistency_loss", "train_consistency_pairs", "train_reanalysis_coverage", "train_reanalysis_target_drift", "train_reanalysis_policy_drift"] },
          { key: "mcts", label: "MCTS", metrics: ["eval_decision_steps", "eval_policy_confidence_mean", "eval_policy_margin_mean", "eval_latent_signal_coverage", "eval_reaction_window_count", "eval_melee_attempts"] },
        ];
        function stateColor(statusName) {
          if (statusName === "complete") return "#22c55e";
          if (statusName === "partial") return "#f59e0b";
          return "#ef4444";
        }
        function summarizeRowCoverage(rowObj) {
          const srcRoot = (rowObj && rowObj.head_diagnostics_eval && typeof rowObj.head_diagnostics_eval === "object") ? rowObj.head_diagnostics_eval : {};
          const perHead = {};
          const reasons = [];
          const counts = { complete: 0, partial: 0, none: 0 };
          for (const spec of headSpecRows) {
            const src = (srcRoot && srcRoot[spec.key] && typeof srcRoot[spec.key] === "object") ? srcRoot[spec.key] : {};
            let available = 0;
            const missing = [];
            for (const mk of spec.metrics) {
              if (Object.prototype.hasOwnProperty.call(src, mk) && hasFiniteNumber(src[mk])) available += 1;
              else missing.push(mk);
            }
            let statusLocal = "none";
            if (available === spec.metrics.length && spec.metrics.length > 0) statusLocal = "complete";
            else if (available > 0) statusLocal = "partial";
            counts[statusLocal] += 1;
            let reason = String(src.telemetry_coverage_reason || src.reason || "").trim();
            if (!reason) {
              if (statusLocal === "complete") reason = "all expected metrics available";
              else if (statusLocal === "partial") reason = "missing metrics: " + missing.slice(0, 2).join(", ");
              else reason = "no eval telemetry for this head";
            }
            perHead[spec.key] = {
              status: statusLocal,
              available: available,
              total: spec.metrics.length,
              reason: reason,
            };
            if (statusLocal !== "complete") reasons.push(reason);
          }
          return {
            perHead: perHead,
            counts: counts,
            missingHeads: Object.keys(perHead).filter(function (k) { return String((perHead[k] || {}).status || "none") !== "complete"; }),
            reasons: reasons,
          };
        }
        function stateBreakdownCard(statusCounts, totalHeads, label) {
          const safeTotal = Math.max(1, Number(totalHeads || 0));
          function line(statusName) {
            const c = Number(statusCounts[statusName] || 0);
            return '<span style="display:inline-block;padding:3px 8px;border:1px solid #334155;border-radius:999px;color:' + stateColor(statusName) + ';margin-right:6px;">' +
              esc(statusName + "=" + String(c) + "/" + String(safeTotal) + " (" + ((c * 100) / safeTotal).toFixed(1) + "%)") +
              '</span>';
          }
          return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<div style="font-weight:700;margin-bottom:6px;">' + esc(label) + '</div>' +
            line("complete") + line("partial") + line("none") +
            '</div>';
        }
        function topReasonsList(reasons, title) {
          const map = {};
          for (const r of (Array.isArray(reasons) ? reasons : [])) {
            const key = String(r || "").trim() || "unspecified reason";
            map[key] = Number(map[key] || 0) + 1;
          }
          const rows = Object.keys(map).map(function (k) { return [k, map[k]]; })
            .sort(function (a, b) { return Number(b[1] || 0) - Number(a[1] || 0); })
            .slice(0, 5);
          return intentTable(title, ["reason", "count"], rows, "No partial/none reasons.");
        }
        const intents = collectIntentSignals();
        function objectiveHeadMetric(metricName) {
          const v = getHeadMetric("objective", metricName);
          if (v !== null) return v;
          if (metricName === "eval_vp_immediate_capture_opportunity_steps") return getHeadMetric("objective", "eval_vp_capture_opportunity_steps");
          if (metricName === "eval_vp_immediate_capture_taken_steps") return getHeadMetric("objective", "eval_vp_capture_taken_steps");
          if (metricName === "eval_vp_immediate_capture_take_rate") return getHeadMetric("objective", "eval_vp_capture_take_rate");
          if (metricName === "eval_vp_immediate_conversion_efficiency") return getHeadMetric("objective", "eval_vp_conversion_efficiency");
          return v;
        }
        let html = '<div class="muted" style="margin-bottom:8px;">status=' + esc(status) + ' | rows_with_head_diag=' + esc(String(Math.round(Number(headDiag.n || 0)))) + '/' + esc(String(rowsTotal)) + '</div>';
        if (status === "no data") {
          root.innerHTML = html + '<div class="muted">No eval head diagnostics found for current eval filters.</div>';
          return;
        }
        const overallBreakdownRows = [];
        const overallStateCounts = { complete: 0, partial: 0, none: 0 };
        const overallReasons = [];
        for (const spec of headSpecRows) {
          const cov = coverageForHead(spec.key, spec.metrics);
          overallStateCounts[cov.status] += 1;
          if (cov.status !== "complete") overallReasons.push(String(cov.reason || "unspecified reason"));
          overallBreakdownRows.push([
            spec.label,
            String(cov.status || "none"),
            String(Number(cov.available || 0)) + "/" + String(Number(cov.total || 0)),
            String(cov.reason || ""),
          ]);
        }
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;align-items:start;margin-bottom:10px;">';
        html += stateBreakdownCard(overallStateCounts, headSpecRows.length, "Coverage state breakdown (heads)");
        html += '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
          '<div style="font-weight:700;margin-bottom:6px;">Coverage breakdown by head</div>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">head</th>' +
          '<th style="border:1px solid #334155;padding:6px;">status</th>' +
          '<th style="border:1px solid #334155;padding:6px;">metrics</th>' +
          '<th style="border:1px solid #334155;padding:6px;">reason</th>' +
          '</tr></thead><tbody>' + tableRows(overallBreakdownRows, ["head", "status", "metrics", "reason"], "No head diagnostics available.") + '</tbody></table>' +
          '</div>';
        html += topReasonsList(overallReasons, "Frequent partial/none reasons");
        html += '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
          '<div style="font-weight:700;margin-bottom:6px;">Decision Influence quick access</div>' +
          '<div class="muted" style="margin-bottom:6px;">Use replay for step-level influence; ownership uses policy_overridden_by_mcts (fallback: execution_mismatch on legacy runs).</div>' +
          '<div class="muted" style="margin-bottom:6px;">Ownership source coverage: override_signal_rows=' + esc(String(intents.ownershipSourceSummary.override_signal_rows || 0)) + ', legacy_fallback_rows=' + esc(String(intents.ownershipSourceSummary.legacy_fallback_rows || 0)) + '</div>' +
          '<button id="headDiagOpenReplayBtn" style="padding:4px 8px;font-size:12px;">Open Match Replay (Decision Influence)</button>' +
          intentTable(
            "MCTS decision ownership by side",
            ["side", "rows", "policy_kept", "overwritten", "override_signal_rows", "legacy_fallback_rows"],
            intents.mctsOwnershipRows,
            "No MCTS ownership signals in eval diagnostics."
          ) +
          intentTable(
            "Execution mismatch by side (legacy compatibility metric)",
            ["side", "rows", "execution_match", "execution_mismatch"],
            intents.executionMismatchRows,
            "No execution mismatch metrics in eval diagnostics."
          ) +
          '</div>';
        html += '</div>';
        if (rowsTotal > 1) {
          const rowOptions = evalRowsForTabs.map(function (r, idx) {
            const evalId = String((r && r.eval_id) || "n/a");
            const scenario = String((r && r.scenario_id) || "n/a");
            return '<option value="' + esc(String(idx)) + '">' + esc("row " + String(idx + 1) + " | eval " + evalId + " | " + scenario) + '</option>';
          }).join("");
          html += '<details open style="margin-bottom:10px;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<summary style="cursor:pointer;font-weight:700;">Row/step telemetry inspector</summary>' +
            '<div class="muted" style="margin-top:6px;">Inspect row-level telemetry gaps here; use replay tab for per-step diagnostics.</div>' +
            '<label class="muted" style="display:block;margin-top:6px;">Row <select id="headDiagRowSelect" style="margin-left:6px;">' + rowOptions + '</select></label>' +
            '<div id="headDiagRowInspectorHost" style="margin-top:8px;"></div>' +
            '</details>';
        }
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;align-items:start;">';
        const policyMetrics = [
          ["eval_decision_steps", fmtEvalNum(getHeadMetric("policy", "eval_decision_steps"), 1)],
          ["eval_confidence_mean", fmtEvalNum(getHeadMetric("policy", "eval_confidence_mean"), 4)],
          ["eval_margin_mean", fmtEvalNum(getHeadMetric("policy", "eval_margin_mean"), 4)],
          ["eval_latent_signal_coverage", fmtEvalPct(getHeadMetric("policy", "eval_latent_signal_coverage"))],
          ["train_policy_loss", fmtEvalNum(getHeadMetric("policy", "train_policy_loss"), 4)],
        ];
        const policyCoverage = coverageForHead("policy", headSpecRows[0].metrics);
        const policyIntentHtml = intentTable(
          "Top-k policy actions (eval_decisions_top)",
          ["action_id", "action_kind", "side", "share"],
          intents.topPolicyActions,
          "No top-k policy actions in eval/replay sources."
        );
        const policyConf = getHeadMetric("policy", "eval_confidence_mean");
        const policySummary = (policyConf === null)
          ? "Policy intent is unavailable for current filters (N/A)."
          : (policyConf >= 0.6
            ? "Policy focuses on dominant actions with high confidence."
            : "Policy explores multiple candidate actions.");
        html += headCard("Policy Head", policyCoverage, policySummary, policyMetrics, policyIntentHtml);

        const valueMetrics = [
          ["train_value_loss", fmtEvalNum(getHeadMetric("value", "train_value_loss"), 4)],
          ["eval_win_rate_proxy", fmtEvalPct(getHeadMetric("value", "eval_win_rate_proxy"))],
          ["eval_avg_return_proxy", fmtEvalNum(getHeadMetric("value", "eval_avg_return_proxy"), 4)],
        ];
        const valueCoverage = coverageForHead("value", headSpecRows[1].metrics);
        html += headCard("Value Head", valueCoverage, "Value estimates expected outcome for the active side.", valueMetrics, "");

        const rewardMetrics = [
          ["train_reward_loss", fmtEvalNum(getHeadMetric("reward", "train_reward_loss"), 4)],
          ["eval_avg_return_proxy", fmtEvalNum(getHeadMetric("reward", "eval_avg_return_proxy"), 4)],
          ["eval_avg_steps_proxy", fmtEvalNum(getHeadMetric("reward", "eval_avg_steps_proxy"), 2)],
        ];
        const rewardCoverage = coverageForHead("reward", headSpecRows[2].metrics);
        html += headCard("Reward Head", rewardCoverage, "Reward head estimates immediate gain/cost tendencies.", rewardMetrics, "");

        const objectiveMetrics = [
          ["train_objective_loss", fmtEvalNum(getHeadMetric("objective", "train_objective_loss"), 4)],
          ["eval_vp_capture_opportunity_steps (sum objective_had_opportunity)", fmtEvalNum(getHeadMetric("objective", "eval_vp_capture_opportunity_steps"), 1)],
          ["eval_vp_immediate_capture_opportunity_steps (capture legal now)", fmtEvalNum(objectiveHeadMetric("eval_vp_immediate_capture_opportunity_steps"), 1)],
          ["eval_vp_capture_taken_steps", fmtEvalNum(getHeadMetric("objective", "eval_vp_capture_taken_steps"), 1)],
          ["eval_vp_immediate_capture_taken_steps", fmtEvalNum(objectiveHeadMetric("eval_vp_immediate_capture_taken_steps"), 1)],
          ["eval_vp_capture_take_rate", fmtEvalPct(getHeadMetric("objective", "eval_vp_capture_take_rate"))],
          ["eval_vp_immediate_capture_take_rate", fmtEvalPct(objectiveHeadMetric("eval_vp_immediate_capture_take_rate"))],
          ["eval_vp_conversion_efficiency", fmtEvalPct(getHeadMetric("objective", "eval_vp_conversion_efficiency"))],
          ["eval_vp_immediate_conversion_efficiency", fmtEvalPct(objectiveHeadMetric("eval_vp_immediate_conversion_efficiency"))],
          ["take_rate_denominator_steps", fmtEvalNum(getHeadMetric("objective", "eval_vp_capture_take_rate_denominator_steps"), 1)],
          ["conversion_efficiency_denominator_steps", fmtEvalNum(getHeadMetric("objective", "eval_vp_conversion_efficiency_denominator_steps"), 1)],
        ];
        const objectiveCoverage = coverageForHead("objective", headSpecRows[3].metrics);
        const objOpp = getHeadMetric("objective", "eval_vp_capture_opportunity_steps");
        const objTaken = getHeadMetric("objective", "eval_vp_capture_taken_steps");
        const objImmediateOpp = objectiveHeadMetric("eval_vp_immediate_capture_opportunity_steps");
        const objImmediateTaken = objectiveHeadMetric("eval_vp_immediate_capture_taken_steps");
        const objectiveIntentHtml = intentTable(
          "Objective intent signals",
          ["signal", "value"],
          [
            ["vp_capture_opportunities (objective_had_opportunity)", fmtEvalNum(objOpp, 1)],
            ["vp_immediate_capture_opportunities (legal capture window)", fmtEvalNum(objImmediateOpp, 1)],
            ["vp_capture_taken", fmtEvalNum(objTaken, 1)],
            ["vp_immediate_capture_taken", fmtEvalNum(objImmediateTaken, 1)],
            ["vp_take_rate", fmtEvalPct(getHeadMetric("objective", "eval_vp_capture_take_rate"))],
            ["vp_immediate_take_rate", fmtEvalPct(objectiveHeadMetric("eval_vp_immediate_capture_take_rate"))],
            ["vp_conversion_efficiency_denominator", fmtEvalNum(getHeadMetric("objective", "eval_vp_conversion_efficiency_denominator_steps"), 1)],
          ],
          "No objective intent signals in eval telemetry."
        );
        const objectiveSummary = (objOpp === null || objTaken === null)
          ? "Objective intent is unavailable for current filters (N/A)."
          : (objOpp > 0 && objTaken > 0
            ? "Objective head identifies and converts VP opportunities."
            : "Objective head sees VP opportunities but conversion is limited.");
        html += headCard("Objective Head", objectiveCoverage, objectiveSummary, objectiveMetrics, objectiveIntentHtml);

        const consistencyMetrics = [
          ["train_consistency_loss", fmtEvalNum(getHeadMetric("consistency", "train_consistency_loss"), 4)],
          ["train_consistency_pairs", fmtEvalNum(getHeadMetric("consistency", "train_consistency_pairs"), 1)],
          ["train_reanalysis_coverage", fmtEvalPct(getHeadMetric("consistency", "train_reanalysis_coverage"))],
          ["train_reanalysis_target_drift", fmtEvalNum(getHeadMetric("consistency", "train_reanalysis_target_drift"), 4)],
          ["train_reanalysis_policy_drift", fmtEvalNum(getHeadMetric("consistency", "train_reanalysis_policy_drift"), 4)],
        ];
        const consistencyCoverage = coverageForHead("consistency", headSpecRows[4].metrics);
        html += headCard("Consistency Head", consistencyCoverage, "Consistency tracks latent stability under reanalysis.", consistencyMetrics, "");

        const mctsMetrics = [
          ["eval_decision_steps", fmtEvalNum(getHeadMetric("mcts", "eval_decision_steps"), 1)],
          ["eval_policy_confidence_mean", fmtEvalNum(getHeadMetric("mcts", "eval_policy_confidence_mean"), 4)],
          ["eval_policy_margin_mean", fmtEvalNum(getHeadMetric("mcts", "eval_policy_margin_mean"), 4)],
          ["eval_latent_signal_coverage", fmtEvalPct(getHeadMetric("mcts", "eval_latent_signal_coverage"))],
          ["eval_reaction_window_count", fmtEvalNum(getHeadMetric("mcts", "eval_reaction_window_count"), 1)],
          ["eval_melee_attempts", fmtEvalNum(getHeadMetric("mcts", "eval_melee_attempts"), 1)],
        ];
        const mctsCoverage = coverageForHead("mcts", headSpecRows[5].metrics);
        const mctsIntentHtml = intentTable(
          "MCTS decision ownership by side",
          ["side", "rows", "policy_kept", "overwritten", "override_signal_rows", "legacy_fallback_rows"],
          intents.mctsOwnershipRows,
          "No MCTS ownership signals in eval diagnostics."
        ) + intentTable(
          "Execution mismatch by side (legacy compatibility metric)",
          ["side", "rows", "execution_match", "execution_mismatch"],
          intents.executionMismatchRows,
          "No execution mismatch metrics in eval diagnostics."
        );
        const mctsMargin = getHeadMetric("mcts", "eval_policy_margin_mean");
        const mctsSummary = (mctsMargin === null)
          ? "MCTS intent is unavailable for current filters (N/A)."
          : (mctsMargin >= 0.25
            ? "MCTS converges on a dominant line."
            : "MCTS keeps meaningful alternatives open.");
        html += headCard("MCTS Diagnostics", mctsCoverage, mctsSummary, mctsMetrics, mctsIntentHtml);
        html += '</div>';
        root.innerHTML = html;
        const openReplayBtn = document.getElementById("headDiagOpenReplayBtn");
        if (openReplayBtn) {
          openReplayBtn.onclick = function () {
            switchTab("replay");
          };
        }
        function renderSelectedRowCoverage(rowIndexRaw) {
          const inspectorHost = document.getElementById("headDiagRowInspectorHost");
          if (!inspectorHost) return;
          const rows = Array.isArray(evalRowsForTabs) ? evalRowsForTabs : [];
          if (!rows.length) {
            inspectorHost.innerHTML = '<div class="muted">No rows to inspect.</div>';
            return;
          }
          const rowIndex = Math.max(0, Math.min(rows.length - 1, Number(rowIndexRaw || 0)));
          const rowObj = rows[rowIndex] || {};
          const rowSummary = summarizeRowCoverage(rowObj);
          const breakdownRows = headSpecRows.map(function (spec) {
            const c = rowSummary.perHead[spec.key] || { status: "none", available: 0, total: spec.metrics.length, reason: "no eval telemetry for this head" };
            return [spec.label, c.status, String(Number(c.available || 0)) + "/" + String(Number(c.total || 0)), c.reason];
          });
          const missingTxt = rowSummary.missingHeads.length
            ? rowSummary.missingHeads.map(function (k) { return String(k || "").toUpperCase(); }).join(", ")
            : "none";
          inspectorHost.innerHTML =
            stateBreakdownCard(rowSummary.counts, headSpecRows.length, "Selected row coverage states") +
            '<div style="margin-top:8px;">' +
              '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
                '<th style="border:1px solid #334155;padding:6px;">head</th>' +
                '<th style="border:1px solid #334155;padding:6px;">status</th>' +
                '<th style="border:1px solid #334155;padding:6px;">metrics</th>' +
                '<th style="border:1px solid #334155;padding:6px;">reason</th>' +
              '</tr></thead><tbody>' + tableRows(breakdownRows, ["head", "status", "metrics", "reason"], "No row telemetry.") + '</tbody></table>' +
            '</div>' +
            '<div class="muted" style="margin-top:6px;">Missing/partial heads: ' + esc(missingTxt) + '</div>' +
            topReasonsList(rowSummary.reasons, "Frequent reasons in selected row");
        }
        const rowSelect = document.getElementById("headDiagRowSelect");
        if (rowSelect) {
          rowSelect.onchange = function () {
            renderSelectedRowCoverage(Number(rowSelect.value || 0));
          };
          renderSelectedRowCoverage(Number(rowSelect.value || 0));
        }
      }
      function renderUnifiedActions(filteredResultRows, filterCtx) {
        const host = document.getElementById("unifiedRoot");
        if (!host) return;
        if (!Array.isArray(filteredResultRows) || !filteredResultRows.length) {
          host.innerHTML = '<h3 style="margin:8px 0;">By Action Kind</h3><div class="muted">No rows for current filters.</div>';
          return;
        }
        const rowMap = {};
        const rowBySideMap = {};
        for (const er of filteredResultRows) {
          const results = Array.isArray(er.results) ? er.results : [];
          for (const r of results) {
            const summary = (r && r.eval_decision_summary) || {};
            const by = summary.by_action_kind_and_side || {};
            for (const key of Object.keys(by || {})) {
              const src = by[key] || {};
              const action = String(src.action_kind || "UNKNOWN");
              const side = String(src.unit_side || "UNK");
              if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, side, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
              const ctrl = String(controllerFor(r, side));
              if (!rowMap[action]) rowMap[action] = { action: action, count: 0, damage: 0, kills: 0 };
              rowMap[action].count += Number(src.count || 0);
              rowMap[action].damage += Number(src.damage_sum || 0);
              rowMap[action].kills += Number(src.kills_sum || 0);
              const k2 = action + "|" + side + "|" + ctrl;
              if (!rowBySideMap[k2]) rowBySideMap[k2] = { action: action, side: side, controller: ctrl, count: 0, damage: 0, kills: 0 };
              rowBySideMap[k2].count += Number(src.count || 0);
              rowBySideMap[k2].damage += Number(src.damage_sum || 0);
              rowBySideMap[k2].kills += Number(src.kills_sum || 0);
            }
          }
        }
        const rows = Object.values(rowMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
        const rowsBySide = Object.values(rowBySideMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
        let html = '<h3 style="margin:8px 0;">By Action Kind</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">action_kind</th>' +
          '<th style="border:1px solid #334155;padding:6px;">count</th>' +
          '<th style="border:1px solid #334155;padding:6px;">damage</th>' +
          '<th style="border:1px solid #334155;padding:6px;">kills</th>' +
          '</tr></thead><tbody>';
        if (!rows.length) {
          html += '<tr><td colspan="4" style="border:1px solid #334155;padding:6px;" class="muted">No unified rows available.</td></tr>';
        } else {
          for (const r of rows) {
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.count || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.damage || 0).toFixed(3)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.kills || 0).toFixed(3)) + '</td>' +
              '</tr>';
          }
        }
        html += '</tbody></table>';
        html += '<h3 style="margin:12px 0 8px 0;">By Action x Side x Controller</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">action_kind</th>' +
          '<th style="border:1px solid #334155;padding:6px;">side</th>' +
          '<th style="border:1px solid #334155;padding:6px;">controller</th>' +
          '<th style="border:1px solid #334155;padding:6px;">count</th>' +
          '<th style="border:1px solid #334155;padding:6px;">damage</th>' +
          '<th style="border:1px solid #334155;padding:6px;">kills</th>' +
          '</tr></thead><tbody>';
        if (!rowsBySide.length) {
          html += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No side/controller rows available.</td></tr>';
        } else {
          for (const r of rowsBySide) {
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.side || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.controller || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.count || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.damage || 0).toFixed(3)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.kills || 0).toFixed(3)) + '</td>' +
              '</tr>';
          }
        }
        html += '</tbody></table>';
        host.innerHTML = html;
      }
      function renderEvalDecisions(filteredResultRows, filterCtx) {
        const host = document.getElementById("evalDecisionsRoot");
        if (!host) return;
        if (!Array.isArray(filteredResultRows) || !filteredResultRows.length) {
          host.innerHTML = '<h3 style="margin:8px 0;">Table A: Action Kind x Side</h3><div class="muted">No rows for current filters.</div>';
          return;
        }
        const rowMap = {};
        const topActions = {};
        const ownership = {};
        for (const er of filteredResultRows) {
          const results = Array.isArray(er.results) ? er.results : [];
          for (const r of results) {
            const summary = (r && r.eval_decision_summary) || {};
            const by = summary.by_action_kind_and_side || {};
            for (const key of Object.keys(by || {})) {
              const src = by[key] || {};
              const srcSide = String(src.unit_side || "UNK");
              if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, srcSide, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
              const k = String(src.action_kind || "UNKNOWN") + "|" + String(src.unit_side || "UNK");
              if (!rowMap[k]) rowMap[k] = { action_kind: String(src.action_kind || "UNKNOWN"), side: String(src.unit_side || "UNK"), count: 0, damage: 0, kills: 0 };
              rowMap[k].count += Number(src.count || 0);
              rowMap[k].damage += Number(src.damage_sum || 0);
              rowMap[k].kills += Number(src.kills_sum || 0);
            }
            const tops = Array.isArray(r.eval_decisions_top) ? r.eval_decisions_top : [];
            for (const t of tops) {
              const tSide = String(t.unit_side || "UNK");
              if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, tSide, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
              const aid = String(t.action_id || "UNKNOWN_ACTION");
              if (!topActions[aid]) topActions[aid] = { action_id: aid, action_kind: String(t.action_kind || ""), side: String(t.unit_side || ""), count: 0, damage: 0, kills: 0 };
              topActions[aid].count += Number(t.count || 0);
              topActions[aid].damage += Number(t.damage_sum || 0);
              topActions[aid].kills += Number(t.kills_sum || 0);
            }
            const own = summary.decision_ownership_by_side || {};
            for (const s of Object.keys(own || {})) {
              if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, s, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
              const o = own[s] || {};
              if (!ownership[s]) ownership[s] = { side: s, rows: 0, policy_kept: 0, overwritten: 0, override_signal_rows: 0, legacy_fallback_rows: 0 };
              ownership[s].rows += Number(o.rows || 0);
              ownership[s].policy_kept += Number(o.policy_kept || 0);
              ownership[s].overwritten += Number(o.overwritten || 0);
              ownership[s].override_signal_rows += Number(o.override_signal_rows || 0);
              ownership[s].legacy_fallback_rows += Number(o.legacy_fallback_rows || 0);
            }
          }
        }
        const rows = Object.values(rowMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
        const topRows = Object.values(topActions).sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 20);
        const ownRows = Object.values(ownership).sort((a, b) => String(a.side).localeCompare(String(b.side)));
        let html = '<h3 style="margin:8px 0;">Table A: Action Kind x Side</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">action_kind</th>' +
          '<th style="border:1px solid #334155;padding:6px;">side</th>' +
          '<th style="border:1px solid #334155;padding:6px;">count</th>' +
          '<th style="border:1px solid #334155;padding:6px;">damage</th>' +
          '<th style="border:1px solid #334155;padding:6px;">kills</th>' +
          '</tr></thead><tbody>';
        if (!rows.length) {
          html += '<tr><td colspan="5" style="border:1px solid #334155;padding:6px;" class="muted">No decision rows available.</td></tr>';
        } else {
          for (const r of rows) {
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action_kind || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.side || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.count || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.damage || 0).toFixed(3)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.kills || 0).toFixed(3)) + '</td>' +
              '</tr>';
          }
        }
        html += '</tbody></table>';
        html += '<h3 style="margin:12px 0 8px 0;">Table B: Decision Ownership by Side</h3>' +
          '<div class="muted" style="margin:0 0 6px 0;">Source: policy_overridden_by_mcts (fallback: execution_mismatch for legacy runs without override telemetry).</div>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">side</th>' +
          '<th style="border:1px solid #334155;padding:6px;">rows</th>' +
          '<th style="border:1px solid #334155;padding:6px;">policy_kept</th>' +
          '<th style="border:1px solid #334155;padding:6px;">overwritten</th>' +
          '<th style="border:1px solid #334155;padding:6px;">override_signal_rows</th>' +
          '<th style="border:1px solid #334155;padding:6px;">legacy_fallback_rows</th>' +
          '</tr></thead><tbody>';
        if (!ownRows.length) {
          html += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No ownership rows available.</td></tr>';
        } else {
          for (const r of ownRows) {
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.side || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.rows || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.policy_kept || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.overwritten || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.override_signal_rows || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.legacy_fallback_rows || 0)) + '</td>' +
              '</tr>';
          }
        }
        html += '</tbody></table>';
        html += '<h3 style="margin:12px 0 8px 0;">Top Actions</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">action_id</th>' +
          '<th style="border:1px solid #334155;padding:6px;">action_kind</th>' +
          '<th style="border:1px solid #334155;padding:6px;">side</th>' +
          '<th style="border:1px solid #334155;padding:6px;">count</th>' +
          '<th style="border:1px solid #334155;padding:6px;">damage</th>' +
          '<th style="border:1px solid #334155;padding:6px;">kills</th>' +
          '</tr></thead><tbody>';
        if (!topRows.length) {
          html += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No top actions available.</td></tr>';
        } else {
          for (const r of topRows) {
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action_id || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action_kind || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.side || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.count || 0)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.damage || 0).toFixed(3)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.kills || 0).toFixed(3)) + '</td>' +
              '</tr>';
          }
        }
        html += '</tbody></table>';
        host.innerHTML = html;
      }
      let replayState = {
        evalId: "__all__",
        episodeIndex: 0,
        step: 0,
        playing: false,
        timer: null,
        payload: null,
        pendingLayoutRetries: 0,
        stepNavFeedbackTimer: null,
        unitFilter: "__all__",
        knownUnits: [],
        headTopK: 5,
      };
      function stopReplayTimer() {
        if (replayState.timer) {
          clearInterval(replayState.timer);
          replayState.timer = null;
        }
        replayState.playing = false;
      }
      function renderMatchReplay(filteredResultRows) {
        try {
        const host = document.getElementById("replayRoot");
        if (!host) return;
        host.innerHTML = '<div class="muted">Loading replay...</div>';
        let rows = [];
        try {
          rows = Array.isArray(filteredResultRows)
            ? filteredResultRows
                .map(r => Object.assign({}, r, { eval_source_path: String(r.eval_source_path || r.source_path || "") }))
                .filter(r => String(r.eval_source_path || "").trim())
            : [];
        } catch (e) {
          host.innerHTML = '<div class="muted">Replay rows parse error: ' + esc(String((e && e.message) || e || "unknown")) + '</div>';
          return;
        }
        if (!rows.length) {
          stopReplayTimer();
          host.innerHTML = '<div class="muted">No replay source for current filters (eval_source_path/source_path missing).</div>';
          return;
        }
        const seenEval = {};
        const evalRows = [];
        for (const rr of rows) {
          const eid = String(rr.eval_id || "");
          if (!seenEval[eid]) {
            seenEval[eid] = true;
            evalRows.push(rr);
          }
        }
        if (!evalRows.some(r => String(r.eval_id || "") === String(replayState.evalId || ""))) {
          replayState.evalId = String(evalRows[0].eval_id || "");
          replayState.payload = null;
          replayState.step = 0;
          replayState.episodeIndex = 0;
        }
        const activeRow = evalRows.find(r => String(r.eval_id || "") === String(replayState.evalId || "")) || evalRows[0];
        const speedMs = 220;
        host.innerHTML = `
          <div class="replay-top">
            <button id="replayLoadBtn">Load from selected eval</button>
            <label class="muted">Eval:
              <select id="replayEvalSelect" class="replay-select" style="margin-left:6px;">
                ${evalRows.map(r => `<option value="${esc(String(r.eval_id || ""))}" ${String(r.eval_id||"")===String(replayState.evalId||"")?"selected":""}>${esc(String(r.eval_id || ""))}</option>`).join("")}
              </select>
            </label>
            <label class="muted">Episode:
              <select id="replayEpisodeSelect" class="replay-select" style="margin-left:6px;"></select>
            </label>
            <label class="muted">Step:
              <input id="replayStepRange" type="range" min="0" max="0" value="0" style="width:260px;margin-left:6px;" />
            </label>
            <span id="replayStepLabel" class="muted">step 0/0</span>
            <label class="muted">Unit:
              <span id="replayUnitFilterHost" style="margin-left:6px;"></span>
            </label>
            <button id="replayUnitFilterClearBtn" title="Clear unit filter">Reset Unit</button>
            <button id="replayPrevStepBtn" title="Go to previous step">Prev Step</button>
            <button id="replayNextStepBtn" title="Go to next step">Next Step</button>
            <button id="replayPlayBtn">Play</button>
            <button id="replayPauseBtn">Pause</button>
            <span id="replayStepNavFeedback" class="muted" style="min-width:180px;"></span>
            <label class="muted">Speed(ms):
              <input id="replaySpeedInput" class="replay-input" type="number" min="40" max="2000" value="${speedMs}" style="width:88px;margin-left:6px;" />
            </label>
            <label class="muted">Head top-k:
              <input id="replayHeadTopKInput" class="replay-input" type="number" min="1" max="10" value="${Math.max(1, Number(replayState.headTopK || 5))}" style="width:72px;margin-left:6px;" />
            </label>
          </div>
          <div id="replaySummary" class="replay-kv"></div>
          <div class="replay-grid">
            <div class="replay-panel">
              <h3>Map Snapshot</h3>
              <canvas id="replayCanvas" width="980" height="540" class="replay-canvas"></canvas>
            </div>
            <div style="display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:10px;min-height:0;">
              <div class="replay-panel">
                <h3>Step Details</h3>
                <div id="replayStepDetail" class="list"></div>
              </div>
              <div class="replay-panel">
                <h3>Head Diagnostics (per step)</h3>
                <div id="replayHeadDiagnosticsHost" class="list"></div>
              </div>
              <div class="replay-panel">
                <h3>Decision Influence</h3>
                <div id="replayDecisionInfluenceHost" class="list"></div>
              </div>
              <div class="replay-panel">
                <h3>Units Snapshot</h3>
                <div id="replayUnitsHost" class="list"></div>
              </div>
            </div>
            <div class="replay-panel" style="min-height:0;display:flex;flex-direction:column;">
              <h3>Execution Log</h3>
              <pre id="replayLogHost" style="white-space:pre-wrap;word-break:break-word;background:#0b1220;border:1px solid #334155;border-radius:6px;padding:8px;font-size:12px;line-height:1.35;overflow:auto;max-height:520px;min-height:280px;">Loading...</pre>
            </div>
          </div>
        `;
        async function loadReplay() {
          stopReplayTimer();
          const details = document.getElementById("replayStepDetail");
          if (details) details.innerHTML = '<div class="muted">Loading replay payload...</div>';
          const evalSel = document.getElementById("replayEvalSelect");
          const epSel = document.getElementById("replayEpisodeSelect");
          replayState.evalId = String((((evalSel || {}).value) || replayState.evalId || ""));
          const row = evalRows.find(r => String(r.eval_id || "") === String(replayState.evalId || "")) || activeRow;
          const episodeIdx = Math.max(0, Number((((epSel || {}).value) || replayState.episodeIndex || 0)));
          replayState.episodeIndex = episodeIdx;
          if (!row || !String(row.eval_source_path || "").trim()) {
            replayState.payload = null;
            drawReplay();
            return;
          }
          try {
            const resp = await fetch(`/api/muzero-replay?eval_source_path=${encodeURIComponent(String(row.eval_source_path || ""))}&episode_index=${encodeURIComponent(String(episodeIdx))}`);
            replayState.payload = await resp.json();
            if (replayState.payload && replayState.payload.error) {
              if (details) details.innerHTML = '<div class="muted">Replay payload error: ' + esc(String(replayState.payload.error)) + '</div>';
            }
            replayState.step = 0;
          } catch (_e) {
            replayState.payload = null;
            if (details) details.innerHTML = '<div class="muted">Replay fetch failed.</div>';
          }
          drawReplay();
          loadReplayLog();
        }
        async function loadReplayLog() {
          const logHost = document.getElementById("replayLogHost");
          if (!logHost) return;
          try {
            const evalSel = document.getElementById("replayEvalSelect");
            const epSel = document.getElementById("replayEpisodeSelect");
            const evalId = String((((evalSel || {}).value) || replayState.evalId || ""));
            const epIdx = Math.max(0, Number((((epSel || {}).value) || replayState.episodeIndex || 0)));
            const row = evalRows.find(r => String(r.eval_id || "") === String(evalId)) || activeRow;
            const src = String((row && row.eval_source_path) || "");
            if (!src) {
              logHost.textContent = "No execution log: missing eval_source_path.";
              return;
            }
            const upto = Math.max(0, Number(replayState.step || 0));
            const url = "/api/replay-log?eval_source_path=" + encodeURIComponent(src)
              + "&episode_index=" + encodeURIComponent(String(epIdx))
              + "&upto_step=" + encodeURIComponent(String(upto));
            const resp = await fetch(url);
            const payload = await resp.json();
            const lines = Array.isArray(payload.lines) ? payload.lines : [];
            if (lines.length) {
              const withUnitAfterToPlay = lines.map(function (line) {
                const txt = String(line || "");
                if (txt.indexOf("to_play=") < 0) return txt;
                if (txt.indexOf("unit_id=") >= 0) return txt;
                const unitMatch = txt.match(/action=[^\\s:]+:([^\\s:]+)/);
                if (!unitMatch || !unitMatch[1]) return txt;
                return txt.replace(/(to_play=[^\\s]+)/, "$1 unit_id=" + unitMatch[1]);
              });
              const unitId = String(replayState.unitFilter || "__all__");
              const filteredLines = unitId === "__all__"
                ? withUnitAfterToPlay
                : withUnitAfterToPlay.filter(function (line) { return replayLogLineMatchesUnit(line, unitId); });
              if (filteredLines.length) {
                logHost.textContent = filteredLines.join("\\n");
              } else {
                logHost.textContent = "Execution log has no lines for selected unit.";
              }
            } else if (payload.error) {
              logHost.textContent = "Execution log unavailable: " + String(payload.error);
            } else {
              logHost.textContent = "Execution log has no lines for current episode/step.";
            }
            logHost.scrollTop = logHost.scrollHeight;
          } catch (e) {
            logHost.textContent = "Execution log unavailable: " + String((e && e.message) || e || "unknown error");
          }
        }
        function oddRRaw(q, r) {
          const qn = Number(q || 0);
          const rn = Number(r || 0);
          return {
            // Match assault_ai_ui axialToPixel with HEX_WIDTH=sqrt(3)*HEX_SIZE and HEX_HEIGHT=1.5*HEX_SIZE.
            x: Math.sqrt(3) * (qn + 0.5 * (rn % 2)) + (Math.sqrt(3) / 2),
            y: 1.5 * rn + 1.0,
          };
        }
        function makeProjection(baseCells, w, h, pad) {
          const cells = Array.isArray(baseCells) && baseCells.length
            ? baseCells
            : Array.from({ length: h }, (_, rr) =>
                Array.from({ length: w }, (_, qq) => ({ q: qq, r: rr }))
              ).flat();
          const raws = cells.map((c) => oddRRaw(Number(c.q || 0), Number(c.r || 0)));
          let minX = Number.POSITIVE_INFINITY;
          let maxX = Number.NEGATIVE_INFINITY;
          let minY = Number.POSITIVE_INFINITY;
          let maxY = Number.NEGATIVE_INFINITY;
          for (const p of raws) {
            minX = Math.min(minX, Number(p.x || 0));
            maxX = Math.max(maxX, Number(p.x || 0));
            minY = Math.min(minY, Number(p.y || 0));
            maxY = Math.max(maxY, Number(p.y || 0));
          }
          const spanX = Math.max(1e-9, maxX - minX);
          const spanY = Math.max(1e-9, maxY - minY);
          // Fit by cell centers + one full hex radius margin on each side.
          const spanXWithMargin = spanX + 2.0;
          const spanYWithMargin = spanY + 2.0;
          const scale = Math.min((w - 2 * pad) / spanXWithMargin, (h - 2 * pad) / spanYWithMargin);
          const offsetX = (w - spanXWithMargin * scale) / 2;
          const offsetY = (h - spanYWithMargin * scale) / 2;
          // Exact sb3-style hex geometry: radius ~= center spacing scale.
          const hexRadius = Math.max(2.0, scale);
          const toPixel = (q, r) => {
            const raw = oddRRaw(q, r);
            return {
              x: offsetX + (raw.x - minX + 1.0) * scale,
              y: offsetY + (raw.y - minY + 1.0) * scale,
            };
          };
          return { toPixel, hexRadius };
        }
        function drawHex(ctx, cx, cy, size, stroke, fill) {
          ctx.beginPath();
          for (let i = 0; i < 6; i += 1) {
            const a = (Math.PI / 180) * (60 * i - 30);
            const x = cx + size * Math.cos(a);
            const y = cy + size * Math.sin(a);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.closePath();
          ctx.fillStyle = fill;
          ctx.fill();
          ctx.strokeStyle = stroke;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
        function buildReplayUnitCatalog(transitions) {
          const byId = {};
          for (const row of (Array.isArray(transitions) ? transitions : [])) {
            const units = Array.isArray(row && row.units) ? row.units : [];
            for (const u of units) {
              const unitId = String((u && u.unit_id) || "").trim();
              if (!unitId) continue;
              const unitLabel = String((u && (u.unit_label || u.unit_key)) || "").trim();
              const side = String((u && u.side) || "").trim();
              if (!byId[unitId]) byId[unitId] = { unit_id: unitId, unit_label: unitLabel, side: side };
            }
          }
          return Object.values(byId).sort(function (a, b) { return String(a.unit_id || "").localeCompare(String(b.unit_id || "")); });
        }
        function replayLogLineMatchesUnit(line, unitId) {
          const txt = String(line || "");
          const wanted = String(unitId || "").trim();
          if (!wanted) return true;
          return txt.indexOf("unit_id=" + wanted) >= 0 || txt.indexOf(":" + wanted + ":") >= 0;
        }
        function replayStepHasRelevantUnitActivity(stepRow, unitId) {
          const wanted = String(unitId || "").trim();
          if (!wanted || wanted === "__all__") return true;
          if (!stepRow || typeof stepRow !== "object") return false;
          const unitMatchesWanted = function (value) {
            return String(value || "").trim() === wanted;
          };
          const containsWantedUnit = function (value) {
            if (!value) return false;
            if (Array.isArray(value)) {
              return value.some(function (item) {
                if (item && typeof item === "object") {
                  return (
                    unitMatchesWanted(item.unit_id) ||
                    unitMatchesWanted(item.id) ||
                    unitMatchesWanted(item.actor_unit_id) ||
                    unitMatchesWanted(item.target_unit_id)
                  );
                }
                return unitMatchesWanted(item);
              });
            }
            if (value && typeof value === "object") {
              return (
                unitMatchesWanted(value.unit_id) ||
                unitMatchesWanted(value.id) ||
                unitMatchesWanted(value.actor_unit_id) ||
                unitMatchesWanted(value.target_unit_id)
              );
            }
            return unitMatchesWanted(value);
          };
          const actionId = String((stepRow && stepRow.action_id) || "").trim();
          if (actionId && actionId.indexOf(":" + wanted + ":") >= 0) return true;
          const actionUnit = String((stepRow && stepRow.unit_id) || "").trim();
          if (actionUnit && actionUnit === wanted) return true;
          const actionActorUnit = String((stepRow && stepRow.actor_unit_id) || "").trim();
          if (actionActorUnit && actionActorUnit === wanted) return true;
          const actionTargetUnit = String((stepRow && stepRow.target_unit_id) || "").trim();
          if (actionTargetUnit && actionTargetUnit === wanted) return true;
          if (containsWantedUnit(stepRow.unit_event)) return true;
          if (containsWantedUnit(stepRow.unit_events)) return true;
          if (containsWantedUnit(stepRow.events)) return true;
          if (containsWantedUnit(stepRow.runtime_events)) return true;
          if (containsWantedUnit(stepRow.event_unit_ids)) return true;
          if (containsWantedUnit(stepRow.affected_unit_ids)) return true;
          // IMPORTANT: board-state presence alone is not a step activity signal.
          // Using `units` here makes almost every step "relevant" for alive units,
          // which breaks unit-aware Next/Prev navigation.
          return false;
        }
        function setReplayStepNavFeedback(message) {
          const host = document.getElementById("replayStepNavFeedback");
          if (!host) return;
          const txt = String(message || "").trim();
          host.textContent = txt;
          host.title = txt;
          if (!txt) return;
          if (replayState.stepNavFeedbackTimer) clearTimeout(replayState.stepNavFeedbackTimer);
          replayState.stepNavFeedbackTimer = setTimeout(function () {
            const currentHost = document.getElementById("replayStepNavFeedback");
            if (!currentHost) return;
            currentHost.textContent = "";
            currentHost.title = "";
            replayState.stepNavFeedbackTimer = null;
          }, 1600);
        }
        function resolveReplayStepDelta(delta) {
          const transitions = Array.isArray(replayState.payload && replayState.payload.transitions) ? replayState.payload.transitions : [];
          const maxStep = Math.max(0, transitions.length - 1);
          const current = Math.max(0, Math.min(maxStep, Number(replayState.step || 0)));
          const direction = Number(delta || 0) >= 0 ? 1 : -1;
          if (transitions.length <= 1) return { targetStep: current, moved: false };
          if (String(replayState.unitFilter || "__all__") === "__all__") {
            const nextStep = Math.max(0, Math.min(maxStep, current + direction));
            return { targetStep: nextStep, moved: nextStep !== current };
          }
          const selectedUnitId = String(replayState.unitFilter || "__all__");
          let idx = current + direction;
          while (idx >= 0 && idx <= maxStep) {
            if (replayStepHasRelevantUnitActivity(transitions[idx], selectedUnitId)) {
              return { targetStep: idx, moved: idx !== current };
            }
            idx += direction;
          }
          return { targetStep: current, moved: false };
        }
        function moveReplayStep(delta) {
          const nav = resolveReplayStepDelta(delta);
          replayState.step = nav.targetStep;
          drawReplay();
          loadReplayLog();
          if (!nav.moved) {
            const direction = Number(delta || 0) >= 0 ? "next" : "previous";
            if (String(replayState.unitFilter || "__all__") === "__all__") {
              setReplayStepNavFeedback("No " + direction + " step.");
            } else {
              setReplayStepNavFeedback("No " + direction + " step for selected unit.");
            }
          } else {
            setReplayStepNavFeedback("");
          }
          return nav.moved;
        }
        function snapReplayStepToRelevantUnitActivity() {
          if (String(replayState.unitFilter || "__all__") === "__all__") return false;
          const transitions = Array.isArray(replayState.payload && replayState.payload.transitions) ? replayState.payload.transitions : [];
          if (!transitions.length) return false;
          const maxStep = Math.max(0, transitions.length - 1);
          const current = Math.max(0, Math.min(maxStep, Number(replayState.step || 0)));
          const selectedUnitId = String(replayState.unitFilter || "__all__");
          if (replayStepHasRelevantUnitActivity(transitions[current], selectedUnitId)) return false;
          const nextNav = resolveReplayStepDelta(1);
          if (nextNav.moved) {
            replayState.step = nextNav.targetStep;
            return true;
          }
          const prevNav = resolveReplayStepDelta(-1);
          if (prevNav.moved) {
            replayState.step = prevNav.targetStep;
            return true;
          }
          return false;
        }
        function renderReplayUnitFilter(unitOptions) {
          const host = document.getElementById("replayUnitFilterHost");
          if (!host) return;
          const selected = String(replayState.unitFilter || "__all__");
          const opts = (unitOptions || []).map(function (u) {
            const unitId = String((u && u.unit_id) || "");
            const labelCore = String((u && (u.unit_label || "")) || "");
            const side = String((u && u.side) || "");
            const unitLabel = (labelCore ? (unitId + " - " + labelCore) : unitId) + (side ? (" [" + side + "]") : "");
            const isSelected = unitId === selected ? "selected" : "";
            return "<option value='" + esc(unitId) + "' " + isSelected + ">" + esc(unitLabel) + "</option>";
          }).join("");
          host.innerHTML =
            "<select id='replayUnitSelect' class='replay-select'>" +
              "<option value='__all__' " + (selected === "__all__" ? "selected" : "") + ">all units</option>" +
              opts +
            "</select>";
          const select = document.getElementById("replayUnitSelect");
          if (select) {
            select.onchange = function () {
              replayState.unitFilter = String(select.value || "__all__");
              snapReplayStepToRelevantUnitActivity();
              setReplayStepNavFeedback("");
              drawReplay();
              loadReplayLog();
            };
          }
          const clearBtn = document.getElementById("replayUnitFilterClearBtn");
          if (clearBtn) {
            clearBtn.onclick = function () {
              replayState.unitFilter = "__all__";
              setReplayStepNavFeedback("");
              drawReplay();
              loadReplayLog();
            };
          }
        }
        function headSummaryPolicy(stepRow) {
          const topProbRaw = (Array.isArray(stepRow.policy_top_probs) && stepRow.policy_top_probs.length) ? stepRow.policy_top_probs[0] : null;
          const topProb = (topProbRaw === null || topProbRaw === undefined) ? null : Number(topProbRaw);
          const legalCapture = Number(stepRow.legal_capture_options || 0);
          const legalAttack = Number(stepRow.legal_attack_options || 0);
          const actionKind = String(stepRow.action_kind || "").toUpperCase();
          if (topProb === null || Number.isNaN(topProb)) return "no policy distribution available for this step";
          if (legalCapture > 0 && actionKind === "MOVE") return "favors VP advance (capture options open)";
          if (legalAttack > 0 && (actionKind.indexOf("FIRE") >= 0 || actionKind.indexOf("MELEE") >= 0)) return "prioritizes combat";
          if (topProb >= 0.65) return "highly focused decision (high confidence)";
          if (topProb >= 0.40) return "balanced moderate exploration";
          return "high exploration / open decision";
        }
        function headSummaryValue(stepRow) {
          const raw = stepRow.predicted_value_root;
          if (raw === null || raw === undefined || raw === "") return "no value signal available for this step";
          const v = Number(raw);
          if (v >= 0.35) return "favorable outlook for the active side";
          if (v <= -0.35) return "high risk for the active side";
          return "neutral expected value";
        }
        function headSummaryReward(stepRow) {
          const raw = stepRow.dynamics_pred_reward;
          if (raw === null || raw === undefined || raw === "") return "no reward prediction available for this step";
          const r = Number(raw);
          if (r >= 0.2) return "predicts positive immediate reward";
          if (r <= -0.2) return "predicts negative immediate reward/cost";
          return "weak immediate signal";
        }
        function headSummaryObjective(stepRow) {
          const hadOpp = Number(stepRow.objective_had_opportunity || 0) > 0;
          const prog = Number(stepRow.objective_progress_delta || 0);
          const conv = Number(stepRow.objective_converted || 0) > 0;
          if (!hadOpp) return "no clear VP objective opportunity";
          if (conv) return "converts VP opportunity";
          if (prog > 0) return "advances toward VP objective";
          if (prog < 0) return "moves away from VP objective";
          return "no objective progress";
        }
        function headSummaryConsistency(stepRow) {
          const raw = stepRow.dynamics_delta_l2;
          if (raw === null || raw === undefined || raw === "") return "no latent dynamics available";
          const delta = Number(raw);
          if (delta <= 0.6) return "stable latent transition";
          if (delta >= 1.8) return "strong latent state change";
          return "intermediate latent adjustment";
        }
        function headSummaryMcts(stepRow) {
          const p = Number(stepRow.chosen_action_prob || 0);
          const margin = Number(stepRow.mcts_margin || 0);
          const visits = Number(stepRow.mcts_total_visits || 0);
          if (p >= 0.6 || margin >= 0.25) return "MCTS prioritizes a dominant line";
          if (visits > 0 && p <= 0.3 && margin <= 0.1) return "MCTS explores alternatives";
          return "MCTS with moderate consensus";
        }
        function renderReplayHeadDiagnostics(stepRow) {
          const host = document.getElementById("replayHeadDiagnosticsHost");
          if (!host) return;
          if (!stepRow || typeof stepRow !== "object") {
            host.innerHTML = '<div class="muted">No head diagnostics for this step.</div>';
            return;
          }
          const topK = Math.max(1, Math.min(10, Number(replayState.headTopK || 5)));
          function fmtNumber(value, digits) {
            if (value === null || value === undefined || value === "") return "N/A";
            const num = Number(value);
            if (!Number.isFinite(num)) return "N/A";
            return num.toFixed(digits);
          }
          function fmtPercent(value, digits) {
            if (value === null || value === undefined || value === "") return "N/A";
            const num = Number(value);
            if (!Number.isFinite(num)) return "N/A";
            return (num * 100).toFixed(digits) + "%";
          }
          function telemetryHeadState(stepRow, headName) {
            const heads = (stepRow && stepRow.telemetry_heads && typeof stepRow.telemetry_heads === "object")
              ? stepRow.telemetry_heads
              : {};
            const h = (heads && heads[headName] && typeof heads[headName] === "object") ? heads[headName] : {};
            return {
              status: String(h.status || "unknown"),
              reason: String(h.reason || ""),
            };
          }
          function coverageBadge(stepRow, headName) {
            const hs = telemetryHeadState(stepRow, headName);
            let color = "#94a3b8";
            if (hs.status === "complete") color = "#22c55e";
            else if (hs.status === "partial") color = "#f59e0b";
            else if (hs.status === "none") color = "#ef4444";
            const reason = hs.reason ? (" - " + hs.reason) : "";
            return '<span style="display:inline-block;padding:1px 6px;border:1px solid #334155;border-radius:999px;color:' + color + ';font-size:11px;">' + esc(hs.status + reason) + '</span>';
          }
          const policyActs = Array.isArray(stepRow.policy_top_actions) ? stepRow.policy_top_actions : [];
          const policyProbs = Array.isArray(stepRow.policy_top_probs) ? stepRow.policy_top_probs : [];
          const policyRows = [];
          for (let i = 0; i < Math.min(topK, policyActs.length, policyProbs.length); i += 1) {
            policyRows.push([String(policyActs[i] || ""), fmtPercent(policyProbs[i], 1)]);
          }
          const latentIdx = Array.isArray(stepRow.latent_top_indices) ? stepRow.latent_top_indices : [];
          const latentVals = Array.isArray(stepRow.latent_top_values) ? stepRow.latent_top_values : [];
          const latentRows = [];
          for (let i = 0; i < Math.min(topK, latentIdx.length, latentVals.length); i += 1) {
            latentRows.push([String(latentIdx[i]), Number(latentVals[i] || 0).toFixed(4)]);
          }
          function tableRows(rows, emptyMsg) {
            if (!rows.length) {
              return '<tr><td colspan="2" style="border:1px solid #334155;padding:6px;" class="muted">' + esc(emptyMsg) + '</td></tr>';
            }
            return rows.map(function (r) {
              return '<tr><td style="border:1px solid #334155;padding:6px;">' + esc(String(r[0])) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(r[1])) + '</td></tr>';
            }).join("");
          }
          function headCard(title, summary, tableTitleA, tableTitleB, rows, emptyMsg, headName) {
            return '<div style="border:1px solid #334155;border-radius:8px;background:#0b1220;padding:8px;">' +
              '<div style="font-weight:700;margin-bottom:6px;">' + esc(title) + ' ' + coverageBadge(stepRow, headName) + '</div>' +
              '<div class="muted" style="margin-bottom:6px;">' + esc(summary) + '</div>' +
              '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
                '<th style="border:1px solid #334155;padding:6px;">' + esc(tableTitleA) + '</th>' +
                '<th style="border:1px solid #334155;padding:6px;">' + esc(tableTitleB) + '</th>' +
              '</tr></thead><tbody>' + tableRows(rows, emptyMsg) + '</tbody></table>' +
            '</div>';
          }
          const covStatus = String(stepRow.telemetry_coverage_status || "unknown");
          const covReason = String(stepRow.telemetry_coverage_reason || "");
          let html = '<div class="muted">Head top-k=' + esc(String(topK)) + ' | coverage=' + esc(covStatus + (covReason ? (" (" + covReason + ")") : "")) + '</div>';
          html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px;">';
          html += headCard("Policy Head", headSummaryPolicy(stepRow), "action_id", "prob", policyRows, "No policy distribution available.", "policy");
          html += headCard(
            "Value Head",
            headSummaryValue(stepRow),
            "signal",
            "value",
            [["predicted_value_root", fmtNumber(stepRow.predicted_value_root, 4)]],
            "No value signal.",
            "value"
          );
          html += headCard(
            "Reward Head",
            headSummaryReward(stepRow),
            "signal",
            "value",
            [["dynamics_pred_reward", fmtNumber(stepRow.dynamics_pred_reward, 4)]],
            "No reward signal.",
            "reward"
          );
          html += headCard(
            "Objective Head",
            headSummaryObjective(stepRow),
            "metric",
            "value",
            [
              ["objective_had_opportunity", String(Number(stepRow.objective_had_opportunity || 0))],
              ["objective_min_dist_before", fmtNumber(stepRow.objective_min_dist_before, 3)],
              ["objective_min_dist_after", fmtNumber(stepRow.objective_min_dist_after, 3)],
              ["objective_progress_delta", fmtNumber(stepRow.objective_progress_delta, 3)],
              ["objective_converted", String(Number(stepRow.objective_converted || 0))],
              ["objective_best_vp_id", String(stepRow.objective_best_vp_id || "N/A")]
            ],
            "No objective metrics.",
            "objective"
          );
          html += headCard("Consistency Head", headSummaryConsistency(stepRow), "latent_idx", "|activation|", latentRows, "No latent ranking available.", "consistency");
          html += headCard(
            "MCTS Diagnostics",
            headSummaryMcts(stepRow),
            "metric",
            "value",
            [
              ["chosen_action_prob", fmtPercent(stepRow.chosen_action_prob, 1)],
              ["mcts_margin", fmtNumber(stepRow.mcts_margin, 4)],
              ["mcts_entropy", fmtNumber(stepRow.mcts_entropy, 4)],
              ["mcts_total_visits", fmtNumber(stepRow.mcts_total_visits, 0)]
            ],
            "No MCTS diagnostics.",
            "mcts"
          );
          html += '</div>';
          host.innerHTML = html;
        }
        function renderDecisionInfluence(stepRow, transitions) {
          const host = document.getElementById("replayDecisionInfluenceHost");
          if (!host) return;
          if (!stepRow || typeof stepRow !== "object") {
            host.innerHTML = '<div class="muted">No decision influence data for this step.</div>';
            return;
          }
          const rows = Array.isArray(transitions) ? transitions : [];
          const safeNum = function (value) {
            if (value === null || value === undefined || value === "") return null;
            const n = Number(value);
            return Number.isFinite(n) ? n : null;
          };
          const fmtNum = function (value, digits) {
            const n = safeNum(value);
            return n === null ? "N/A" : n.toFixed(digits);
          };
          const fmtPct = function (value, digits) {
            const n = safeNum(value);
            return n === null ? "N/A" : ((n * 100).toFixed(digits) + "%");
          };
          const coverageState = function (parts) {
            const present = (Array.isArray(parts) ? parts : []).filter(Boolean).length;
            const total = Math.max(1, (Array.isArray(parts) ? parts : []).length);
            if (present <= 0) return "none";
            if (present >= total) return "complete";
            return "partial";
          };
          const inferLegalTypes = function (row) {
            const direct = Array.isArray(row.legal_action_types) ? row.legal_action_types : [];
            if (direct.length) return direct.map(function (x) { return String(x || ""); }).filter(Boolean);
            const acts = Array.isArray(row.policy_top_actions) ? row.policy_top_actions : [];
            const kinds = {};
            for (const aid of acts) {
              const kind = String(aid || "").split(":")[0];
              if (kind) kinds[kind] = true;
            }
            return Object.keys(kinds).sort();
          };
          const policyTopAction = String(stepRow.policy_top_action || (((Array.isArray(stepRow.policy_top_actions) ? stepRow.policy_top_actions : [])[0]) || ""));
          const finalAction = String(stepRow.mcts_chosen_action || stepRow.action_id || "");
          const overriddenRaw = stepRow.policy_overridden_by_mcts;
          const overridden = overriddenRaw === null || overriddenRaw === undefined || overriddenRaw === ""
            ? (policyTopAction && finalAction ? (policyTopAction !== finalAction) : null)
            : (Number(overriddenRaw) > 0);
          const legalTypes = inferLegalTypes(stepRow);
          const legalCountRaw = safeNum(stepRow.legal_action_count);
          const legalCount = legalCountRaw === null
            ? ((Array.isArray(stepRow.policy_top_actions) && stepRow.policy_top_actions.length) ? stepRow.policy_top_actions.length : null)
            : legalCountRaw;
          const objectiveOpp = safeNum(stepRow.objective_had_opportunity);
          const objectiveConverted = safeNum(stepRow.objective_converted);
          const objectiveProgress = safeNum(stepRow.objective_progress_delta);
          const mctsDominanceScore = Math.max(safeNum(stepRow.chosen_action_prob) || 0, safeNum(stepRow.mcts_margin) || 0);
          const policyDominanceScore = safeNum((Array.isArray(stepRow.policy_top_probs) ? stepRow.policy_top_probs[0] : null)) || 0;
          const objectiveDominanceScore = Math.max((objectiveOpp || 0) * 0.35, Math.max(0, objectiveProgress || 0) * 0.6, (objectiveConverted || 0) * 1.0);
          // Transparent heuristics for attribution:
          // - mcts-dominant: explicit policy override, or strong search confidence/margin.
          // - objective-dominant: objective opportunity converted, or meaningful objective progress.
          // - policy-dominant: no override and high top-1 policy confidence.
          let dominantLabel = "policy-dominant";
          if (overridden === true || mctsDominanceScore >= 0.65) dominantLabel = "mcts-dominant";
          else if ((objectiveConverted || 0) > 0 || (objectiveProgress || 0) >= 0.75) dominantLabel = "objective-dominant";
          else if (policyDominanceScore >= 0.55) dominantLabel = "policy-dominant";
          else if (objectiveDominanceScore > policyDominanceScore) dominantLabel = "objective-dominant";
          const partsPresent = [
            legalCount !== null || legalTypes.length > 0,
            policyTopAction || finalAction,
            safeNum(stepRow.predicted_value_root) !== null || safeNum(stepRow.dynamics_pred_reward) !== null || objectiveOpp !== null,
            safeNum(stepRow.mcts_total_visits) !== null || safeNum(stepRow.mcts_margin) !== null || safeNum(stepRow.mcts_entropy) !== null,
            safeNum(stepRow.reward) !== null || objectiveProgress !== null || safeNum(stepRow.damage_dealt) !== null || safeNum(stepRow.kills_dealt) !== null,
          ];
          const stepCoverage = coverageState(partsPresent);
          const coverageColor = stepCoverage === "complete" ? "#22c55e" : (stepCoverage === "partial" ? "#f59e0b" : "#ef4444");
          let opportunities = 0;
          let converted = 0;
          let overrides = 0;
          let comparable = 0;
          const dominance = { policy: 0, objective: 0, mcts: 0 };
          for (const row of rows) {
            if (!row || typeof row !== "object") continue;
            const rowTopAction = String(row.policy_top_action || (((Array.isArray(row.policy_top_actions) ? row.policy_top_actions : [])[0]) || ""));
            const rowFinalAction = String(row.mcts_chosen_action || row.action_id || "");
            const rowOverrideRaw = row.policy_overridden_by_mcts;
            const rowOverride = rowOverrideRaw === null || rowOverrideRaw === undefined || rowOverrideRaw === ""
              ? (rowTopAction && rowFinalAction ? (rowTopAction !== rowFinalAction) : null)
              : (Number(rowOverrideRaw) > 0);
            if (rowOverride !== null) {
              comparable += 1;
              if (rowOverride) overrides += 1;
            }
            const rowOpp = safeNum(row.objective_had_opportunity);
            const rowConv = safeNum(row.objective_converted);
            const rowObjProg = safeNum(row.objective_progress_delta);
            if ((rowOpp || 0) > 0) opportunities += 1;
            if ((rowConv || 0) > 0) converted += 1;
            const rowMctsScore = Math.max(safeNum(row.chosen_action_prob) || 0, safeNum(row.mcts_margin) || 0);
            const rowPolicyScore = safeNum((Array.isArray(row.policy_top_probs) ? row.policy_top_probs[0] : null)) || 0;
            let rowDom = "policy";
            if (rowOverride === true || rowMctsScore >= 0.65) rowDom = "mcts";
            else if ((rowConv || 0) > 0 || (rowObjProg || 0) >= 0.75) rowDom = "objective";
            else if (rowPolicyScore >= 0.55) rowDom = "policy";
            else if (Math.max((rowOpp || 0) * 0.35, Math.max(0, rowObjProg || 0) * 0.6, (rowConv || 0) * 1.0) > rowPolicyScore) rowDom = "objective";
            dominance[rowDom] += 1;
          }
          const episodeCoverage = coverageState([
            comparable > 0,
            opportunities > 0 || converted > 0,
            rows.length > 0,
          ]);
          const pipelineRows = [
            ["legal actions context", (legalCount === null ? "N/A" : String(Math.round(legalCount))) + " | types=" + (legalTypes.length ? legalTypes.join(",") : "N/A")],
            ["policy top-k", policyTopAction ? (policyTopAction + " | top1=" + fmtPct((Array.isArray(stepRow.policy_top_probs) ? stepRow.policy_top_probs[0] : null), 1)) : "N/A"],
            ["value/reward/objective/consistency", "value=" + fmtNum(stepRow.predicted_value_root, 3) + " | reward=" + fmtNum(stepRow.dynamics_pred_reward, 3) + " | obj_dist=" + fmtNum(stepRow.objective_min_dist_before, 3) + "->" + fmtNum(stepRow.objective_min_dist_after, 3) + " | obj_prog=" + fmtNum(objectiveProgress, 3) + " | cons_l2=" + fmtNum(stepRow.dynamics_delta_l2, 3)],
            ["opportunity vp weighting", "fire_no_prog=" + fmtNum(stepRow.opportunity_fire_no_progress, 3) + " | skip_preserve=" + fmtNum(stepRow.opportunity_skip_capture_preserve, 3) + " | label=" + String(stepRow.opportunity_vp_weighting_label || "N/A")],
            ["mcts metrics", "visits=" + fmtNum(stepRow.mcts_total_visits, 0) + " | margin=" + fmtNum(stepRow.mcts_margin, 3) + " | entropy=" + fmtNum(stepRow.mcts_entropy, 3) + " | chosen_prob=" + fmtPct(stepRow.chosen_action_prob, 1)],
            ["final action", finalAction || "N/A"],
            ["step outcome", "reward=" + fmtNum(stepRow.reward, 3) + " | obj_prog=" + fmtNum(objectiveProgress, 3) + " | dmg=" + fmtNum(stepRow.damage_dealt, 3) + " | kills=" + fmtNum(stepRow.kills_dealt, 0)],
          ];
          const episodeRows = [
            ["mcts override rate", (comparable > 0) ? ((100.0 * overrides / comparable).toFixed(1) + "% (" + String(overrides) + "/" + String(comparable) + ")") : "N/A"],
            ["override sample quality", comparable >= 100 ? "OK (>=100 comparable steps)" : ("WARN low sample (" + String(comparable) + " comparable steps)")],
            ["override diagnostics", (
              comparable <= 0
                ? "No comparable steps (missing policy_top_action or chosen action)"
                : (overrides > 0
                  ? "Override behavior observed"
                  : "0 overrides observed; may be real high-consensus policy/MCTS or low-ambiguity sample")
            )],
            ["objective opportunity rate", rows.length ? ((100.0 * opportunities / rows.length).toFixed(1) + "% (" + String(opportunities) + "/" + String(rows.length) + ")") : "N/A"],
            ["objective conversion on opportunities", opportunities > 0 ? ((100.0 * converted / opportunities).toFixed(1) + "% (" + String(converted) + "/" + String(opportunities) + ")") : "N/A"],
            ["dominance distribution", rows.length ? ("policy=" + ((100.0 * dominance.policy / rows.length).toFixed(1)) + "% | objective=" + ((100.0 * dominance.objective / rows.length).toFixed(1)) + "% | mcts=" + ((100.0 * dominance.mcts / rows.length).toFixed(1)) + "%") : "N/A"],
          ];
          const whyBlock = (stepRow.why_action_vs_vp && typeof stepRow.why_action_vs_vp === "object") ? stepRow.why_action_vs_vp : {};
          const whyTopK = Math.max(1, Math.min(10, Number(whyBlock.top_k || replayState.headTopK || 5)));
          const candidateRowsRaw = Array.isArray(whyBlock.candidate_actions) ? whyBlock.candidate_actions : (Array.isArray(stepRow.mcts_action_candidates) ? stepRow.mcts_action_candidates : []);
          const candidateRows = candidateRowsRaw.slice(0, whyTopK);
          const chosenActionWhy = String(whyBlock.chosen_action_id || finalAction || "");
          const vpBestActionWhy = String(whyBlock.vp_best_action_id || "");
          const deltaScoreWhy = safeNum(whyBlock.delta_score);
          const whyShortText = String(stepRow.why_action_vs_vp_text || whyBlock.explanation || "N/A");
          const whyComponents = Array.isArray(whyBlock.score_components_priority) ? whyBlock.score_components_priority : [];
          const whyRows = candidateRows.map(function (c) {
            const actionId = String((c && c.action_id) || "");
            const badges = [];
            if (actionId && actionId === chosenActionWhy) badges.push("chosen");
            if (actionId && actionId === vpBestActionWhy) badges.push("vp-best");
            return [
              (actionId || "N/A") + (badges.length ? (" [" + badges.join(", ") + "]") : ""),
              "prior=" + fmtNum(c ? c.policy_prior : null, 3) +
              " | Q=" + fmtNum(c ? c.q_estimate : null, 3) +
              " | reward=" + fmtNum(c ? c.reward_estimate : null, 3) +
              " | U=" + fmtNum(c ? c.exploration_bonus_u : null, 3) +
              " | score=" + fmtNum(c ? c.final_score : null, 3) +
              " | vp_prog=" + fmtNum(c ? c.vp_progress_delta : null, 3)
            ];
          });
          const whySummaryRows = [
            ["chosen_action", chosenActionWhy || "N/A"],
            ["vp_best_action", vpBestActionWhy || "N/A"],
            ["delta_score (chosen - vp_best)", deltaScoreWhy === null ? "N/A" : deltaScoreWhy.toFixed(4)],
            ["dominant components", whyComponents.length ? whyComponents.join(", ") : "N/A"],
            ["opportunity_vp_weighting_label", String(stepRow.opportunity_vp_weighting_label || "N/A")],
            ["opportunity_fire_no_progress", fmtNum(stepRow.opportunity_fire_no_progress, 3)],
            ["opportunity_skip_capture_preserve", fmtNum(stepRow.opportunity_skip_capture_preserve, 3)],
            ["step explanation", whyShortText || "N/A"],
          ];
          const tableHtml = function (rowsIn, emptyMsg) {
            if (!rowsIn.length) return '<tr><td colspan="2" style="border:1px solid #334155;padding:6px;" class="muted">' + esc(emptyMsg) + '</td></tr>';
            return rowsIn.map(function (r) {
              return '<tr><td style="border:1px solid #334155;padding:6px;width:38%;">' + esc(String(r[0])) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(r[1])) + '</td></tr>';
            }).join("");
          };
          host.innerHTML =
            '<div class="muted" style="margin-bottom:6px;">' +
            'step_coverage=<span style="color:' + coverageColor + ';">' + esc(stepCoverage) + '</span>' +
            ' | episode_coverage=' + esc(episodeCoverage) +
            ' | step_dominance=' + esc(dominantLabel) +
            '</div>' +
            '<div class="muted" style="margin-bottom:4px;">Pipeline by step</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">component</th>' +
              '<th style="border:1px solid #334155;padding:6px;">signal</th>' +
            '</tr></thead><tbody>' + tableHtml(pipelineRows, "No step data.") + '</tbody></table>' +
            '<div class="muted" style="margin-bottom:4px;">Why this action vs VP</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">focus</th>' +
              '<th style="border:1px solid #334155;padding:6px;">detail</th>' +
            '</tr></thead><tbody>' + tableHtml(whySummaryRows, "No chosen vs VP summary.") + '</tbody></table>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:8px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">candidate action</th>' +
              '<th style="border:1px solid #334155;padding:6px;">score breakdown (top-k=' + esc(String(whyTopK)) + ')</th>' +
            '</tr></thead><tbody>' + tableHtml(whyRows, "No candidate breakdown available (legacy run or missing telemetry).") + '</tbody></table>' +
            '<div class="muted" style="margin-bottom:4px;">Episode aggregation</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">metric</th>' +
              '<th style="border:1px solid #334155;padding:6px;">value</th>' +
            '</tr></thead><tbody>' + tableHtml(episodeRows, "No episode aggregation available.") + '</tbody></table>';
        }
        function drawReplay() {
          const epMeta = Array.isArray(replayState.payload && replayState.payload.episodes_meta) ? replayState.payload.episodes_meta : [];
          const epSel = document.getElementById("replayEpisodeSelect");
          if (epSel) {
            epSel.innerHTML = epMeta.map(e => `<option value="${esc(String(e.episode_index || 0))}" ${Number(e.episode_index||0)===Number(replayState.episodeIndex||0)?"selected":""}>ep ${esc(String(e.episode_index||0))} seed ${esc(String(e.seed||""))}</option>`).join("");
          }
          const transitions = Array.isArray(replayState.payload && replayState.payload.transitions) ? replayState.payload.transitions : [];
          const unitOptions = buildReplayUnitCatalog(transitions);
          replayState.knownUnits = unitOptions;
          if (
            replayState.unitFilter !== "__all__" &&
            !unitOptions.some(function (u) { return String((u && u.unit_id) || "") === String(replayState.unitFilter || ""); })
          ) {
            replayState.unitFilter = "__all__";
          }
          renderReplayUnitFilter(unitOptions);
          const maxStep = Math.max(0, transitions.length - 1);
          replayState.step = Math.max(0, Math.min(maxStep, Number(replayState.step || 0)));
          const stepRow = transitions[replayState.step] || null;
          const range = document.getElementById("replayStepRange");
          if (range) {
            range.max = String(maxStep);
            range.value = String(replayState.step);
          }
          const stepLabel = document.getElementById("replayStepLabel");
          if (stepLabel) stepLabel.textContent = "step " + String(replayState.step) + "/" + String(maxStep);
          const headTopKInput = document.getElementById("replayHeadTopKInput");
          if (headTopKInput) {
            const headTopK = Math.max(1, Math.min(10, Number(replayState.headTopK || 5)));
            replayState.headTopK = headTopK;
            headTopKInput.value = String(headTopK);
          }
          const summary = document.getElementById("replaySummary");
          if (summary) {
            const src = replayState.payload || {};
            summary.innerHTML =
              "<div><span>Run:</span> <b>" + esc(String(src.run_id || "")) + "</b></div>" +
              "<div><span>Eval:</span> <b>" + esc(String(replayState.evalId || "")) + "</b></div>" +
              "<div><span>Scenario:</span> <b>" + esc(String(src.scenario_id || "")) + "</b></div>" +
              "<div><span>Transitions:</span> <b>" + esc(String(transitions.length || 0)) + "</b></div>";
          }
          const details = document.getElementById("replayStepDetail");
          if (details) {
            if (!stepRow) {
              details.innerHTML = '<div class="muted">No replay loaded.</div>';
            } else {
              const tq = (stepRow.target_q === undefined || stepRow.target_q === null) ? "-" : String(stepRow.target_q);
              const tr = (stepRow.target_r === undefined || stepRow.target_r === null) ? "-" : String(stepRow.target_r);
              const targetQr = tq + "," + tr;
              const dmgKills = Number(stepRow.damage_dealt || 0).toFixed(3) + " / " + Number(stepRow.kills_dealt || 0).toFixed(0);
              const coverageTxt = String(stepRow.telemetry_coverage_status || "unknown")
                + (String(stepRow.telemetry_coverage_reason || "").trim() ? (" (" + String(stepRow.telemetry_coverage_reason || "").trim() + ")") : "");
              details.innerHTML =
                '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
                  '<tbody>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">to_play</td><td style="border:1px solid #334155;padding:6px;">' + esc(stepRow.to_play) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">action_id</td><td style="border:1px solid #334155;padding:6px;">' + esc(stepRow.action_id) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">unit_id</td><td style="border:1px solid #334155;padding:6px;">' + esc(stepRow.unit_id) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">target_qr</td><td style="border:1px solid #334155;padding:6px;">' + esc(targetQr) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">reward</td><td style="border:1px solid #334155;padding:6px;">' + esc(Number(stepRow.reward || 0).toFixed(4)) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">damage / kills</td><td style="border:1px solid #334155;padding:6px;">' + esc(dmgKills) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">telemetry_coverage</td><td style="border:1px solid #334155;padding:6px;">' + esc(coverageTxt) + '</td></tr>' +
                  '</tbody>' +
                '</table>';
            }
          }
          renderReplayHeadDiagnostics(stepRow);
          renderDecisionInfluence(stepRow, transitions);
          const canvas = document.getElementById("replayCanvas");
          if (canvas && canvas.getContext) {
            const ctx = canvas.getContext("2d");
            if (ctx) {
              const dpr = Math.max(1, window.devicePixelRatio || 1);
              const rect = canvas.getBoundingClientRect();
              const cssW = Math.max(640, Math.floor(rect.width || canvas.clientWidth || 980));
              const cssH = Math.max(280, Math.floor(rect.height || canvas.clientHeight || (cssW * (9 / 16))));
              // First visit can happen while tab is hidden, producing unstable geometry.
              // Retry a few frames until layout settles, then draw once with final size.
              if ((rect.width || 0) < 40 || (rect.height || 0) < 40) {
                if (replayState.pendingLayoutRetries < 12) {
                  replayState.pendingLayoutRetries += 1;
                  requestAnimationFrame(() => drawReplay());
                } else {
                  replayState.pendingLayoutRetries = 0;
                }
                return;
              }
              replayState.pendingLayoutRetries = 0;
              if (canvas.width !== Math.floor(cssW * dpr) || canvas.height !== Math.floor(cssH * dpr)) {
                canvas.width = Math.floor(cssW * dpr);
                canvas.height = Math.floor(cssH * dpr);
              }
              ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
              ctx.clearRect(0, 0, cssW, cssH);
              ctx.fillStyle = "#0b0f18";
              ctx.fillRect(0, 0, cssW, cssH);
              const allStepUnits = Array.isArray(stepRow && stepRow.units) ? stepRow.units : [];
              const selectedUnitId = String(replayState.unitFilter || "__all__");
              const units = selectedUnitId === "__all__"
                ? allStepUnits
                : allStepUnits.filter(function (u) { return String((u && u.unit_id) || "") === selectedUnitId; });
              const unitCoords = [];
              const qs = [];
              const rs = [];
              for (const u of units) {
                const uq = Number(u && u.q);
                const ur = Number(u && u.r);
                if (!Number.isFinite(uq) || !Number.isFinite(ur)) continue;
                const uc = Object.assign({}, u, { q: Number(u.q || 0), r: Number(u.r || 0) });
                unitCoords.push(uc);
                qs.push(Number(uc.q || 0));
                rs.push(Number(uc.r || 0));
              }
              const tQ = Number.isFinite(Number(stepRow && stepRow.target_q)) ? Number(stepRow.target_q) : null;
              const tR = Number.isFinite(Number(stepRow && stepRow.target_r)) ? Number(stepRow.target_r) : null;
              if (tQ !== null && tR !== null) { qs.push(tQ); rs.push(tR); }
              const overlay = (replayState.payload && replayState.payload.scenario_overlay) || {};
              const shape = Array.isArray(overlay.shape) ? overlay.shape : [];
              const vpHexes = Array.isArray(overlay.vp_hexes) ? overlay.vp_hexes : [];
              const mapCellsOverlay = Array.isArray(overlay.map_cells) ? overlay.map_cells : [];
              const minQ = (qs.length ? Math.min(...qs) : 0) - 2;
              const maxQ = (qs.length ? Math.max(...qs) : 8) + 2;
              const minR = (rs.length ? Math.min(...rs) : 0) - 2;
              const maxR = (rs.length ? Math.max(...rs) : 8) + 2;
              const baseCells = [];
              if (mapCellsOverlay.length > 0) {
                for (const c of mapCellsOverlay) {
                  const q = Number(c && c.q);
                  const r = Number(c && c.r);
                  if (Number.isFinite(q) && Number.isFinite(r)) baseCells.push({ q, r });
                }
              } else if (shape.length >= 2 && Number(shape[0]) > 0 && Number(shape[1]) > 0) {
                const wCells = Math.max(1, Number(shape[0]));
                const hCells = Math.max(1, Number(shape[1]));
                for (let r = 0; r < hCells; r += 1) {
                  for (let q = 0; q < wCells; q += 1) {
                    baseCells.push({ q, r });
                  }
                }
              } else {
                for (let q = minQ; q <= maxQ; q += 1) {
                  for (let r = minR; r <= maxR; r += 1) {
                    baseCells.push({ q, r });
                  }
                }
              }
              const proj = makeProjection(baseCells, cssW, cssH, 8);
              const size = proj.hexRadius;
              for (const c of baseCells) {
                const p = proj.toPixel(c.q, c.r);
                drawHex(ctx, p.x, p.y, size, "#263244", "rgba(15,23,42,0.35)");
              }
              const points = [];
              for (const u of unitCoords) {
                const px = proj.toPixel(u.q, u.r);
                points.push(Object.assign({}, u, px));
              }
              for (const p of points) {
                drawHex(ctx, p.x, p.y, size, "#334155", "rgba(15,23,42,0.45)");
              }
              for (const u of points) {
                const isIT = String(u.side || "").toUpperCase() === "IT";
                ctx.beginPath();
                ctx.arc(u.x, u.y, Math.max(4, size * 0.42), 0, Math.PI * 2);
                ctx.fillStyle = isIT ? "#f97316" : "#38bdf8";
                if (!Boolean(u.alive)) ctx.fillStyle = "#64748b";
                ctx.fill();
                ctx.strokeStyle = "#0f172a";
                ctx.lineWidth = 1.2;
                ctx.stroke();
                ctx.fillStyle = "#e2e8f0";
                ctx.font = String(Math.max(9, Math.floor(size * 0.58))) + "px sans-serif";
                ctx.fillText(String(u.unit_id || ""), u.x + size * 0.65, u.y + 3);
              }
              if (
                Number.isFinite(Number(stepRow && stepRow.target_q)) &&
                Number.isFinite(Number(stepRow && stepRow.target_r)) &&
                Number(((stepRow && stepRow.attack_distance_mean) === undefined || (stepRow && stepRow.attack_distance_mean) === null) ? -1 : (stepRow && stepRow.attack_distance_mean)) >= 0
              ) {
                const t = proj.toPixel(Number(stepRow.target_q), Number(stepRow.target_r));
                drawHex(ctx, t.x, t.y, size * 1.08, "#facc15", "rgba(250,204,21,0.10)");
              }
              for (const vp of vpHexes) {
                const q = Number(vp && vp.q);
                const r = Number(vp && vp.r);
                if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
                const p = proj.toPixel(q, r);
                const owner = String((vp && vp.initial_owner) || "").toUpperCase();
                const ownerColor = owner === "IT" ? "#fb923c" : (owner === "US" ? "#38bdf8" : "#facc15");
                drawHex(ctx, p.x, p.y, size * 1.12, "#facc15", "rgba(250,204,21,0.06)");
                ctx.beginPath();
                ctx.arc(p.x, p.y, Math.max(3, size * 0.22), 0, Math.PI * 2);
                ctx.fillStyle = ownerColor;
                ctx.fill();
                ctx.strokeStyle = "#0f172a";
                ctx.lineWidth = 1;
                ctx.stroke();
              }
            }
          }
          const unitsHost = document.getElementById("replayUnitsHost");
          if (unitsHost) {
            const allStepUnits = Array.isArray(stepRow && stepRow.units) ? stepRow.units : [];
            const selectedUnitId = String(replayState.unitFilter || "__all__");
            const units = selectedUnitId === "__all__"
              ? allStepUnits
              : allStepUnits.filter(function (u) { return String((u && u.unit_id) || "") === selectedUnitId; });
            let unitsHtml = '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
              '<thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">side</th>' +
              '<th style="border:1px solid #334155;padding:6px;">unit_id</th>' +
              '<th style="border:1px solid #334155;padding:6px;">unit</th>' +
              '<th style="border:1px solid #334155;padding:6px;">hex</th>' +
              '<th style="border:1px solid #334155;padding:6px;">hp</th>' +
              '<th style="border:1px solid #334155;padding:6px;">alive</th>' +
              '</tr></thead><tbody>';
            if (!units.length) {
              unitsHtml += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No units for selected filter.</td></tr>';
            } else {
              for (const u of units) {
                const hex = String(u.q) + "," + String(u.r);
                const unitWithId = String(u.unit_id || "") + " - " + String(u.unit_label || u.unit_key || "");
                unitsHtml += '<tr>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(u.side) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(u.unit_id) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(unitWithId) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(hex) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(u.hp || 0).toFixed(1)) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(Boolean(u.alive) ? "yes" : "no") + '</td>' +
                  '</tr>';
              }
            }
            unitsHtml += '</tbody></table>';
            unitsHost.innerHTML = unitsHtml;
          }
        }
        const evalSelect = document.getElementById("replayEvalSelect");
        if (evalSelect) evalSelect.onchange = async () => {
          replayState.evalId = String(evalSelect.value || "");
          replayState.episodeIndex = 0;
          await loadReplay();
          loadReplayLog();
        };
        const epSelect = document.getElementById("replayEpisodeSelect");
        if (epSelect) epSelect.onchange = async () => {
          replayState.episodeIndex = Math.max(0, Number(epSelect.value || 0));
          await loadReplay();
          loadReplayLog();
        };
        const loadBtn = document.getElementById("replayLoadBtn");
        if (loadBtn) loadBtn.onclick = async () => {
          await loadReplay();
          loadReplayLog();
        };
        const replayRangeInput = document.getElementById("replayStepRange");
        if (replayRangeInput) replayRangeInput.oninput = () => {
          replayState.step = Math.max(0, Number(replayRangeInput.value || 0));
          setReplayStepNavFeedback("");
          drawReplay();
          loadReplayLog();
        };
        const prevStepBtn = document.getElementById("replayPrevStepBtn");
        if (prevStepBtn) prevStepBtn.onclick = () => moveReplayStep(-1);
        const nextStepBtn = document.getElementById("replayNextStepBtn");
        if (nextStepBtn) nextStepBtn.onclick = () => moveReplayStep(1);
        const playBtn = document.getElementById("replayPlayBtn");
        if (playBtn) playBtn.onclick = () => {
          stopReplayTimer();
          replayState.playing = true;
          const speedInput = document.getElementById("replaySpeedInput");
          const speed = Math.max(40, Math.min(2000, Number((((speedInput || {}).value) || speedMs))));
          replayState.timer = setInterval(() => {
            const transitions = Array.isArray(replayState.payload && replayState.payload.transitions) ? replayState.payload.transitions : [];
            const maxStep = Math.max(0, transitions.length - 1);
            const moved = moveReplayStep(1);
            if (!moved || replayState.step >= maxStep) stopReplayTimer();
          }, speed);
        };
        const pauseBtn = document.getElementById("replayPauseBtn");
        if (pauseBtn) pauseBtn.onclick = () => stopReplayTimer();
        const replayHeadTopKInput = document.getElementById("replayHeadTopKInput");
        if (replayHeadTopKInput) replayHeadTopKInput.onchange = () => {
          replayState.headTopK = Math.max(1, Math.min(10, Number(replayHeadTopKInput.value || 5)));
          drawReplay();
        };
        window.onkeydown = (ev) => {
          if (activeTab !== "replay") return;
          const transitions = Array.isArray(replayState.payload && replayState.payload.transitions) ? replayState.payload.transitions : [];
          if (ev.key === "ArrowRight") {
            moveReplayStep(1);
          } else if (ev.key === "ArrowLeft") {
            moveReplayStep(-1);
          } else if (ev.key === " ") {
            ev.preventDefault();
            if (replayState.playing) {
              stopReplayTimer();
            } else {
              const pbtn = document.getElementById("replayPlayBtn");
              if (pbtn) pbtn.click();
            }
          }
        };
        window.onresize = () => drawReplay();
        drawReplay();
        setTimeout(() => drawReplay(), 0);
        setTimeout(() => drawReplay(), 60);
        loadReplayLog();
        loadReplay();
        } catch (e) {
          const host = document.getElementById("replayRoot");
          if (host) host.innerHTML = '<div class="muted">Replay render error: ' + esc(String((e && e.message) || e || "unknown")) + '</div>';
        }
      }
      let flowSideSelected = "__all__";
      function _buildFlowDataset(flowRows, flowSide, selectedEvalId, selectedProfile, selectedSide, selectedController) {
        const sidePoolsFor = (row) => [
          row.vp_initial_avg_by_side || {},
          row.vp_final_avg_by_side || {},
          row.vp_net_avg_by_side || {},
          row.vp_gained_avg_by_side || {},
          row.vp_lost_avg_by_side || {},
        ];
        const hasSideFor = (row, side) => sidePoolsFor(row).some(p => Object.prototype.hasOwnProperty.call(p, String(side)));
        const allSidesFor = (row) => [...new Set(sidePoolsFor(row).flatMap(p => Object.keys(p || {})))];
        const resultMatches = (row) => {
          if (selectedProfile !== "__all__" && String(row.matchup_profile || "") !== String(selectedProfile)) return false;
          if (selectedSide !== "__all__") {
            if (!hasSideFor(row, selectedSide)) return false;
            const selectedSideController = sideController(row, selectedSide);
            // Flow is meaningful only for MuZero-controlled side unless controller is explicitly set.
            if (selectedController === "__all__") {
              if (selectedSideController !== "MuZero") return false;
            } else if (selectedSideController !== selectedController) {
              return false;
            }
          }
          if (selectedController !== "__all__") {
            if (selectedSide === "__all__" && !allSidesFor(row).some(s => sideController(row, s) === selectedController)) {
              return false;
            }
          }
          if (flowSide !== "__all__") {
            if (!hasSideFor(row, flowSide)) return false;
            if (sideController(row, flowSide) !== "MuZero") return false;
          }
          return true;
        };

        const resultRows = (rows || [])
          .filter(er => selectedEvalId === "__all__" || String(er.eval_id || "") === String(selectedEvalId))
          .flatMap(er => (Array.isArray(er.results) ? er.results : []).map(r => ({ ...r, eval_id: er.eval_id || "" })))
          .filter(r => String(r.agent_name || "").startsWith("muzero"))
          .filter(resultMatches);

        if (!resultRows.length) {
          return { nodes: [], links: [], summary: "no eval result rows match current filters" };
        }

        const agg = resultRows.reduce((a, row) => {
          const bySide = row.phase_2_9_eval_kpis_by_side || {};
          let k = row.phase_2_9_eval_kpis || {};
          if (flowSide !== "__all__" && bySide && bySide[flowSide]) {
            k = bySide[flowSide] || {};
          } else if (flowSide === "__all__" && bySide && Object.keys(bySide).length > 0) {
            const muSides = Object.keys(bySide).filter(s => sideController(row, s) === "MuZero");
            if (muSides.length > 0) {
              const sumK = {
                reaction_window_count: 0,
                reaction_fire_count: 0,
                reaction_fire_skipped_count: 0,
                melee_attempts: 0,
                converted_rate_near_vp: 0,
                converted_from_progress_rate: 0,
              };
              muSides.forEach(s => {
                const ks = bySide[s] || {};
                sumK.reaction_window_count += Number(ks.reaction_window_count || 0);
                sumK.reaction_fire_count += Number(ks.reaction_fire_count || 0);
                sumK.reaction_fire_skipped_count += Number(ks.reaction_fire_skipped_count || 0);
                sumK.melee_attempts += Number(ks.melee_attempts || 0);
                sumK.converted_rate_near_vp += Number(ks.converted_rate_near_vp || 0);
                sumK.converted_from_progress_rate += Number(ks.converted_from_progress_rate || 0);
              });
              k = sumK;
            }
          }
          const opportunities = Number(k.reaction_window_count || 0);
          const progress = Number(k.melee_attempts || 0);
          // Strict policy: only use explicitly emitted fields; do not infer counts from rates.
          if (!Object.prototype.hasOwnProperty.call(k, "conversions") && !Object.prototype.hasOwnProperty.call(k, "conversions_count")) {
            a.missingColumns.conversions = true;
          }
          if (!Object.prototype.hasOwnProperty.call(k, "stalls") && !Object.prototype.hasOwnProperty.call(k, "no_progress_count")) {
            a.missingColumns.stalls = true;
          }
          if (
            !Object.prototype.hasOwnProperty.call(k, "converted_after_progress") &&
            !Object.prototype.hasOwnProperty.call(k, "converted_after_progress_count")
          ) {
            a.missingColumns.converted_after_progress = true;
          }
          if (
            !Object.prototype.hasOwnProperty.call(k, "converted_without_progress") &&
            !Object.prototype.hasOwnProperty.call(k, "converted_without_progress_count")
          ) {
            a.missingColumns.converted_without_progress = true;
          }
          if (
            !Object.prototype.hasOwnProperty.call(k, "progressed_but_not_converted") &&
            !Object.prototype.hasOwnProperty.call(k, "progressed_but_not_converted_count")
          ) {
            a.missingColumns.progressed_but_not_converted = true;
          }
          if (
            !Object.prototype.hasOwnProperty.call(k, "stalled_and_not_converted") &&
            !Object.prototype.hasOwnProperty.call(k, "stalled_and_not_converted_count")
          ) {
            a.missingColumns.stalled_and_not_converted = true;
          }
          if (!Object.prototype.hasOwnProperty.call(k, "non_progress_actions")) {
            a.missingColumns.non_progress_actions = true;
          }

          const conversions = Number(k.conversions || k.conversions_count || 0);
          const stalls = Number(k.stalls || k.no_progress_count || 0);
          const convertedAfterProgress = Number(
            k.converted_after_progress || k.converted_after_progress_count || 0
          );
          const convertedWithoutProgress = Number(
            k.converted_without_progress || k.converted_without_progress_count || 0
          );
          const progressedButNotConverted = Number(
            k.progressed_but_not_converted || k.progressed_but_not_converted_count || 0
          );
          const stalledAndNotConverted = Number(
            k.stalled_and_not_converted || k.stalled_and_not_converted_count || 0
          );

          a.episodes += Math.max(1, Number(row.episodes || 1));
          a.opportunities += opportunities;
          a.progress_actions += progress;
          a.conversions += conversions;
          a.stalls += stalls;
          a.converted_after_progress += convertedAfterProgress;
          a.converted_without_progress += convertedWithoutProgress;
          a.progressed_but_not_converted += progressedButNotConverted;
          a.stalled_and_not_converted += stalledAndNotConverted;
          a.no_progress_reason_counts.reaction_fire =
            (a.no_progress_reason_counts.reaction_fire || 0) + Number(k.reaction_fire_count || 0);
          a.no_progress_reason_counts.reaction_skip =
            (a.no_progress_reason_counts.reaction_skip || 0) + Number(k.reaction_fire_skipped_count || 0);
          a.no_progress_reason_counts.non_progress_actions =
            (a.no_progress_reason_counts.non_progress_actions || 0) +
            Number(k.non_progress_actions || 0);
          return a;
        }, {
          episodes: 0,
          opportunities: 0,
          progress_actions: 0,
          conversions: 0,
          stalls: 0,
          converted_after_progress: 0,
          converted_without_progress: 0,
          progressed_but_not_converted: 0,
          stalled_and_not_converted: 0,
          no_progress_reason_counts: {},
          missingColumns: {},
        });

        const opportunities = Number(agg.opportunities);
        const progress = Number(agg.progress_actions);
        const conversions = Number(agg.conversions);
        const noProgress = Number(agg.stalls);
        const notConverted = Math.max(0, opportunities - conversions);
        const convertedFromProgress = Number(agg.converted_after_progress);
        const convertedFromNoProgress = Number(agg.converted_without_progress);
        const notConvFromProgress = Number(agg.progressed_but_not_converted);
        const notConvFromNoProgress = Number(agg.stalled_and_not_converted);
        const noProgL1 = Object.fromEntries(
          Object.entries(agg.no_progress_reason_counts || {}).map(([k, v]) => [k, Number(v)])
        );
        const noProgL2 = {};
        const topEntries = (obj, n=2) => Object.entries(obj || {}).sort((a,b)=>Number(b[1]||0)-Number(a[1]||0)).slice(0,n);
        const topL1 = topEntries(noProgL1, 2);
        const topL2 = topEntries(noProgL2, 2);
        const nodes = [
          { id: "opportunity", label: "OPPORTUNITY", value: opportunities, x: 140, y: 170 },
          { id: "progress", label: "PROGRESS", value: progress, x: 380, y: 120 },
          { id: "no_progress", label: "NO PROGRESS", value: noProgress, x: 380, y: 235 },
          { id: "converted", label: "CONVERTED", value: conversions, x: 620, y: 120 },
          { id: "not_converted", label: "NOT CONVERTED", value: notConverted, x: 620, y: 235 },
          { id: "l1_1", label: (topL1[0] ? String(topL1[0][0]) : "l1 cause #1"), value: Number((topL1[0] && topL1[0][1]) || 0), x: 330, y: 360 },
          { id: "l1_2", label: (topL1[1] ? String(topL1[1][0]) : "l1 cause #2"), value: Number((topL1[1] && topL1[1][1]) || 0), x: 470, y: 360 },
          { id: "l2_1", label: (topL2[0] ? String(topL2[0][0]) : "l2 cause #1"), value: Number((topL2[0] && topL2[0][1]) || 0), x: 620, y: 360 },
          { id: "l2_2", label: (topL2[1] ? String(topL2[1][0]) : "l2 cause #2"), value: Number((topL2[1] && topL2[1][1]) || 0), x: 760, y: 360 },
        ];
        const links = [
          { source: "opportunity", target: "progress", value: progress },
          { source: "opportunity", target: "no_progress", value: noProgress },
          { source: "progress", target: "converted", value: convertedFromProgress },
          { source: "no_progress", target: "converted", value: convertedFromNoProgress },
          { source: "progress", target: "not_converted", value: notConvFromProgress },
          { source: "no_progress", target: "not_converted", value: notConvFromNoProgress },
          { source: "no_progress", target: "l1_1", value: Number((topL1[0] && topL1[0][1]) || 0) },
          { source: "no_progress", target: "l1_2", value: Number((topL1[1] && topL1[1][1]) || 0) },
          { source: "not_converted", target: "l2_1", value: Number((topL2[0] && topL2[0][1]) || 0) },
          { source: "not_converted", target: "l2_2", value: Number((topL2[1] && topL2[1][1]) || 0) },
        ];
        const missingCols = Object.keys(agg.missingColumns || {}).sort();
        const missingNote = missingCols.length
          ? ` missing=[${missingCols.join(",")}]`
          : "";
        return {
          nodes,
          links,
          summary: `source=eval.result_rows rows=${resultRows.length} episodes=${agg.episodes} flow_side=${flowSide} profile=${selectedProfile} side=${selectedSide} controller=${selectedController} strict=explicit_fields_only${missingNote}`,
        };
      }

      function _renderFlowGraph(dataset) {
        const host = document.getElementById("flowGraphHost");
        if (!host) return;
        host.innerHTML = "";
        if (!dataset || !Array.isArray(dataset.nodes) || dataset.nodes.length === 0) {
          host.innerHTML = `<div class="muted" style="padding:12px;">No flow data available for selected eval rows. This graph now uses eval metrics (phase_2_9_eval_kpis).</div>`;
          const summaryEl = document.getElementById("flowSummary");
          if (summaryEl) summaryEl.textContent = (dataset && dataset.summary) ? dataset.summary : "no flow dataset";
          return;
        }
        const width = Math.max(760, host.clientWidth || 760);
        const height = Math.max(420, host.clientHeight || 420);
        const svgns = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(svgns, "svg");
        svg.setAttribute("width", String(width));
        svg.setAttribute("height", String(height));
        svg.style.width = "100%";
        svg.style.height = "100%";
        svg.style.cursor = "grab";
        const world = document.createElementNS(svgns, "g");
        svg.appendChild(world);
        host.appendChild(svg);

        const nodeById = {};
        for (const n of dataset.nodes) nodeById[n.id] = { ...n };
        let transform = { x: 0, y: 0, k: 1 };
        let panState = null;
        let dragNode = null;
        let dragOffset = { x: 0, y: 0 };

        function applyTransform() {
          world.setAttribute("transform", `translate(${transform.x},${transform.y}) scale(${transform.k})`);
        }
        function toWorld(clientX, clientY) {
          const r = svg.getBoundingClientRect();
          const sx = clientX - r.left;
          const sy = clientY - r.top;
          return { x: (sx - transform.x) / transform.k, y: (sy - transform.y) / transform.k };
        }
        function radiusFor(v) {
          const vv = Number(v || 0);
          return Math.max(16, Math.min(44, 16 + Math.sqrt(Math.max(0, vv)) * 2.2));
        }
        function strokeFor(v) {
          return `${Math.max(1, Math.min(8, Math.sqrt(Math.max(0, Number(v || 0))) / 2))}`;
        }
        function render() {
          world.innerHTML = "";
          // links
          for (const lk of dataset.links) {
            const a = nodeById[lk.source];
            const b = nodeById[lk.target];
            if (!a || !b) continue;
            const line = document.createElementNS(svgns, "line");
            line.setAttribute("x1", String(a.x));
            line.setAttribute("y1", String(a.y));
            line.setAttribute("x2", String(b.x));
            line.setAttribute("y2", String(b.y));
            line.setAttribute("stroke", "#64748b");
            line.setAttribute("stroke-width", strokeFor(lk.value));
            line.setAttribute("opacity", "0.9");
            world.appendChild(line);
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            const lbl = document.createElementNS(svgns, "text");
            lbl.setAttribute("x", String(mx));
            lbl.setAttribute("y", String(my - 4));
            lbl.setAttribute("fill", "#93c5fd");
            lbl.setAttribute("font-size", "11");
            lbl.setAttribute("text-anchor", "middle");
            lbl.textContent = `${Number(lk.value || 0).toFixed(1)}`;
            world.appendChild(lbl);
          }
          // nodes
          for (const n of Object.values(nodeById)) {
            const g = document.createElementNS(svgns, "g");
            g.setAttribute("data-node-id", n.id);
            g.style.cursor = "move";
            const c = document.createElementNS(svgns, "circle");
            c.setAttribute("cx", String(n.x));
            c.setAttribute("cy", String(n.y));
            c.setAttribute("r", String(radiusFor(n.value)));
            c.setAttribute("fill", "#1e3a5f");
            c.setAttribute("stroke", "#22d3ee");
            c.setAttribute("stroke-width", "2");
            g.appendChild(c);
            const t1 = document.createElementNS(svgns, "text");
            t1.setAttribute("x", String(n.x));
            t1.setAttribute("y", String(n.y - 4));
            t1.setAttribute("fill", "#e2e8f0");
            t1.setAttribute("font-size", "11");
            t1.setAttribute("text-anchor", "middle");
            t1.textContent = n.label;
            g.appendChild(t1);
            const t2 = document.createElementNS(svgns, "text");
            t2.setAttribute("x", String(n.x));
            t2.setAttribute("y", String(n.y + 12));
            t2.setAttribute("fill", "#fde68a");
            t2.setAttribute("font-size", "12");
            t2.setAttribute("font-weight", "700");
            t2.setAttribute("text-anchor", "middle");
            t2.textContent = Number(n.value || 0).toFixed(1);
            g.appendChild(t2);
            world.appendChild(g);
          }
          applyTransform();
        }

        svg.addEventListener("wheel", (ev) => {
          ev.preventDefault();
          const zoom = ev.deltaY < 0 ? 1.08 : 0.92;
          const p = toWorld(ev.clientX, ev.clientY);
          transform.k = Math.max(0.3, Math.min(3.5, transform.k * zoom));
          const p2x = p.x * transform.k + transform.x;
          const p2y = p.y * transform.k + transform.y;
          transform.x += (ev.clientX - svg.getBoundingClientRect().left) - p2x;
          transform.y += (ev.clientY - svg.getBoundingClientRect().top) - p2y;
          applyTransform();
        }, { passive: false });

        svg.addEventListener("mousedown", (ev) => {
          const target = ev.target;
          const nodeEl = target.closest ? target.closest("[data-node-id]") : null;
          if (nodeEl) {
            const id = nodeEl.getAttribute("data-node-id");
            if (id && nodeById[id]) {
              dragNode = id;
              const p = toWorld(ev.clientX, ev.clientY);
              dragOffset = { x: p.x - nodeById[id].x, y: p.y - nodeById[id].y };
            }
            return;
          }
          panState = { x: ev.clientX, y: ev.clientY, ox: transform.x, oy: transform.y };
          svg.style.cursor = "grabbing";
        });
        window.addEventListener("mousemove", (ev) => {
          if (dragNode) {
            if ((ev.buttons & 1) === 0) {
              dragNode = null;
              return;
            }
            const n = nodeById[dragNode];
            if (!n) return;
            const p = toWorld(ev.clientX, ev.clientY);
            n.x = p.x - dragOffset.x;
            n.y = p.y - dragOffset.y;
            render();
            return;
          }
          if (!panState) return;
          transform.x = panState.ox + (ev.clientX - panState.x);
          transform.y = panState.oy + (ev.clientY - panState.y);
          applyTransform();
        });
        window.addEventListener("mouseup", () => {
          dragNode = null;
          panState = null;
          svg.style.cursor = "grab";
        });

        const resetViewBtn = document.getElementById("flowResetViewBtn");
        if (resetViewBtn) resetViewBtn.onclick = () => {
          transform = { x: 0, y: 0, k: 1 };
          applyTransform();
        };
        const resetLayoutBtn = document.getElementById("flowResetLayoutBtn");
        if (resetLayoutBtn) resetLayoutBtn.onclick = () => {
          for (const n of dataset.nodes) {
            if (nodeById[n.id]) {
              nodeById[n.id].x = n.x;
              nodeById[n.id].y = n.y;
            }
          }
          render();
        };
        const summaryEl = document.getElementById("flowSummary");
        if (summaryEl) summaryEl.textContent = dataset.summary || "";
        render();
      }
      function renderFiltered() {
        return;
      }
      // legacy filter pipeline disabled; simplified filtering now happens inside renderMuzeroVps

    function switchSection(section) {
      activeSection = section;
      const secTrain = el("sectionTrainBtn");
      const secEval = el("sectionEvalBtn");
      const secMeta = el("sectionMetaBtn");
      if (secTrain) secTrain.classList.toggle("active", section === "train");
      if (secEval) secEval.classList.toggle("active", section === "eval");
      if (secMeta) secMeta.classList.toggle("active", section === "meta");
      ["tabTrainDetailBtn", "tabTrainHeadDiagnosticsBtn", "tabObjectiveRewardConfigBtn", "tabMuzeroVpsBtn", "tabHeadDiagnosticsBtn", "tabUnifiedBtn", "tabEvalDecisionsBtn", "tabReplayBtn", "tabOverviewBtn"].forEach(id => {
        const n = el(id);
        if (!n) return;
        const sec = n.getAttribute("data-section");
        n.style.display = (sec === section) ? "" : "none";
      });
      const filtersHost = el("analysisFiltersHost");
      if (filtersHost) filtersHost.style.display = (section === "eval") ? "block" : "none";
      if (section === "train" && activeTab !== "train-detail" && activeTab !== "train-head-diagnostics" && activeTab !== "objective-reward-config") switchTab("train-detail");
      if (section === "eval" && activeTab !== "vps" && activeTab !== "head-diagnostics" && activeTab !== "unified" && activeTab !== "eval-decisions" && activeTab !== "replay") switchTab("vps");
      if (section === "meta" && activeTab !== "overview") switchTab("overview");
    }

    function switchTab(tab) {
      activeTab = tab;
      const tOverviewBtn = el("tabOverviewBtn");
      const tVpsBtn = el("tabMuzeroVpsBtn");
      const tHeadDiagBtn = el("tabHeadDiagnosticsBtn");
      const tUnifiedBtn = el("tabUnifiedBtn");
      const tDecisionsBtn = el("tabEvalDecisionsBtn");
      const tReplayBtn = el("tabReplayBtn");
      const tTrainDetailBtn = el("tabTrainDetailBtn");
      const tTrainHeadDiagBtn = el("tabTrainHeadDiagnosticsBtn");
      const tObjectiveRewardConfigBtn = el("tabObjectiveRewardConfigBtn");
      const pOverview = el("tabOverview");
      const pVps = el("tabMuzeroVps");
      const pHeadDiag = el("tabHeadDiagnostics");
      const pUnified = el("tabUnified");
      const pDecisions = el("tabEvalDecisions");
      const pReplay = el("tabReplay");
      const pTrainDetail = el("tabTrainDetail");
      const pTrainHeadDiag = el("tabTrainHeadDiagnostics");
      const pObjectiveRewardConfig = el("tabObjectiveRewardConfig");
      if (tOverviewBtn) tOverviewBtn.classList.toggle("active", tab === "overview");
      if (tVpsBtn) tVpsBtn.classList.toggle("active", tab === "vps");
      if (tHeadDiagBtn) tHeadDiagBtn.classList.toggle("active", tab === "head-diagnostics");
      if (tUnifiedBtn) tUnifiedBtn.classList.toggle("active", tab === "unified");
      if (tDecisionsBtn) tDecisionsBtn.classList.toggle("active", tab === "eval-decisions");
      if (tReplayBtn) tReplayBtn.classList.toggle("active", tab === "replay");
      if (tTrainDetailBtn) tTrainDetailBtn.classList.toggle("active", tab === "train-detail");
      if (tTrainHeadDiagBtn) tTrainHeadDiagBtn.classList.toggle("active", tab === "train-head-diagnostics");
      if (tObjectiveRewardConfigBtn) tObjectiveRewardConfigBtn.classList.toggle("active", tab === "objective-reward-config");
      if (pOverview) pOverview.classList.toggle("active", tab === "overview");
      if (pVps) pVps.classList.toggle("active", tab === "vps");
      if (pHeadDiag) pHeadDiag.classList.toggle("active", tab === "head-diagnostics");
      if (pUnified) pUnified.classList.toggle("active", tab === "unified");
      if (pDecisions) pDecisions.classList.toggle("active", tab === "eval-decisions");
      if (pReplay) pReplay.classList.toggle("active", tab === "replay");
      if (pTrainDetail) pTrainDetail.classList.toggle("active", tab === "train-detail");
      if (pTrainHeadDiag) pTrainHeadDiag.classList.toggle("active", tab === "train-head-diagnostics");
      if (pObjectiveRewardConfig) pObjectiveRewardConfig.classList.toggle("active", tab === "objective-reward-config");
      if (tab === "objective-reward-config") {
        renderObjectiveRewardConfig();
      }
      if (tab === "replay") {
        setTimeout(() => { try { window.dispatchEvent(new Event("resize")); } catch (_e) {} }, 0);
        setTimeout(() => { try { window.dispatchEvent(new Event("resize")); } catch (_e) {} }, 80);
      }
    }

    function setTrainCollapsed(next) {
      trainCollapsed = !!next;
      const main = document.querySelector(".main");
      if (!main) return;
      main.classList.toggle("train-collapsed", trainCollapsed);
      const btn = el("collapseTrainBtn");
      if (btn) btn.textContent = trainCollapsed ? "⟩" : "⟨";
    }

    const nSectionTrain = el("sectionTrainBtn");
    const nSectionEval = el("sectionEvalBtn");
    const nSectionMeta = el("sectionMetaBtn");
    const nTabTrainDetail = el("tabTrainDetailBtn");
    const nTabTrainHeadDiag = el("tabTrainHeadDiagnosticsBtn");
    const nTabObjectiveRewardConfig = el("tabObjectiveRewardConfigBtn");
    const nTabOverview = el("tabOverviewBtn");
    const nTabVps = el("tabMuzeroVpsBtn");
    const nTabHeadDiag = el("tabHeadDiagnosticsBtn");
    const nTabUnified = el("tabUnifiedBtn");
    const nTabDecisions = el("tabEvalDecisionsBtn");
    const nTabReplay = el("tabReplayBtn");
    if (nSectionTrain) nSectionTrain.onclick = () => switchSection("train");
    if (nSectionEval) nSectionEval.onclick = () => switchSection("eval");
    if (nSectionMeta) nSectionMeta.onclick = () => switchSection("meta");
    if (nTabTrainDetail) nTabTrainDetail.onclick = () => switchTab("train-detail");
    if (nTabTrainHeadDiag) nTabTrainHeadDiag.onclick = () => switchTab("train-head-diagnostics");
    if (nTabObjectiveRewardConfig) nTabObjectiveRewardConfig.onclick = () => switchTab("objective-reward-config");
    if (nTabOverview) nTabOverview.onclick = () => switchTab("overview");
    if (nTabVps) nTabVps.onclick = () => switchTab("vps");
    if (nTabHeadDiag) nTabHeadDiag.onclick = () => switchTab("head-diagnostics");
    if (nTabUnified) nTabUnified.onclick = () => switchTab("unified");
    if (nTabDecisions) nTabDecisions.onclick = () => switchTab("eval-decisions");
    if (nTabReplay) nTabReplay.onclick = () => switchTab("replay");
    el("collapseTrainBtn").onclick = () => setTrainCollapsed(!trainCollapsed);
    switchSection("eval");
    switchTab("vps");
    loadModel();
  </script>
</body>
</html>
"""


def _watch_paths_and_exit(watch_paths: list[Path], poll_sec: float = 1.0) -> None:
    def _snapshot(paths: list[Path]) -> dict[str, float]:
        out: dict[str, float] = {}
        for base in paths:
            if not base.exists():
                continue
            for p in base.rglob("*.py"):
                try:
                    out[str(p.resolve())] = float(p.stat().st_mtime)
                except Exception:
                    continue
        return out

    last = _snapshot(watch_paths)
    while True:
        time.sleep(max(0.2, float(poll_sec)))
        now = _snapshot(watch_paths)
        if now != last:
            print("[ReportingViewer] code change detected, restarting...")
            os._exit(3)


def serve(
    repo_root: Path,
    host: str,
    port: int,
    catalog_rel_path: str,
    dev_watch_paths: list[Path] | None = None,
) -> None:
    catalog_path = (repo_root / catalog_rel_path).resolve()
    if dev_watch_paths:
        t = threading.Thread(
            target=_watch_paths_and_exit,
            args=(dev_watch_paths, 1.0),
            daemon=True,
        )
        t.start()

    class Handler(BaseHTTPRequestHandler):
        def _send_bytes(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            # Prevent stale inline JS/HTML during iterative debugging.
            self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = _index_html().encode("utf-8")
                self._send_bytes(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/model":
                body = _model_html().encode("utf-8")
                self._send_bytes(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/catalog":
                qs = parse_qs(parsed.query)
                # Optional ?path=... override for quick debugging.
                rel = str(qs.get("path", [catalog_rel_path])[0] or catalog_rel_path)
                payload = _read_catalog((repo_root / rel).resolve())
                body = _json_bytes(payload)
                self._send_bytes(body, "application/json; charset=utf-8")
                return
            if parsed.path == "/api/model":
                qs = parse_qs(parsed.query)
                engine = str(qs.get("engine", [""])[0] or "")
                model_id = str(qs.get("model", [""])[0] or "")
                payload = _read_catalog((repo_root / catalog_rel_path).resolve())
                engines = list(payload.get("engines", []) or [])
                engine_row = next((e for e in engines if str(e.get("engine", "")) == engine), {})
                model_row = next(
                    (m for m in list(engine_row.get("models", []) or []) if str(m.get("model_id", "")) == model_id),
                    {},
                )
                body = _json_bytes(model_row if isinstance(model_row, dict) else {})
                self._send_bytes(body, "application/json; charset=utf-8")
                return
            if parsed.path == "/api/train-summary":
                qs = parse_qs(parsed.query)
                run_id = str(qs.get("run_id", [""])[0] or "").strip()
                if not run_id:
                    body = _json_bytes({})
                else:
                    catalog_payload = _read_catalog((repo_root / catalog_rel_path).resolve())
                    payload = {}
                    runs_roots = list(catalog_payload.get("runs_roots", []) or [])
                    if not runs_roots:
                        legacy_root = str(
                            catalog_payload.get("runs_root", "runs_curriculum") or "runs_curriculum"
                        ).strip()
                        runs_roots = [legacy_root] if legacy_root else ["runs_curriculum"]
                    for runs_root_rel in runs_roots:
                        p = (repo_root / str(runs_root_rel) / run_id / "metrics" / "summary.json").resolve()
                        if not p.exists():
                            continue
                        try:
                            payload = json.loads(p.read_text(encoding="utf-8"))
                        except Exception:
                            payload = {}
                        break
                    body = _json_bytes(payload if isinstance(payload, dict) else {})
                self._send_bytes(body, "application/json; charset=utf-8")
                return
            if parsed.path == "/api/muzero-replay":
                qs = parse_qs(parsed.query)
                eval_source_path = str(qs.get("eval_source_path", [""])[0] or "")
                replay_path = str(qs.get("replay_path", [""])[0] or "")
                episode_index = int(qs.get("episode_index", ["0"])[0] or 0)
                rp = _resolve_replay_path(eval_source_path=eval_source_path, explicit_replay_path=replay_path)
                payload: dict = {
                    "replay_path": str(rp) if rp is not None else "",
                    "episodes_meta": [],
                    "transitions": [],
                }
                if rp is not None:
                    try:
                        raw = json.loads(rp.read_text(encoding="utf-8"))
                        episodes = list(raw.get("episodes", []) or [])
                        payload["schema_version"] = str(raw.get("schema_version", "") or "")
                        payload["run_id"] = str(raw.get("run_id", "") or "")
                        payload["scenario_id"] = str(raw.get("scenario_id", "") or "")
                        payload["bench_id"] = str(raw.get("bench_id", "") or "")
                        payload["scenario_overlay"] = _load_scenario_overlay(
                            repo_root=repo_root,
                            scenario_id=str(raw.get("scenario_id", "") or ""),
                        )
                        payload["episodes_meta"] = [
                            {
                                "episode_index": int(ep.get("episode_index", idx) or idx),
                                "seed": int(ep.get("seed", 0) or 0),
                                "agent_name": str(ep.get("agent_name", "") or ""),
                                "transitions": int(len(list(ep.get("transitions", []) or []))),
                            }
                            for idx, ep in enumerate(episodes)
                            if isinstance(ep, dict)
                        ]
                        if episodes:
                            idx = max(0, min(int(episode_index), len(episodes) - 1))
                            selected = episodes[idx] if isinstance(episodes[idx], dict) else {}
                            payload["selected_episode_index"] = idx
                            payload["selected_seed"] = int(selected.get("seed", 0) or 0)
                            payload["selected_agent_name"] = str(selected.get("agent_name", "") or "")
                            payload["transitions"] = list(selected.get("transitions", []) or [])
                    except Exception as exc:
                        payload["error"] = f"failed to load replay: {exc}"
                else:
                    payload["error"] = "replay file not found"
                body = _json_bytes(payload)
                self._send_bytes(body, "application/json; charset=utf-8")
                return
            if parsed.path == "/api/replay-log":
                qs = parse_qs(parsed.query)
                eval_source_path = str(qs.get("eval_source_path", [""])[0] or "")
                replay_path = str(qs.get("replay_path", [""])[0] or "")
                episode_index = int(qs.get("episode_index", ["0"])[0] or 0)
                upto_step = int(qs.get("upto_step", ["0"])[0] or 0)
                rp = _resolve_replay_path(eval_source_path=eval_source_path, explicit_replay_path=replay_path)
                payload: dict = {"lines": [], "replay_path": str(rp) if rp is not None else ""}
                if rp is None:
                    payload["error"] = "replay file not found"
                else:
                    try:
                        raw = json.loads(rp.read_text(encoding="utf-8"))
                        episodes = list(raw.get("episodes", []) or [])
                        if episodes:
                            idx = max(0, min(int(episode_index), len(episodes) - 1))
                            selected = episodes[idx] if isinstance(episodes[idx], dict) else {}
                            transitions = list(selected.get("transitions", []) or [])
                            end_idx = max(0, min(int(upto_step), max(0, len(transitions) - 1)))
                            lines: list[str] = []
                            for i, tr in enumerate(transitions[: end_idx + 1]):
                                row = dict(tr or {})
                                prefix = ">>" if i == end_idx else "  "
                                turn_pre = int(row.get("game_turn", row.get("turn", 0)) or 0)
                                turn_post = int(row.get("turn", turn_pre) or turn_pre)
                                to_play = str(row.get("to_play", "") or "")
                                action_id = str(row.get("action_id", "") or "")
                                reward = float(row.get("reward", 0.0) or 0.0)
                                dmg = float(row.get("damage_dealt", 0.0) or 0.0)
                                kills = int(row.get("kills_dealt", 0) or 0)
                                turn_suffix = ""
                                if turn_post != turn_pre:
                                    turn_suffix = f" turn_closed->{turn_post}"
                                lines.append(
                                    f"{prefix} step={i} turn={turn_pre}{turn_suffix} to_play={to_play} action={action_id} "
                                    f"reward={reward:.4f} dmg={dmg:.3f} kills={kills}"
                                )
                            payload["lines"] = lines
                    except Exception as exc:
                        payload["error"] = f"failed to build replay log: {exc}"
                body = _json_bytes(payload)
                self._send_bytes(body, "application/json; charset=utf-8")
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A003
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"[ReportingViewer] http://{host}:{port} catalog={catalog_path}")
    httpd.serve_forever()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run curriculum reporting viewer.")
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host.")
    parser.add_argument("--port", default=8777, type=int, help="HTTP port.")
    parser.add_argument(
        "--catalog",
        default="runs_curriculum/experiments/reporting/model_catalog_latest.json",
        help="Catalog path relative to repo-root.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable dev mode (exit on code changes for auto-restart wrapper).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    watch_paths = []
    if bool(args.dev):
        watch_paths = [
            (Path(args.repo_root).resolve() / "mlops" / "reporting"),
        ]
    serve(
        repo_root=Path(args.repo_root).resolve(),
        host=str(args.host),
        port=int(args.port),
        catalog_rel_path=str(args.catalog),
        dev_watch_paths=watch_paths,
    )
