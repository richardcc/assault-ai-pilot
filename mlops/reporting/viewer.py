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
    .ok-chip {
      display:inline-block;
      padding:1px 6px;
      border:1px solid #14532d;
      border-radius:999px;
      color:#86efac;
      background:#052e16;
      font-size:11px;
      font-weight:600;
    }
    .degraded-chip {
      display:inline-block;
      padding:1px 6px;
      border:1px solid #7c2d12;
      border-radius:999px;
      color:#fdba74;
      background:#431407;
      font-size:11px;
      font-weight:600;
    }
    .ok-text { color:#86efac; font-weight:600; }
    .degraded-text { color:#fdba74; font-weight:600; }
    .na-text { color:#94a3b8; font-style:italic; }
    .ok-chip {
      display:inline-block;
      padding:1px 6px;
      border:1px solid #14532d;
      border-radius:999px;
      color:#86efac;
      background:#052e16;
      font-size:11px;
      font-weight:600;
    }
    .degraded-chip {
      display:inline-block;
      padding:1px 6px;
      border:1px solid #7c2d12;
      border-radius:999px;
      color:#fdba74;
      background:#431407;
      font-size:11px;
      font-weight:600;
    }
    .ok-text { color:#86efac; font-weight:600; }
    .degraded-text { color:#fdba74; font-weight:600; }
    .na-text { color:#94a3b8; font-style:italic; }
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
    <div id="catalogBuildMarker" class="muted" style="font-size:11px;margin-top:-6px;margin-bottom:6px;">build: pending</div>
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
    window.__CATALOG_BUILD__ = "catalog-2026-07-20-replay-candidate-fix";
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

    const catalogBuildEl = el("catalogBuildMarker");
    if (catalogBuildEl) catalogBuildEl.textContent = "build: " + String(window.__CATALOG_BUILD__ || "unknown");

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


def _catalog_html() -> str:
    """Backward-compatible alias for tests/importers expecting _catalog_html."""
    return _index_html()


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
    .ok-chip {
      display:inline-block;
      padding:1px 6px;
      border:1px solid #14532d;
      border-radius:999px;
      color:#86efac;
      background:#052e16;
      font-size:11px;
      font-weight:600;
    }
    .degraded-chip {
      display:inline-block;
      padding:1px 6px;
      border:1px solid #7c2d12;
      border-radius:999px;
      color:#fdba74;
      background:#431407;
      font-size:11px;
      font-weight:600;
    }
    .ok-text { color:#86efac; font-weight:600; }
    .degraded-text { color:#fdba74; font-weight:600; }
    .na-text { color:#94a3b8; font-style:italic; }
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
    .replay-hover-legend { display:flex; gap:12px; align-items:center; margin-top:8px; font-size:12px; color:#cbd5e1; }
    .replay-hover-legend-chip { display:inline-block; width:10px; height:10px; border-radius:999px; margin-right:6px; border:1px solid #334155; vertical-align:middle; }
    .replay-hover-legend-move { background:rgba(34,197,94,0.34); border-color:#22c55e; }
    .replay-hover-legend-attack { background:rgba(239,68,68,0.34); border-color:#ef4444; }
    .replay-grid { display:grid; grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.8fr) minmax(280px, 0.75fr); gap:10px; }
    .replay-side-col {
      display:grid;
      gap:10px;
      min-height:0;
      max-height:760px;
      overflow:auto;
      overscroll-behavior: contain;
      padding-right:2px;
    }
    .replay-details-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:10px; }
    .replay-details-grid .replay-panel { margin-top:0; }
    @media (max-width: 1400px) { .replay-grid { grid-template-columns: minmax(0, 1fr); } }
    @media (max-width: 900px) { .replay-details-grid { grid-template-columns: minmax(0, 1fr); } }
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
    .replay-candidate-table-wrap {
      max-height: 320px;
      overflow-y: auto;
      border: 1px solid #334155;
      border-radius: 6px;
    }
    .replay-candidate-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    .replay-candidate-sort-btn {
      background: transparent;
      border: 0;
      color: #cbd5e1;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      padding: 0;
      text-align: left;
    }
    .replay-candidate-sort-btn:hover {
      color: #7dd3fc;
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
              <button id="tabEvalMetricsBtn" class="tab-btn" data-section="eval">Eval Metrics</button>
              <button id="tabUnifiedBtn" class="tab-btn" data-section="eval">Unified Actions + Attack Effectiveness</button>
              <button id="tabEvalDecisionsBtn" class="tab-btn" data-section="eval">Eval KBI Decisions</button>
              <button id="tabReplayBtn" class="tab-btn" data-section="eval">Match Replay</button>
              <button id="tabOverviewBtn" class="tab-btn" data-section="meta">Overview</button>
            </div>
          </div>
          <div class="toolbar-sep"></div>
        <div id="analysisFiltersHost" class="toolbar-filters"></div>
        <span id="viewerBuildMarker" class="muted" style="margin-left:auto;font-size:11px;"></span>
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
        <div id="tabEvalMetrics" class="tab-pane">
          <h2 style="margin-top:8px;">Eval Metrics</h2>
          <div id="evalMetricsRoot" class="list"></div>
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
    window.__VIEWER_BUILD__ = "viewer-2026-07-20-replay-candidate-fix";
    function el(id) { return document.getElementById(id); }
    function esc(v) {
      return String((v === undefined || v === null) ? "" : v).replace(/[&<>"']/g, function (c) {
        return ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" })[c];
      });
    }
    const viewerBuildMarker = el("viewerBuildMarker");
    if (viewerBuildMarker) viewerBuildMarker.textContent = "build: " + String(window.__VIEWER_BUILD__ || "unknown");
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
      objective_pos_weight: 6.8,
      objective_opportunity_max_dist: 3.0,
      mcts_q_clip_abs: 20.0,
      mcts_q_root_normalization_mode: "adaptive_minmax",
      mcts_q_root_normalization_strength: 0.40,
      mcts_q_flat_spread_epsilon: 1.0e-6,
      mcts_vp_flat_q_score_epsilon: 0.02,
      mcts_vp_flat_q_min_progress: 0.0,
      aux_objective_enabled: false,
      aux_objective_loss_weight: 0.0,
      aux_intent_loss_weight: 0.5,
      aux_multi_vp_loss_weight: 0.5,
      aux_multi_vp_feature_dim: 4,
      aux_intent_classes: 8,
      objective_progress_positive_threshold: 0.0,
      objective_opportunity_near_vp_max_dist: 3.0,
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
      mcts_vp_tiebreak_epsilon: 0.015,
      capture_bonus: 0.70,
      vp_capture_bonus_per_hex: 1.20,
      objective_progress_bonus_per_hex: 0.95,
      objective_no_progress_penalty: 0.46,
      objective_no_progress_attack_penalty: 0.40,
      reaction_fire_soft_signal_enabled: true,
      reaction_fire_soft_signal_weight: 0.04,
      reaction_fire_soft_signal_expected_damage_scale: 4.0,
      global_strategy_soft_enabled: true,
      global_strategy_vp_control_net_gain_weight: 0.08,
      global_strategy_units_in_vp_ring_weight: 0.04,
      global_strategy_enemy_vp_threat_reduced_weight: 0.05,
      global_strategy_sustained_vp_advantage_weight: 0.02,
      global_strategy_role_consistency_weight: 0.03,
      global_strategy_setup_convert_weight: 0.03,
      global_strategy_vp_ring_radius: 2,
      global_strategy_enemy_threat_radius: 3,
      global_strategy_sustained_advantage_min_turns: 2,
      global_strategy_total_cap_abs: 0.15,
      vp_horizon_soft_enabled: true,
      vp_horizon_soft_weight: 0.02,
      vp_horizon_soft_cap_steps: 8.0,
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
        ["VP Tiebreak Epsilon", fmtDashNum(trainSelf.mcts_vp_tiebreak_epsilon, 3)],
        ["Progress Bonus/Hex", fmtDashNum(((trainSelf.reward_shaping || {}).objective_progress_bonus_per_hex), 3)],
        ["No-Progress Penalty", fmtDashNum(((trainSelf.reward_shaping || {}).objective_no_progress_penalty), 3)],
        ["No-Progress Attack Penalty", fmtDashNum(((trainSelf.reward_shaping || {}).objective_no_progress_attack_penalty), 3)],
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
          return { label: label, value: explicitValue, source: "run_config", status: "ok" };
        }
        if (Object.prototype.hasOwnProperty.call(objectiveRewardDefaults, fallbackKey || label)) {
          return {
            label: label,
            value: objectiveRewardDefaults[fallbackKey || label],
            source: "fallback_default",
            status: "degraded",
          };
        }
        return { label: label, value: "N/A", source: "missing", status: "degraded" };
      }
      const rows = [
        { section: "Objective Head Runtime", row: pull("objective_loss_weight", trainCfg.objective_loss_weight) },
        { section: "Objective Head Runtime", row: pull("objective_target_mode", trainCfg.objective_target_mode) },
        { section: "Objective Head Runtime", row: pull("objective_pos_weight", trainCfg.objective_pos_weight) },
        { section: "Objective Head Runtime", row: pull("mcts_vp_tiebreak_epsilon", selfCfg.mcts_vp_tiebreak_epsilon) },
        { section: "Objective Head Runtime", row: pull("objective_opportunity_max_dist", trainCfg.objective_opportunity_max_dist) },
        { section: "Objective Head Runtime", row: pull("aux_objective_enabled", trainCfg.aux_objective_enabled) },
        { section: "Objective Head Runtime", row: pull("aux_objective_loss_weight", trainCfg.aux_objective_loss_weight) },
        { section: "Objective Head Runtime", row: pull("aux_intent_loss_weight", trainCfg.aux_intent_loss_weight) },
        { section: "Objective Head Runtime", row: pull("aux_multi_vp_loss_weight", trainCfg.aux_multi_vp_loss_weight) },
        { section: "Objective Head Runtime", row: pull("aux_multi_vp_feature_dim", trainCfg.aux_multi_vp_feature_dim) },
        { section: "Objective Head Runtime", row: pull("aux_intent_classes", trainCfg.aux_intent_classes) },
        { section: "Objective Head Runtime", row: pull("objective_progress_positive_threshold", headCfg.progress_positive_threshold) },
        { section: "Objective Head Runtime", row: pull("objective_opportunity_near_vp_max_dist", signalCfg.opportunity_near_vp_max_dist) },
        { section: "Q Calibration / MCTS", row: pull("mcts_q_clip_abs", selfCfg.mcts_q_clip_abs) },
        { section: "Q Calibration / MCTS", row: pull("mcts_q_root_normalization_mode", selfCfg.mcts_q_root_normalization_mode) },
        { section: "Q Calibration / MCTS", row: pull("mcts_q_root_normalization_strength", selfCfg.mcts_q_root_normalization_strength) },
        { section: "Q Calibration / MCTS", row: pull("mcts_q_flat_spread_epsilon", selfCfg.mcts_q_flat_spread_epsilon) },
        { section: "Q Calibration / MCTS", row: pull("mcts_vp_flat_q_score_epsilon", selfCfg.mcts_vp_flat_q_score_epsilon) },
        { section: "Q Calibration / MCTS", row: pull("mcts_vp_flat_q_min_progress", selfCfg.mcts_vp_flat_q_min_progress) },
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
        { section: "Combat Soft Signals", row: pull("reaction_fire_soft_signal_enabled", rewardCfg.reaction_fire_soft_signal_enabled) },
        { section: "Combat Soft Signals", row: pull("reaction_fire_soft_signal_weight", rewardCfg.reaction_fire_soft_signal_weight) },
        { section: "Combat Soft Signals", row: pull("reaction_fire_soft_signal_expected_damage_scale", rewardCfg.reaction_fire_soft_signal_expected_damage_scale) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_soft_enabled", rewardCfg.global_strategy_soft_enabled) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_vp_control_net_gain_weight", rewardCfg.global_strategy_vp_control_net_gain_weight) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_units_in_vp_ring_weight", rewardCfg.global_strategy_units_in_vp_ring_weight) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_enemy_vp_threat_reduced_weight", rewardCfg.global_strategy_enemy_vp_threat_reduced_weight) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_sustained_vp_advantage_weight", rewardCfg.global_strategy_sustained_vp_advantage_weight) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_role_consistency_weight", rewardCfg.global_strategy_role_consistency_weight) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_setup_convert_weight", rewardCfg.global_strategy_setup_convert_weight) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_vp_ring_radius", rewardCfg.global_strategy_vp_ring_radius) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_enemy_threat_radius", rewardCfg.global_strategy_enemy_threat_radius) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_sustained_advantage_min_turns", rewardCfg.global_strategy_sustained_advantage_min_turns) },
        { section: "Global Strategy Soft Signals", row: pull("global_strategy_total_cap_abs", rewardCfg.global_strategy_total_cap_abs) },
        { section: "Global Strategy Soft Signals", row: pull("vp_horizon_soft_enabled", rewardCfg.vp_horizon_soft_enabled) },
        { section: "Global Strategy Soft Signals", row: pull("vp_horizon_soft_weight", rewardCfg.vp_horizon_soft_weight) },
        { section: "Global Strategy Soft Signals", row: pull("vp_horizon_soft_cap_steps", rewardCfg.vp_horizon_soft_cap_steps) },
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
        { name: "Q Calibration / MCTS", wide: false },
        { name: "Combat Soft Signals", wide: false },
        { name: "Global Strategy Soft Signals", wide: true },
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
          const statusChip = (r.status === "ok")
            ? "<span class='ok-chip'>OK</span>"
            : "<span class='degraded-chip'>degraded</span>";
          const valueClass = (r.status === "ok") ? "ok-text" : ((String(r.value) === "N/A") ? "na-text" : "degraded-text");
          return "<tr>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(r.label) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'><span class='" + valueClass + "'>" + esc(r.value) + "</span></td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + statusChip + " <span class='muted'>(" + esc(r.source) + ")</span></td>" +
            "</tr>";
        }).join("");
        return "<div class='" + sectionClass + "'>" +
          "<h3>" + esc(sectionName) + "</h3>" +
          "<div class='objective-reward-table-wrap'>" +
            "<table class='objective-reward-table'>" +
              "<thead><tr>" +
                "<th style='text-align:left;border:1px solid #334155;padding:6px;'>parameter</th>" +
                "<th style='text-align:left;border:1px solid #334155;padding:6px;'>active_value</th>" +
                "<th style='text-align:left;border:1px solid #334155;padding:6px;'>status/source</th>" +
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
        '<div class="muted" style="margin-bottom:8px;">OK criteria: <b>run_config</b> values are green; <b>fallback_default</b> and <b>missing (N/A)</b> are degraded.</div>' +
        "<div class='objective-reward-grid'>" + sectionTables + "</div>" +
        "<div class='muted' style='margin-top:8px;'>Rows marked degraded indicate fallback/defaulted or missing config coverage.</div>";
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
      if (p === "mcts" || p === "muzero" || p === "muzero_controller") return "MuZero";
      if (p === "random") return "Random";
      if (p === "legacy/unlabeled") return "Legacy/Unlabeled";
      return "Unknown";
    }

    function sideValueFromMap(src, side) {
      if (!src || typeof src !== "object") return "";
      const sideRaw = String(side || "");
      const sideUp = sideRaw.toUpperCase();
      const v = src[sideUp] || src[sideRaw] || src[String(sideRaw || "").toLowerCase()];
      return String(v || "").trim();
    }

    function readResultMetadata(resultRow) {
      if (!resultRow || typeof resultRow !== "object") return {};
      const direct = resultRow.metadata;
      if (direct && typeof direct === "object") return direct;
      const fallback = resultRow.meta;
      if (fallback && typeof fallback === "object") return fallback;
      const raw = resultRow.metadata_json || resultRow.meta_json;
      if (!raw) return {};
      try {
        const parsed = JSON.parse(String(raw));
        return (parsed && typeof parsed === "object") ? parsed : {};
      } catch (_e) {
        return {};
      }
    }

    function controllerFor(resultRow, side) {
      const s = String(side || "").trim().toUpperCase();
      const cb = (resultRow && resultRow.controller_by_side) || {};
      const explicit = sideValueFromMap(cb, s);
      if (explicit) {
        const normalizedExplicit = normalizeControllerLabel(explicit);
        return normalizedExplicit !== "Unknown" ? normalizedExplicit : explicit;
      }
      const pb = (resultRow && resultRow.policy_by_side) || {};
      const p = String(sideValueFromMap(pb, s) || "").toLowerCase();
      if (p) return normalizeControllerLabel(p);
      const meta = readResultMetadata(resultRow);
      const metaCb = (meta && meta.controller_by_side) || {};
      const metaExplicit = sideValueFromMap(metaCb, s);
      if (metaExplicit) {
        const normalizedMetaExplicit = normalizeControllerLabel(metaExplicit);
        return normalizedMetaExplicit !== "Unknown" ? normalizedMetaExplicit : metaExplicit;
      }
      const metaPb = (meta && (meta.policy_by_side || meta.side_policy_by_side)) || {};
      const metaPolicy = String(sideValueFromMap(metaPb, s) || "").toLowerCase();
      if (metaPolicy) return normalizeControllerLabel(metaPolicy);
      return "Legacy/Unlabeled";
    }

    function controllerBySideFromResult(resultRow) {
      const row = (resultRow && typeof resultRow === "object") ? resultRow : {};
      const meta = readResultMetadata(row);
      const summary = (row.eval_decision_summary && typeof row.eval_decision_summary === "object") ? row.eval_decision_summary : {};
      const byActionSide = (summary.by_action_kind_and_side && typeof summary.by_action_kind_and_side === "object")
        ? summary.by_action_kind_and_side
        : {};
      const sideSet = {};
      function registerFromMap(src) {
        if (!src || typeof src !== "object") return;
        for (const key of Object.keys(src)) {
          const side = String(key || "").trim().toUpperCase();
          if (side) sideSet[side] = true;
        }
      }
      registerFromMap(row.controller_by_side);
      registerFromMap(row.policy_by_side);
      registerFromMap(meta.controller_by_side);
      registerFromMap(meta.policy_by_side);
      registerFromMap(meta.side_policy_by_side);
      for (const key of Object.keys(byActionSide)) {
        const side = String(((byActionSide[key] || {}).unit_side) || "").trim().toUpperCase();
        if (side) sideSet[side] = true;
      }
      const sides = Object.keys(sideSet).sort((a, b) => String(a || "").localeCompare(String(b || "")));
      if (!sides.length) {
        return [{ side: "Unlabeled side", controller: "Unknown/Unlabeled", source: "fallback" }];
      }
      return sides.map(function (side) {
        const explicit = sideValueFromMap(row.controller_by_side, side);
        if (explicit) {
          const normalizedExplicit = normalizeControllerLabel(explicit);
          return { side: side, controller: normalizedExplicit !== "Unknown" ? normalizedExplicit : explicit, source: "controller_by_side" };
        }
        const policy = sideValueFromMap(row.policy_by_side, side);
        if (policy) {
          return { side: side, controller: normalizeControllerLabel(policy), source: "policy_by_side" };
        }
        const metaExplicit = sideValueFromMap(meta.controller_by_side, side);
        if (metaExplicit) {
          const normalizedMetaExplicit = normalizeControllerLabel(metaExplicit);
          return { side: side, controller: normalizedMetaExplicit !== "Unknown" ? normalizedMetaExplicit : metaExplicit, source: "metadata" };
        }
        const metaPolicy = sideValueFromMap((meta && (meta.policy_by_side || meta.side_policy_by_side)) || {}, side);
        if (metaPolicy) {
          return { side: side, controller: normalizeControllerLabel(metaPolicy), source: "metadata" };
        }
        return { side: side, controller: "Unknown/Unlabeled", source: "fallback" };
      });
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
        const c = normalizeControllerLabel(controllerFor(resultRow, s));
        const selectedCtrlNorm = selectedController === "__all__"
          ? "__all__"
          : normalizeControllerLabel(selectedController);
        if (selectedCtrlNorm !== "__all__" && c !== selectedCtrlNorm) return false;
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
      function fmtNumNa(v) { return (v === null || v === undefined) ? "N/A" : Number(v).toFixed(3); }
      function fmtPctNa(v) { return (v === null || v === undefined) ? "N/A" : (Number(v) * 100).toFixed(1) + "%"; }
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
          vp_approach_rate_eligible_steps: 0,
          vp_approach_rate_positive_steps: 0,
          vp_regret_delta_count: 0,
          vp_regret_delta_mean_weighted_sum: 0,
          vp_regret_delta_p95_weighted_sum: 0,
          q_saturation_candidate_rows: 0,
          q_saturation_hits: 0,
          decision_spread_step_count: 0,
          decision_spread_mean_weighted_sum: 0,
          decision_spread_p50_weighted_sum: 0,
          decision_spread_p95_weighted_sum: 0,
          path_to_capture_length_count: 0,
          path_to_capture_length_weighted_sum: 0,
          path_to_capture_length_p95_weighted_sum: 0,
          opportunity_conversion_early_opportunity_steps: 0,
          opportunity_conversion_early_converted_steps: 0,
          opportunity_conversion_mid_opportunity_steps: 0,
          opportunity_conversion_mid_converted_steps: 0,
          opportunity_conversion_late_opportunity_steps: 0,
          opportunity_conversion_late_converted_steps: 0,
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
              vp_approach_rate_eligible_steps: 0,
              vp_approach_rate_positive_steps: 0,
              vp_regret_delta_count: 0,
              vp_regret_delta_mean: 0,
              vp_regret_delta_p95: 0,
              q_saturation_candidate_rows: 0,
              q_saturation_hits: 0,
              decision_spread_step_count: 0,
              decision_spread_mean: 0,
              decision_spread_p50: 0,
              decision_spread_p95: 0,
              path_to_capture_length_count: 0,
              path_to_capture_length_mean: 0,
              path_to_capture_length_p95: 0,
              opportunity_conversion_early_opportunity_steps: 0,
              opportunity_conversion_early_converted_steps: 0,
              opportunity_conversion_mid_opportunity_steps: 0,
              opportunity_conversion_mid_converted_steps: 0,
              opportunity_conversion_late_opportunity_steps: 0,
              opportunity_conversion_late_converted_steps: 0,
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
              merged.vp_approach_rate_eligible_steps += Number(ks.vp_approach_rate_eligible_steps || 0);
              merged.vp_approach_rate_positive_steps += Number(ks.vp_approach_rate_positive_steps || 0);
              merged.vp_regret_delta_count += Number(ks.vp_regret_delta_count || 0);
              merged.vp_regret_delta_mean += Number(ks.vp_regret_delta_mean || 0);
              merged.vp_regret_delta_p95 += Number(ks.vp_regret_delta_p95 || 0);
              merged.q_saturation_candidate_rows += Number(ks.q_saturation_candidate_rows || 0);
              merged.q_saturation_hits += Number(ks.q_saturation_hits || 0);
              merged.decision_spread_step_count += Number(ks.decision_spread_step_count || 0);
              merged.decision_spread_mean += Number(ks.decision_spread_mean || 0);
              merged.decision_spread_p50 += Number(ks.decision_spread_p50 || 0);
              merged.decision_spread_p95 += Number(ks.decision_spread_p95 || 0);
              merged.path_to_capture_length_count += Number(ks.path_to_capture_length_count || 0);
              merged.path_to_capture_length_mean += Number(ks.path_to_capture_length_mean || 0);
              merged.path_to_capture_length_p95 += Number(ks.path_to_capture_length_p95 || 0);
              merged.opportunity_conversion_early_opportunity_steps += Number(ks.opportunity_conversion_early_opportunity_steps || 0);
              merged.opportunity_conversion_early_converted_steps += Number(ks.opportunity_conversion_early_converted_steps || 0);
              merged.opportunity_conversion_mid_opportunity_steps += Number(ks.opportunity_conversion_mid_opportunity_steps || 0);
              merged.opportunity_conversion_mid_converted_steps += Number(ks.opportunity_conversion_mid_converted_steps || 0);
              merged.opportunity_conversion_late_opportunity_steps += Number(ks.opportunity_conversion_late_opportunity_steps || 0);
              merged.opportunity_conversion_late_converted_steps += Number(ks.opportunity_conversion_late_converted_steps || 0);
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
          totals.vp_approach_rate_eligible_steps += Number(k.vp_approach_rate_eligible_steps || 0);
          totals.vp_approach_rate_positive_steps += Number(k.vp_approach_rate_positive_steps || 0);
          totals.vp_regret_delta_count += Number(k.vp_regret_delta_count || 0);
          totals.vp_regret_delta_mean_weighted_sum += Number(k.vp_regret_delta_mean || 0) * Number(k.vp_regret_delta_count || 0);
          totals.vp_regret_delta_p95_weighted_sum += Number(k.vp_regret_delta_p95 || 0) * eps;
          totals.q_saturation_candidate_rows += Number(k.q_saturation_candidate_rows || 0);
          totals.q_saturation_hits += Number(k.q_saturation_hits || 0);
          totals.decision_spread_step_count += Number(k.decision_spread_step_count || 0);
          totals.decision_spread_mean_weighted_sum += Number(k.decision_spread_mean || 0) * Number(k.decision_spread_step_count || 0);
          totals.decision_spread_p50_weighted_sum += Number(k.decision_spread_p50 || 0) * eps;
          totals.decision_spread_p95_weighted_sum += Number(k.decision_spread_p95 || 0) * eps;
          totals.path_to_capture_length_count += Number(k.path_to_capture_length_count || 0);
          totals.path_to_capture_length_weighted_sum += Number(k.path_to_capture_length_mean || 0) * Number(k.path_to_capture_length_count || 0);
          totals.path_to_capture_length_p95_weighted_sum += Number(k.path_to_capture_length_p95 || 0) * Number(k.path_to_capture_length_count || 0);
          totals.opportunity_conversion_early_opportunity_steps += Number(k.opportunity_conversion_early_opportunity_steps || 0);
          totals.opportunity_conversion_early_converted_steps += Number(k.opportunity_conversion_early_converted_steps || 0);
          totals.opportunity_conversion_mid_opportunity_steps += Number(k.opportunity_conversion_mid_opportunity_steps || 0);
          totals.opportunity_conversion_mid_converted_steps += Number(k.opportunity_conversion_mid_converted_steps || 0);
          totals.opportunity_conversion_late_opportunity_steps += Number(k.opportunity_conversion_late_opportunity_steps || 0);
          totals.opportunity_conversion_late_converted_steps += Number(k.opportunity_conversion_late_converted_steps || 0);
          totals.weight_n += eps;
        }
        const den = Math.max(1, Number(totals.weight_n || 0));
        const decisions = Math.max(1, Number(totals.xai_decision_steps || 0));
        const regretCount = Number(totals.vp_regret_delta_count || 0);
        const spreadCount = Number(totals.decision_spread_step_count || 0);
        const pathCount = Number(totals.path_to_capture_length_count || 0);
        const approachEligible = Number(totals.vp_approach_rate_eligible_steps || 0);
        const qSatCandidates = Number(totals.q_saturation_candidate_rows || 0);
        const oppEarly = Number(totals.opportunity_conversion_early_opportunity_steps || 0);
        const oppMid = Number(totals.opportunity_conversion_mid_opportunity_steps || 0);
        const oppLate = Number(totals.opportunity_conversion_late_opportunity_steps || 0);
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
          vp_approach_rate_eligible_steps: approachEligible,
          vp_approach_rate_positive_steps: Number(totals.vp_approach_rate_positive_steps || 0),
          vp_approach_rate: approachEligible > 0 ? (Number(totals.vp_approach_rate_positive_steps || 0) / approachEligible) : null,
          vp_regret_delta_count: regretCount,
          vp_regret_delta_mean: regretCount > 0 ? (totals.vp_regret_delta_mean_weighted_sum / regretCount) : null,
          vp_regret_delta_p95: den > 0 ? (totals.vp_regret_delta_p95_weighted_sum / den) : null,
          q_saturation_candidate_rows: qSatCandidates,
          q_saturation_hits: Number(totals.q_saturation_hits || 0),
          q_saturation_rate: qSatCandidates > 0 ? (Number(totals.q_saturation_hits || 0) / qSatCandidates) : null,
          decision_spread_step_count: spreadCount,
          decision_spread_mean: spreadCount > 0 ? (totals.decision_spread_mean_weighted_sum / spreadCount) : null,
          decision_spread_p50: den > 0 ? (totals.decision_spread_p50_weighted_sum / den) : null,
          decision_spread_p95: den > 0 ? (totals.decision_spread_p95_weighted_sum / den) : null,
          path_to_capture_length_count: pathCount,
          path_to_capture_length_mean: pathCount > 0 ? (totals.path_to_capture_length_weighted_sum / pathCount) : null,
          path_to_capture_length_p95: pathCount > 0 ? (totals.path_to_capture_length_p95_weighted_sum / pathCount) : null,
          opportunity_conversion_early_opportunity_steps: oppEarly,
          opportunity_conversion_early_converted_steps: Number(totals.opportunity_conversion_early_converted_steps || 0),
          opportunity_conversion_early_rate: oppEarly > 0 ? (Number(totals.opportunity_conversion_early_converted_steps || 0) / oppEarly) : null,
          opportunity_conversion_mid_opportunity_steps: oppMid,
          opportunity_conversion_mid_converted_steps: Number(totals.opportunity_conversion_mid_converted_steps || 0),
          opportunity_conversion_mid_rate: oppMid > 0 ? (Number(totals.opportunity_conversion_mid_converted_steps || 0) / oppMid) : null,
          opportunity_conversion_late_opportunity_steps: oppLate,
          opportunity_conversion_late_converted_steps: Number(totals.opportunity_conversion_late_converted_steps || 0),
          opportunity_conversion_late_rate: oppLate > 0 ? (Number(totals.opportunity_conversion_late_converted_steps || 0) / oppLate) : null,
          opportunity_conversion_turn_buckets_definition: "early: turn<=3, mid: turn 4-7, late: turn>=8",
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
        function resultMatchesUnifiedFilters(resultRow) {
          if (!resultRow || typeof resultRow !== "object") return false;
          if (p !== "__all__" && String(resultRow.matchup_profile || "") !== String(p)) return false;
          if (s === "__all__" && c === "__all__") return true;
          const sidesLocal = collectSidesFromResult(resultRow);
          if (!Array.isArray(sidesLocal) || !sidesLocal.length) return false;
          return sidesLocal.some(function (side) {
            return sideAllowed(resultRow, side, s, c);
          });
        }
        const evalRowsForTabs = rows.filter(r =>
          (e === "__all__" || String(r.eval_id || "") === String(e)) &&
          (p === "__all__" || (Array.isArray(r.results) && r.results.some(x => String(x.matchup_profile || "") === String(p)))) &&
          (s === "__all__" || (Array.isArray(r.results) && r.results.some(x => collectSidesFromResult(x).includes(s)))) &&
          (c === "__all__" || (Array.isArray(r.results) && r.results.some(x => collectSidesFromResult(x).some(side => resultController(x, side) === c))))
        );
        const evalRowsForUnified = evalRowsForTabs
          .map(function (er) {
            const results = Array.isArray(er.results)
              ? er.results.filter(resultMatchesUnifiedFilters)
              : [];
            if (!results.length) return null;
            const out = Object.assign({}, er);
            out.results = results;
            return out;
          })
          .filter(Boolean);
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
        const replayRows = evalRowsForUnified;
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
        htmlVps += '<div style="margin-top:12px;"><h3 style="margin:0 0 6px 0;">Decision-making KPIs</h3>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_approach_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_regret_delta_mean</th>' +
          '<th style="border:1px solid #334155;padding:6px;">vp_regret_delta_p95</th>' +
          '<th style="border:1px solid #334155;padding:6px;">q_saturation_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">decision_spread_mean</th>' +
          '<th style="border:1px solid #334155;padding:6px;">decision_spread_p50</th>' +
          '<th style="border:1px solid #334155;padding:6px;">decision_spread_p95</th>' +
          '<th style="border:1px solid #334155;padding:6px;">path_to_capture_length_mean</th>' +
          '<th style="border:1px solid #334155;padding:6px;">path_to_capture_length_p95</th>' +
          '</tr></thead><tbody><tr>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPctNa(xai.vp_approach_rate)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.vp_regret_delta_mean)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.vp_regret_delta_p95)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtPctNa(xai.q_saturation_rate)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.decision_spread_mean)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.decision_spread_p50)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.decision_spread_p95)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.path_to_capture_length_mean)) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(fmtNumNa(xai.path_to_capture_length_p95)) + '</td>' +
          '</tr></tbody></table>' +
          '<div class="muted" style="margin-top:4px;">N/A means producer telemetry for that KPI is unavailable after current filters.</div>' +
          '</div>';
        htmlVps += '<div style="margin-top:12px;"><h3 style="margin:0 0 6px 0;">Opportunity conversion by turn</h3>' +
          '<div class="muted" style="margin-bottom:6px;">Buckets: ' + esc(String(xai.opportunity_conversion_turn_buckets_definition || "early: turn<=3, mid: turn 4-7, late: turn>=8")) + '</div>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">bucket</th>' +
          '<th style="border:1px solid #334155;padding:6px;">opportunity_steps</th>' +
          '<th style="border:1px solid #334155;padding:6px;">converted_steps</th>' +
          '<th style="border:1px solid #334155;padding:6px;">conversion_rate</th>' +
          '</tr></thead><tbody>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">early</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.opportunity_conversion_early_opportunity_steps || 0)))) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.opportunity_conversion_early_converted_steps || 0)))) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(fmtPctNa(xai.opportunity_conversion_early_rate)) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">mid</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.opportunity_conversion_mid_opportunity_steps || 0)))) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.opportunity_conversion_mid_converted_steps || 0)))) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(fmtPctNa(xai.opportunity_conversion_mid_rate)) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">late</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.opportunity_conversion_late_opportunity_steps || 0)))) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(String(Math.round(Number(xai.opportunity_conversion_late_converted_steps || 0)))) + '</td><td style="border:1px solid #334155;padding:6px;">' + esc(fmtPctNa(xai.opportunity_conversion_late_rate)) + '</td></tr>' +
          '</tbody></table></div>';
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
        renderEvalMetrics(evalRowsForUnified, { side: s, controller: c, sideAllowed: sideAllowed });
        renderUnifiedActions(evalRowsForUnified, { side: s, controller: c, sideAllowed: sideAllowed });
        renderEvalDecisions(evalRowsForUnified, { side: s, controller: c, sideAllowed: sideAllowed });
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
      function renderEvalMetrics(filteredResultRows, filterCtx) {
        const host = document.getElementById("evalMetricsRoot");
        if (!host) return;
        const sourceRows = Array.isArray(filteredResultRows) ? filteredResultRows : [];
        const sideAllowedFn = (filterCtx && typeof filterCtx.sideAllowed === "function")
          ? filterCtx.sideAllowed
          : function () { return true; };
        const selectedSide = (filterCtx && filterCtx.side) || "__all__";
        const selectedController = (filterCtx && filterCtx.controller) || "__all__";
        const channels = [
          { key: "obs_unit_position", label: "obs_unit_position", layer: "input", source: "observation_stack:unit_positions", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["unit_positions", "units"]); } },
          { key: "obs_unit_hp_map", label: "obs_unit_hp_map", layer: "input", source: "observation_stack:unit_hp_map", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["unit_hp_map"]); } },
          { key: "obs_unit_alive_map", label: "obs_unit_alive_map", layer: "input", source: "observation_stack:unit_alive_map", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["unit_alive_map"]); } },
          { key: "obs_vp_map", label: "obs_vp_map", layer: "input", source: "observation_stack:vp_map", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["vp_map", "objective_map"]); } },
          { key: "obs_enemy_vp_threat_map", label: "obs_enemy_vp_threat_map", layer: "input", source: "observation_stack:obs_enemy_vp_threat_map", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_enemy_vp_threat_map"]); } },
          { key: "obs_terrain_type_map", label: "obs_terrain_type_map", layer: "input", source: "observation_stack:terrain_type_by_hex", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_terrain_type_map"]); } },
          { key: "obs_terrain_cover_map", label: "obs_terrain_cover_map", layer: "input", source: "observation_stack:terrain_cover_by_hex", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_terrain_cover_map", "terrain_cover_by_hex"]); } },
          { key: "obs_terrain_los_block_map", label: "obs_terrain_los_block_map", layer: "input", source: "observation_stack:terrain_los_block_by_hex", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_terrain_los_block_map", "terrain_los_block_by_hex"]); } },
          { key: "obs_terrain_move_cost_map", label: "obs_terrain_move_cost_map", layer: "input", source: "observation_stack:terrain_move_cost_by_hex", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_terrain_move_cost_map", "terrain_move_cost_by_hex"]); } },
          { key: "obs_fortification_type_map", label: "obs_fortification_type_map", layer: "input", source: "observation_stack:fortification_type_by_hex", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_fortification_type_map"]); } },
          { key: "obs_fortification_edge_map", label: "obs_fortification_edge_map", layer: "input", source: "observation_stack:fortification_edge_by_hex", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_fortification_edge_map"]); } },
          { key: "obs_reachable_hex_mask_by_unit", label: "obs_reachable_hex_mask_by_unit", layer: "input", source: "observation_stack:obs_reachable_hex_mask_by_unit", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_reachable_hex_mask_by_unit"]); } },
          { key: "obs_attackable_hex_mask_by_unit", label: "obs_attackable_hex_mask_by_unit", layer: "input", source: "observation_stack:obs_attackable_hex_mask_by_unit", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_attackable_hex_mask_by_unit"]); } },
          { key: "obs_vp_ownership_ttl", label: "obs_vp_ownership_ttl", layer: "input", source: "observation_stack:obs_vp_ownership_ttl", nonNumeric: true, getter: function (step) { return containerFieldPresent(step, ["obs_vp_ownership_ttl"]); } },
          { key: "obs_enemy_reaction_fire_risk", label: "obs_enemy_reaction_fire_risk", layer: "input", source: "observation_stack:obs_enemy_reaction_fire_risk", getter: function (step) { return numberField(step, "obs_enemy_reaction_fire_risk"); } },
          { key: "obs_unit_side", label: "obs_unit_side", layer: "input", source: "observation_stack:unit_side", nonNumeric: true, getter: function (step) { return scalarFieldPresent(step, ["unit_side", "to_play"]); } },
          { key: "mcts_prior", label: "mcts_prior", layer: "decision", source: "producer field:mcts_prior | mcts_action_candidates[].policy_prior", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["mcts_prior"], decisionComponentKeys: ["policy_prior"], availabilityKeys: ["mcts_prior_available"], sourceKeys: ["mcts_prior_source"] }); } },
          { key: "mcts_q_value", label: "mcts_q_value", layer: "decision", source: "producer field:mcts_q_value | mcts_action_candidates[].mcts_q_value", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["mcts_q_value"], decisionComponentKeys: ["mcts_q_value", "q_value"], availabilityKeys: ["mcts_q_value_available"], sourceKeys: ["mcts_q_value_source"] }); } },
          { key: "mcts_u_value", label: "mcts_u_value", layer: "decision", source: "producer field:mcts_u_value | mcts_action_candidates[].mcts_u_value", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["mcts_u_value"], decisionComponentKeys: ["mcts_u_value", "u_value"], availabilityKeys: ["mcts_u_value_available"], sourceKeys: ["mcts_u_value_source"] }); } },
          { key: "vp_progress", label: "vp_progress", layer: "decision", source: "producer field:vp_progress", getter: function (step) { return numberField(step, "vp_progress"); } },
          { key: "mcts_success_prob_proxy", label: "mcts_success_prob_proxy", layer: "decision", source: "producer field:mcts_success_prob_proxy | selected_action.decision_components.success_prob_proxy", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["mcts_success_prob_proxy"], decisionComponentKeys: ["mcts_success_prob_proxy", "success_prob_proxy"], availabilityKeys: ["mcts_success_prob_proxy_available"], sourceKeys: ["mcts_success_prob_proxy_source"] }); } },
          { key: "mcts_success_component", label: "mcts_success_component", layer: "decision", source: "producer field:mcts_success_component | selected_action.decision_components.success_component", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["mcts_success_component"], decisionComponentKeys: ["mcts_success_component", "success_component"], availabilityKeys: ["mcts_success_component_available"], sourceKeys: ["mcts_success_component_source"] }); } },
          { key: "vp_horizon_steps", label: "vp_horizon_steps", layer: "decision", source: "producer field:vp_horizon_steps | selected_action.decision_components.vp_horizon_steps", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["vp_horizon_steps"], decisionComponentKeys: ["vp_horizon_steps"], availabilityKeys: ["vp_horizon_available"], sourceKeys: ["vp_horizon_source"] }); } },
          { key: "vp_horizon_signal", label: "vp_horizon_signal", layer: "decision", source: "producer field:vp_horizon_signal | selected_action.decision_components.vp_horizon_signal", getter: function (step) { return numberFieldMulti(step, ["vp_horizon_signal"], ["vp_horizon_signal"]); } },
          { key: "vp_horizon_component", label: "vp_horizon_component", layer: "decision", source: "producer field:vp_horizon_component | selected_action.decision_components.vp_horizon_component", getter: function (step) { return numberFieldMulti(step, ["vp_horizon_component"], ["vp_horizon_component"]); } },
          { key: "vp_horizon_decision_component", label: "vp_horizon_decision_component", layer: "decision", source: "producer field:vp_horizon_decision_component | selected_action.decision_components.vp_horizon_decision_component", getter: function (step) { return numberFieldMulti(step, ["vp_horizon_decision_component"], ["vp_horizon_component", "vp_horizon_decision_component"]); } },
          { key: "objective_soft_reward_component", label: "objective_soft_reward_component", layer: "decision", source: "producer field:objective_soft_reward_component", getter: function (step) { return numberFieldMulti(step, ["objective_soft_reward_component"], ["objective_soft_reward_component"]); } },
          { key: "global_strategy_soft_reward_component", label: "global_strategy_soft_reward_component", layer: "decision", source: "producer field:global_strategy_soft_reward_component", getter: function (step) { return numberFieldMulti(step, ["global_strategy_soft_reward_component"], ["global_strategy_soft_reward_component"]); } },
          { key: "reaction_fire_soft_reward_component", label: "reaction_fire_soft_reward_component", layer: "decision", source: "producer field:reaction_fire_soft_reward_component", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["reaction_fire_soft_reward_component"], decisionComponentKeys: ["reaction_fire_soft_reward_component"], availabilityKeys: ["reaction_fire_soft_reward_component_available"], sourceKeys: ["reaction_fire_soft_reward_component_source"] }); } },
          { key: "reaction_exposure_component", label: "reaction_exposure_component", layer: "decision", source: "producer field:reaction_exposure_component", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["reaction_exposure_component"], decisionComponentKeys: ["reaction_exposure_component"], availabilityKeys: ["reaction_exposure_component_available"], sourceKeys: ["reaction_exposure_component_source"] }); } },
          { key: "strategy_label", label: "strategy_label", layer: "telemetry", source: "producer field:strategy_label", nonNumeric: true, getter: function (step) { return scalarFieldPresent(step, ["strategy_label"]); } },
          { key: "tie_break_term", label: "tie_break_term", layer: "telemetry", source: "producer field:selected_action.decision_components.tie_break_term", getter: function (step) { return selectedDecisionComponent(step, "tie_break_term"); } },
          { key: "decision_score_selected", label: "decision_score_selected", layer: "telemetry", source: "producer field:real_decision_score | selected_action.real_decision_score", getter: function (step) { return numberFieldProducerAware(step, { topLevelKeys: ["decision_score_selected", "real_decision_score"], decisionComponentKeys: ["real_decision_score", "final_score", "mcts_puct_score"], availabilityKeys: ["decision_score_selected_available"], sourceKeys: ["decision_score_selected_source"] }); } },
          { key: "unit_prefilter_enabled", label: "unit_prefilter_enabled", layer: "telemetry", source: "producer field:unit_prefilter_enabled", getter: function (step) { return numberField(step, "unit_prefilter_enabled"); } },
          { key: "unit_prefilter_constrained_count", label: "unit_prefilter_constrained_count", layer: "telemetry", source: "producer field:unit_prefilter_constrained_count", getter: function (step) { return numberField(step, "unit_prefilter_constrained_count"); } },
          { key: "unit_prefilter_global_count", label: "unit_prefilter_global_count", layer: "telemetry", source: "producer field:unit_prefilter_global_count", getter: function (step) { return numberField(step, "unit_prefilter_global_count"); } },
          { key: "unit_prefilter_selected_unit_id", label: "unit_prefilter_selected_unit_id", layer: "telemetry", source: "producer field:unit_prefilter_selected_unit_id", nonNumeric: true, getter: function (step) { return scalarFieldPresent(step, ["unit_prefilter_selected_unit_id"]); } },
        ];
        const expectedStructuralChannelKeys = new Set([
          "obs_unit_position",
          "obs_unit_hp_map",
          "obs_unit_alive_map",
          "obs_vp_map",
          "obs_enemy_vp_threat_map",
          "obs_terrain_type_map",
          "obs_terrain_cover_map",
          "obs_terrain_los_block_map",
          "obs_terrain_move_cost_map",
          "obs_fortification_type_map",
          "obs_fortification_edge_map",
          "obs_reachable_hex_mask_by_unit",
          "obs_attackable_hex_mask_by_unit",
          "obs_vp_ownership_ttl",
          "obs_unit_side",
          "strategy_label",
          "unit_prefilter_selected_unit_id",
        ]);
        const expectedChannelOrder = [
          "obs_unit_position",
          "obs_unit_hp_map",
          "obs_unit_alive_map",
          "obs_vp_map",
          "obs_enemy_vp_threat_map",
          "obs_terrain_type_map",
          "obs_terrain_cover_map",
          "obs_terrain_los_block_map",
          "obs_terrain_move_cost_map",
          "obs_fortification_type_map",
          "obs_fortification_edge_map",
          "obs_reachable_hex_mask_by_unit",
          "obs_attackable_hex_mask_by_unit",
          "obs_vp_ownership_ttl",
          "obs_enemy_reaction_fire_risk",
          "obs_unit_side",
          "mcts_prior",
          "mcts_q_value",
          "mcts_u_value",
          "vp_progress",
          "mcts_success_prob_proxy",
          "mcts_success_component",
          "vp_horizon_steps",
          "vp_horizon_signal",
          "vp_horizon_component",
          "vp_horizon_decision_component",
          "objective_soft_reward_component",
          "global_strategy_soft_reward_component",
          "reaction_fire_soft_reward_component",
          "reaction_exposure_component",
          "strategy_label",
          "tie_break_term",
          "decision_score_selected",
          "unit_prefilter_enabled",
          "unit_prefilter_constrained_count",
          "unit_prefilter_global_count",
          "unit_prefilter_selected_unit_id",
        ];
        const decisionChannelDependencyMap = [
          {
            channel: "decision_score_selected",
            compute_path: "agents/efficientzero_v2/core/mcts.py::final_score (producer field:real_decision_score | selected_action.real_decision_score)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "eval telemetry only",
            notes: "Expected finite scalar; valid 0 when terms offset to neutral score.",
          },
          {
            channel: "mcts_prior",
            compute_path: "agents/efficientzero_v2/core/mcts.py::_puct_score (producer field:mcts_prior | mcts_action_candidates[].policy_prior)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Policy prior in [0,1]; valid 0 for pruned/very low-prior actions.",
          },
          {
            channel: "mcts_q_value (mcts_q)",
            compute_path: "agents/efficientzero_v2/core/mcts.py::_puct_score (producer field:mcts_q_value | mcts_action_candidates[].mcts_q_value)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Q term can be negative/positive; valid 0 for neutral expectation.",
          },
          {
            channel: "mcts_u_value (mcts_u)",
            compute_path: "agents/efficientzero_v2/core/mcts.py::_puct_score (producer field:mcts_u_value | mcts_action_candidates[].mcts_u_value)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Exploration bonus usually >=0; valid 0 when fully exploited/low prior.",
          },
          {
            channel: "mcts_success_component",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_success_component (producer field:mcts_success_component)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Auxiliary decision term; valid 0 when no success signal applies.",
          },
          {
            channel: "mcts_success_prob_proxy",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_success_prob_proxy (producer field:mcts_success_prob_proxy)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Proxy probability in [0,1] nominally; valid 0 indicates no immediate success path.",
          },
          {
            channel: "reaction_fire_soft_reward_component",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_reaction_fire_soft_reward_component (producer field:reaction_fire_soft_reward_component)",
            injection_point: "reward",
            effect_type: "indirect via reward",
            train_eval_scope: "train+eval",
            notes: "Shaping reward component; valid 0 when risk is absent/disabled.",
          },
          {
            channel: "reaction_exposure_component",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_reaction_exposure_component (producer field:reaction_exposure_component)",
            injection_point: "reward",
            effect_type: "indirect via reward",
            train_eval_scope: "train+eval",
            notes: "Exposure/risk shaping term; valid 0 in safe or non-applicable states.",
          },
          {
            channel: "vp_horizon_steps",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_vp_horizon_component (producer field:vp_horizon_steps)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Step horizon >=0 expected; valid 0 means immediate horizon/no lookahead.",
          },
          {
            channel: "vp_horizon_signal",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_vp_horizon_component (producer field:vp_horizon_signal)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Normalized horizon signal; valid 0 means no VP-progress evidence.",
          },
          {
            channel: "vp_horizon_component",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_vp_horizon_component (producer field:vp_horizon_component)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Decision component added to score; valid 0 when disabled or neutral.",
          },
          {
            channel: "vp_horizon_decision_component",
            compute_path: "agents/efficientzero_v2/core/mcts.py::decision_components.vp_horizon_decision_component (producer field:vp_horizon_decision_component)",
            injection_point: "telemetry",
            effect_type: "telemetry only",
            train_eval_scope: "eval telemetry only",
            notes: "Diagnostic mirror of vp_horizon term; valid 0 when no horizon bonus applied.",
          },
          {
            channel: "tie_break_term",
            compute_path: "agents/efficientzero_v2/core/mcts.py::_break_score_tie (producer field:selected_action.decision_components.tie_break_term)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "eval telemetry only",
            notes: "Small epsilon tie-breaker around 0; valid 0 when no tie-break needed.",
          },
          {
            channel: "vp_progress",
            compute_path: "agents/efficientzero_v2/core/objective_signals.py::compute_vp_progress (producer field:vp_progress)",
            injection_point: "score",
            effect_type: "direct MCTS",
            train_eval_scope: "train+eval",
            notes: "Progress delta signal; valid 0 for flat VP state transitions.",
          },
        ];
        const channelByKey = {};
        for (const ch of channels) {
          if (!ch || !ch.key) continue;
          channelByKey[String(ch.key)] = ch;
        }
        const stableChannels = [];
        for (const key of expectedChannelOrder) {
          const existing = channelByKey[key];
          if (existing) {
            stableChannels.push({
              ...existing,
              nonNumeric: expectedStructuralChannelKeys.has(key) || !!existing.nonNumeric,
              label: String(existing.label || existing.key || key),
              key: String(existing.key || key),
            });
            continue;
          }
          stableChannels.push({
            key: key,
            label: key,
            layer: "telemetry",
            source: "producer field:" + key,
            nonNumeric: expectedStructuralChannelKeys.has(key),
            getter: function () { return null; },
          });
        }
        for (const ch of channels) {
          if (!ch || !ch.key) continue;
          const key = String(ch.key);
          if (expectedChannelOrder.indexOf(key) >= 0) continue;
          stableChannels.push({
            ...ch,
            nonNumeric: expectedStructuralChannelKeys.has(key) || !!ch.nonNumeric,
            label: String(ch.label || key),
            key: key,
          });
        }
        const channelsStable = stableChannels;
        function hasOwn(src, key) {
          return !!src && typeof src === "object" && Object.prototype.hasOwnProperty.call(src, key);
        }
        function numberField(src, key) {
          if (!hasOwn(src, key)) return null;
          const n = Number(src[key]);
          return Number.isFinite(n) ? n : null;
        }
        function scalarFieldPresent(src, keys) {
          const keyList = Array.isArray(keys) ? keys : [];
          for (const key of keyList) {
            if (!hasOwn(src, key)) continue;
            const raw = src[key];
            if (raw === null || raw === undefined) continue;
            if (typeof raw === "string" && raw.trim() === "") continue;
            return true;
          }
          return false;
        }
        function containerFieldPresent(src, keys) {
          const keyList = Array.isArray(keys) ? keys : [];
          for (const key of keyList) {
            if (!hasOwn(src, key)) continue;
            const raw = src[key];
            if (Array.isArray(raw)) return true;
            if (raw && typeof raw === "object") return true;
          }
          return false;
        }
        function selectedCandidate(step) {
          const candidates = Array.isArray(step && step.mcts_action_candidates)
            ? step.mcts_action_candidates
            : [];
          const src = candidates;
          if (!src.length) return null;
          const chosenActionId = String(
            (step && step.why_action_vs_vp && step.why_action_vs_vp.chosen_action_id)
            || (step && step.chosen_action_id)
            || (step && step.selected_action_id)
            || (step && step.action_id)
            || ""
          );
          const selected = src.find(function (c) {
            return c && (c.selected_action === true || String(c.action_id || "") === chosenActionId);
          });
          if (selected) return selected;
          return src[0] || null;
        }
        function selectedCandidateField(step, key) {
          const selected = selectedCandidate(step);
          if (!selected) return null;
          let raw = null;
          if (hasOwn(selected, key)) raw = selected[key];
          if (raw === null || raw === undefined) return null;
          const n = Number(raw);
          return Number.isFinite(n) ? n : null;
        }
        function selectedDecisionComponent(step, key) {
          const topLevelBlock = (step && step.decision_components && typeof step.decision_components === "object")
            ? step.decision_components
            : null;
          const selected = selectedCandidate(step);
          const selectedBlock = (selected && selected.decision_components && typeof selected.decision_components === "object")
            ? selected.decision_components
            : null;
          const block = (topLevelBlock && hasOwn(topLevelBlock, key))
            ? topLevelBlock
            : selectedBlock;
          if (!block || !hasOwn(block, key)) return null;
          const n = Number(block[key]);
          return Number.isFinite(n) ? n : null;
        }
        function numberFieldMulti(step, topLevelKeys, decisionComponentKeys) {
          const topKeys = Array.isArray(topLevelKeys) ? topLevelKeys : [];
          for (const key of topKeys) {
            const n = numberField(step, key);
            if (n !== null) return n;
          }
          const dcKeys = Array.isArray(decisionComponentKeys) ? decisionComponentKeys : [];
          for (const key of dcKeys) {
            const n = selectedDecisionComponent(step, key);
            if (n !== null) return n;
          }
          return null;
        }
        function isMissingSourceTag(sourceText) {
          const s = String(sourceText || "").trim().toLowerCase();
          return !!s && (s.indexOf("missing") >= 0 || s.indexOf("fallback") >= 0 || s.indexOf("default") >= 0);
        }
        function numberFieldProducerAware(step, cfg) {
          const c = cfg || {};
          const availKeys = Array.isArray(c.availabilityKeys) ? c.availabilityKeys : [];
          for (const key of availKeys) {
            if (Object.prototype.hasOwnProperty.call(step || {}, key) && !step[key]) return null;
          }
          const sourceKeys = Array.isArray(c.sourceKeys) ? c.sourceKeys : [];
          for (const key of sourceKeys) {
            if (Object.prototype.hasOwnProperty.call(step || {}, key) && isMissingSourceTag(step[key])) return null;
          }
          return numberFieldMulti(
            step,
            Array.isArray(c.topLevelKeys) ? c.topLevelKeys : [],
            Array.isArray(c.decisionComponentKeys) ? c.decisionComponentKeys : [],
          );
        }
        function telemetryStepsFromResult(resultRow) {
          const games = Array.isArray(resultRow && resultRow.match_games) ? resultRow.match_games : [];
          const fromMatchGames = [];
          for (let gi = 0; gi < games.length; gi += 1) {
            const transitions = Array.isArray((games[gi] && games[gi].transitions)) ? games[gi].transitions : [];
            for (let si = 0; si < transitions.length; si += 1) {
              const step = transitions[si];
              if (step && typeof step === "object") fromMatchGames.push(step);
            }
          }
          if (fromMatchGames.length > 0) {
            return { source: "match_games.transitions", steps: fromMatchGames };
          }
          const fallback = Array.isArray(resultRow && resultRow.eval_decision_steps_top)
            ? resultRow.eval_decision_steps_top
            : [];
          const fromFallback = fallback.filter(function (step) { return step && typeof step === "object"; });
          if (fromFallback.length > 0) {
            return { source: "eval_decision_steps_top", steps: fromFallback };
          }
          return { source: "none", steps: [] };
        }
        const channelBuckets = {};
        for (const ch of channelsStable) {
          channelBuckets[ch.label] = {
            seen: 0,
            nonzero: 0,
            abs: [],
            pos: 0,
            neg: 0,
            zero: 0,
            totalRows: 0,
            nonNumeric: !!ch.nonNumeric,
          };
        }
        const perStepRows = [];
        const debug = {
          artifactPaths: {},
          evalIds: {},
          evalRows: 0,
          matchedResults: 0,
          stepRows: 0,
          candidateRows: 0,
          rowsWithDecisionComponents: 0,
          sourceStepCounts: {
            "match_games.transitions": 0,
            "eval_decision_steps_top": 0,
            "none": 0,
          },
        };
        const qualityStats = {
          rows: 0,
          q_clip_hits: 0,
          entropy_collapse_hits: 0,
          low_active_actions_hits: 0,
        };
        function p95(values) {
          const arr = (Array.isArray(values) ? values : []).filter(function (x) { return Number.isFinite(Number(x)); }).map(Number).sort((a, b) => a - b);
          if (!arr.length) return null;
          const idx = Math.max(0, Math.min(arr.length - 1, Math.floor(0.95 * (arr.length - 1))));
          return arr[idx];
        }
        function fmtPctOrNa(v) {
          const n = Number(v);
          return Number.isFinite(n) ? ((n * 100).toFixed(1) + "%") : "N/A";
        }
        function fmtNum(v, digits) {
          const n = Number(v);
          const d = Number.isFinite(Number(digits)) ? Math.max(0, Math.min(6, Number(digits))) : 3;
          return Number.isFinite(n) ? n.toFixed(d) : "N/A";
        }
        debug.evalRows = sourceRows.length;
        for (const er of sourceRows) {
          const evalId = String((er && er.eval_id) || "");
          if (evalId) debug.evalIds[evalId] = true;
          const sourcePath = String((er && er.source_path) || "");
          if (sourcePath) debug.artifactPaths[sourcePath] = true;
          const results = Array.isArray(er && er.results) ? er.results : [];
          for (const r of results) {
            if (!r || typeof r !== "object") continue;
            const sidesLocal = collectSidesFromResult(r);
            const sidePass = (selectedSide === "__all__" && selectedController === "__all__")
              || (Array.isArray(sidesLocal) && sidesLocal.some(function (s) { return sideAllowedFn(r, s, selectedSide, selectedController); }));
            if (!sidePass) continue;
            debug.matchedResults += 1;
            const sourceBundle = telemetryStepsFromResult(r);
            const sourceKey = String(sourceBundle.source || "none");
            if (!Object.prototype.hasOwnProperty.call(debug.sourceStepCounts, sourceKey)) {
              debug.sourceStepCounts[sourceKey] = 0;
            }
            const steps = Array.isArray(sourceBundle.steps) ? sourceBundle.steps : [];
            debug.sourceStepCounts[sourceKey] += steps.length;
            for (let si = 0; si < steps.length; si += 1) {
              const step = steps[si];
              const stepSide = String(step.unit_side || step.to_play || "");
              if (!sideAllowedFn(r, stepSide, selectedSide, selectedController)) continue;
              debug.stepRows += 1;
              qualityStats.rows += 1;
              if (Number(step.mcts_q_guardrail_clipped_count || 0) > 0) qualityStats.q_clip_hits += 1;
              if (step.mcts_entropy_collapse === true) qualityStats.entropy_collapse_hits += 1;
              if (Number.isFinite(Number(step.mcts_active_actions)) && Number(step.mcts_active_actions) <= 1) {
                qualityStats.low_active_actions_hits += 1;
              }
              const candidates = Array.isArray(step.mcts_action_candidates) ? step.mcts_action_candidates : [];
              debug.candidateRows += candidates.length;
              const selected = selectedCandidate(step);
              if (selected && selected.decision_components && typeof selected.decision_components === "object") {
                debug.rowsWithDecisionComponents += 1;
              }
              for (const ch of channelsStable) {
                const bucket = channelBuckets[ch.label];
                bucket.totalRows += 1;
                const raw = ch.getter(step);
                if (raw === null || raw === false || raw === undefined) continue;
                bucket.seen += 1;
                if (bucket.nonNumeric) continue;
                const absVal = Math.abs(Number(raw));
                bucket.abs.push(absVal);
                if (absVal > 1e-12) bucket.nonzero += 1;
                if (Number(raw) > 1e-12) bucket.pos += 1;
                else if (Number(raw) < -1e-12) bucket.neg += 1;
                else bucket.zero += 1;
              }
              if (perStepRows.length < 20) {
                const rowPreview = {
                  eval_id: String(er.eval_id || ""),
                  step: Number(step.step || si),
                  action_id: String(step.action_id || ""),
                  unit_side: String(step.unit_side || step.to_play || ""),
                };
                for (const ch of channelsStable) {
                  rowPreview[ch.label] = ch.getter(step);
                }
                perStepRows.push(rowPreview);
              }
            }
          }
        }
        const sourcePathKeys = Object.keys(debug.artifactPaths);
        const evalIdCount = Object.keys(debug.evalIds).length;
        const sourcePreview = sourcePathKeys.length
          ? (sourcePathKeys.slice(0, 2).join(" ; ") + (sourcePathKeys.length > 2 ? (" ; +" + String(sourcePathKeys.length - 2) + " more") : ""))
          : "none";
        const sourceCountsText = Object.keys(debug.sourceStepCounts)
          .map(function (k) { return String(k) + ":" + String(Number(debug.sourceStepCounts[k] || 0)); })
          .join(", ");
        const qsDen = Math.max(1, Number(qualityStats.rows || 0));
        const qualityRows = [
          ["q_clip_rows_rate", fmtPctOrNa(Number(qualityStats.q_clip_hits || 0) / qsDen), "High values indicate Q clipping/saturation pressure."],
          ["entropy_collapse_rows_rate", fmtPctOrNa(Number(qualityStats.entropy_collapse_hits || 0) / qsDen), "High values indicate root visit distribution collapse."],
          ["active_actions_le_1_rate", fmtPctOrNa(Number(qualityStats.low_active_actions_hits || 0) / qsDen), "High values indicate weak exploration breadth."],
        ];
        const qualityBody = qualityRows.map(function (row) {
          return "<tr>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[0]) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[1]) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[2]) + "</td>" +
            "</tr>";
        }).join("");
        const channelMapRows = channelsStable.map(function (ch) {
          const b = channelBuckets[ch.label] || {};
          const seen = Number(b.seen || 0);
          const total = Number(b.totalRows || 0);
          const coverage = total > 0 ? (seen / total) : null;
          const absMean = seen > 0 && !b.nonNumeric ? (b.abs.reduce((acc, x) => acc + Number(x || 0), 0) / seen) : null;
          const absP95 = seen > 0 && !b.nonNumeric ? p95(b.abs) : null;
          let status = "missing";
          if (coverage !== null && coverage >= 0.999) status = "ok";
          else if (coverage !== null && coverage > 0) status = "partial";
          return {
            channel_name: ch.label,
            layer: ch.layer,
            source: ch.source,
            availability: fmtPctOrNa(coverage),
            mean_abs: b.nonNumeric ? "N/A (non-numeric)" : (seen > 0 ? fmtNum(absMean) : "N/A"),
            p95_abs: b.nonNumeric ? "N/A (non-numeric)" : (seen > 0 ? fmtNum(absP95) : "N/A"),
            status: status,
          };
        });
        const channelMetaByLabel = {};
        for (const ch of channelsStable) {
          channelMetaByLabel[String(ch.label || "")] = ch || {};
        }
        function buildNumericRowsByLayer(layerName) {
          return Object.keys(channelBuckets).sort().map(function (label) {
            const b = channelBuckets[label] || {};
            if (b.nonNumeric) return null;
            const meta = channelMetaByLabel[String(label)] || {};
            if (String(meta.layer || "") !== String(layerName || "")) return null;
            const seen = Number(b.seen || 0);
            const total = Number(b.totalRows || 0);
            const missingRows = Math.max(0, total - seen);
            const absMean = seen > 0 ? (b.abs.reduce((acc, x) => acc + Number(x || 0), 0) / seen) : null;
            const absP95 = p95(b.abs);
            const nonzeroRate = seen > 0 ? (Number(b.nonzero || 0) / seen) : null;
            const signKnown = seen > 0
              ? ("+ " + fmtPctOrNa(Number(b.pos || 0) / seen) + " / - " + fmtPctOrNa(Number(b.neg || 0) / seen) + " / 0 " + fmtPctOrNa(Number(b.zero || 0) / seen))
              : "N/A (missing producer fields)";
            const producerNote = total > 0 && seen <= 0
              ? "missing producer fields"
              : (missingRows > 0 ? ("partial coverage: missing " + String(missingRows) + " rows") : "ok");
            return [label, seen > 0 ? fmtPctOrNa(nonzeroRate) : "N/A", seen > 0 ? fmtNum(absMean) : "N/A", seen > 0 ? fmtNum(absP95) : "N/A", signKnown, producerNote];
          }).filter(Boolean);
        }
        const summaryRowsNumericDecision = buildNumericRowsByLayer("decision");
        const summaryRowsNumericTelemetry = buildNumericRowsByLayer("telemetry");
        const summaryRowsNumericInput = buildNumericRowsByLayer("input");
        const summaryRowsStructural = Object.keys(channelBuckets).sort().map(function (label) {
          const b = channelBuckets[label] || {};
          if (!b.nonNumeric) return null;
          const seen = Number(b.seen || 0);
          const total = Number(b.totalRows || 0);
          const coverage = total > 0 ? (seen / total) : null;
          const missingRows = Math.max(0, total - seen);
          const producerNote = total > 0 && seen <= 0
            ? "missing producer fields"
            : (missingRows > 0 ? ("partial coverage: missing " + String(missingRows) + " rows") : "ok");
          return [label, fmtPctOrNa(coverage), String(seen), String(total), producerNote];
        }).filter(Boolean);
        const channelMapBody = channelMapRows.length
          ? channelMapRows.map(function (row) {
            const statusTxt = String(row.status || "missing");
            const statusClass = statusTxt === "ok" ? "ok-text" : (statusTxt === "partial" ? "degraded-text" : "na-text");
            return "<tr class='channel-map-row status-" + esc(String(row.status || "missing")) + "'>" +
              "<td style='border:1px solid #334155;padding:6px;'><code>" + esc(row.channel_name) + "</code></td>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.layer) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.source) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'><span class='" + esc(statusClass) + "'>" + esc(row.availability) + "</span></td>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.mean_abs) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.p95_abs) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'><span class='" + esc(statusClass) + "'>" + esc(row.status) + "</span></td>" +
            "</tr>";
          }).join("")
          : "<tr><td colspan='7' style='border:1px solid #334155;padding:6px;' class='muted'>No eval channel rows for current filters.</td></tr>";
        function renderNumericSummaryBody(summaryRowsNumeric) {
          return summaryRowsNumeric.length
            ? summaryRowsNumeric.map(function (row) {
              const coverageNote = String(row[5] || "");
              const rowClass = coverageNote === "ok" ? "ok-text" : (coverageNote.indexOf("partial coverage") >= 0 ? "degraded-text" : "na-text");
              return "<tr>" +
                "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[0]) + "</td>" +
                "<td style='border:1px solid #334155;padding:6px;'><span class='" + esc(rowClass) + "'>" + esc(row[1]) + "</span></td>" +
                "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[2]) + "</td>" +
                "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[3]) + "</td>" +
                "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[4]) + "</td>" +
                "<td style='border:1px solid #334155;padding:6px;'><span class='" + esc(rowClass) + "'>" + esc(row[5]) + "</span></td>" +
              "</tr>";
            }).join("")
            : "<tr><td colspan='6' style='border:1px solid #334155;padding:6px;' class='muted'>No numeric channels for current filters.</td></tr>";
        }
        const summaryBodyNumericDecision = renderNumericSummaryBody(summaryRowsNumericDecision);
        const summaryBodyNumericTelemetry = renderNumericSummaryBody(summaryRowsNumericTelemetry);
        const summaryBodyNumericInput = renderNumericSummaryBody(summaryRowsNumericInput);
        const summaryBodyStructural = summaryRowsStructural.length
          ? summaryRowsStructural.map(function (row) {
            const coverageNote = String(row[4] || "");
            const rowClass = coverageNote === "ok" ? "ok-text" : (coverageNote.indexOf("partial coverage") >= 0 ? "degraded-text" : "na-text");
            return "<tr>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[0]) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'><span class='" + esc(rowClass) + "'>" + esc(row[1]) + "</span></td>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[2]) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'>" + esc(row[3]) + "</td>" +
              "<td style='border:1px solid #334155;padding:6px;'><span class='" + esc(rowClass) + "'>" + esc(row[4]) + "</span></td>" +
            "</tr>";
          }).join("")
          : "<tr><td colspan='5' style='border:1px solid #334155;padding:6px;' class='muted'>No structural/non-numeric channels for current filters.</td></tr>";
        const channelByLabel = {};
        for (const ch of channelsStable) channelByLabel[ch.label] = ch;
        const stepColumns = ["eval_id", "step", "unit_side", "action_id"].concat(channelsStable.map(function (ch) { return ch.label; }));
        function formatPerStepCell(rowObj, colKey) {
          if (colKey === "eval_id" || colKey === "action_id" || colKey === "unit_side") return String(rowObj[colKey] || "");
          if (colKey === "step") return String(Number(rowObj.step || 0));
          const ch = channelByLabel[colKey] || null;
          const raw = rowObj[colKey];
          if (!ch) return (raw === null || raw === undefined || raw === "") ? "N/A" : String(raw);
          if (ch.nonNumeric) {
            if (raw === null || raw === undefined || raw === false) return "N/A";
            return "present";
          }
          const n = Number(raw);
          return Number.isFinite(n) ? fmtNum(n, 3) : "N/A";
        }
        const stepBody = perStepRows.length
          ? perStepRows.map(function (r) {
            return "<tr>" + stepColumns.map(function (colKey) {
              return "<td style='border:1px solid #334155;padding:6px;'>" + esc(formatPerStepCell(r, colKey)) + "</td>";
            }).join("") + "</tr>";
          }).join("")
          : "<tr><td colspan='" + String(stepColumns.length) + "' style='border:1px solid #334155;padding:6px;' class='muted'>No per-step telemetry rows for current filters.</td></tr>";
        const dependencyMapBody = decisionChannelDependencyMap.map(function (row) {
          return "<tr>" +
            "<td style='border:1px solid #334155;padding:6px;'><code>" + esc(row.channel) + "</code></td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.compute_path) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.injection_point) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.effect_type) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.train_eval_scope) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(row.notes) + "</td>" +
          "</tr>";
        }).join("");
        host.innerHTML =
          "<div class='muted' style='margin-bottom:6px;'><b>Debug:</b> source_artifacts=" + esc(sourcePreview) +
          " | eval_rows=" + esc(String(debug.evalRows)) +
          " | eval_ids=" + esc(String(evalIdCount)) +
          " | matched_results=" + esc(String(debug.matchedResults)) +
          " | step_rows=" + esc(String(debug.stepRows)) +
          " | candidate_rows=" + esc(String(debug.candidateRows)) +
          " | rows_with_decision_components=" + esc(String(debug.rowsWithDecisionComponents)) +
          " | step_source_counts=" + esc(sourceCountsText) + "</div>" +
          "<div class='muted' style='margin-bottom:6px;'>Producer-first contract: missing channels are shown as N/A with explicit missing producer notes.</div>" +
          "<h3 style='margin:8px 0;'>Signal Quality Alarms</h3>" +
          "<table style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>alarm</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>rate</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>interpretation</th>" +
          "</tr></thead><tbody>" + qualityBody + "</tbody></table>" +
          "<h3 style='margin:8px 0;'>Channel Map</h3>" +
          "<div class='muted' style='margin-bottom:6px;'>Filter-aware map across input, decision, and telemetry channels. Missing producer fields stay explicit as <b>missing</b>.</div>" +
          "<table id='evalChannelMapTable' class='eval-channel-map' style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>channel_name</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>layer/type</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>source</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>availability coverage</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>mean abs</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>p95 abs</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>status</th>" +
          "</tr></thead><tbody>" + channelMapBody + "</tbody></table>" +
          "<h3 style='margin:8px 0;'>Channel usage diagnostics - Decision channels</h3>" +
          "<table style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>channel</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>nonzero usage rate</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>mean |term|</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>p95 |term|</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>sign distribution</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>producer coverage</th>" +
          "</tr></thead><tbody>" + summaryBodyNumericDecision + "</tbody></table>" +
          "<h3 style='margin:8px 0;'>Channel usage diagnostics - Telemetry channels</h3>" +
          "<table style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>channel</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>nonzero usage rate</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>mean |term|</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>p95 |term|</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>sign distribution</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>producer coverage</th>" +
          "</tr></thead><tbody>" + summaryBodyNumericTelemetry + "</tbody></table>" +
          "<h3 style='margin:8px 0;'>Channel usage diagnostics - Input numeric channels</h3>" +
          "<table style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>channel</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>nonzero usage rate</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>mean |term|</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>p95 |term|</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>sign distribution</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>producer coverage</th>" +
          "</tr></thead><tbody>" + summaryBodyNumericInput + "</tbody></table>" +
          "<h3 style='margin:8px 0;'>Channel usage diagnostics - Structural channels</h3>" +
          "<div class='muted' style='margin-bottom:6px;'>Structural/input channels are analyzed by presence/coverage, not numeric magnitude.</div>" +
          "<table style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>channel</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>availability coverage</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>rows present</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>rows total</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>producer coverage</th>" +
          "</tr></thead><tbody>" + summaryBodyStructural + "</tbody></table>" +
          "<h3 style='margin:12px 0 8px 0;'>Decision Channel Dependency Map</h3>" +
          "<div class='muted' style='margin-bottom:6px;'>Deterministic architecture map for decision channels: channel -> compute path -> injection point -> effect.</div>" +
          "<table id='decisionDependencyMapTable' style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          "<th style='border:1px solid #334155;padding:6px;'>channel</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>compute function/path</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>injection point</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>effect type</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>train vs eval</th>" +
          "<th style='border:1px solid #334155;padding:6px;'>notes</th>" +
          "</tr></thead><tbody>" + dependencyMapBody + "</tbody></table>" +
          "<h3 style='margin:12px 0 8px 0;'>Latest per-step channel rows</h3>" +
          "<table style='width:100%;border-collapse:collapse;font-size:12px;'><thead><tr>" +
          stepColumns.map(function (key) {
            const label = key === "unit_side" ? "side" : key;
            return "<th style='border:1px solid #334155;padding:6px;'>" + esc(label) + "</th>";
          }).join("") +
          "</tr></thead><tbody>" + stepBody + "</tbody></table>";
      }
      function renderHeadDiagnostics(evalRowsForTabs) {
        const root = document.getElementById("headDiagnosticsRoot");
        if (!root) return;
        function isMetricOkValue(v) {
          if (v === null || v === undefined) return false;
          if (typeof v === "string") {
            const t = v.trim();
            if (!t) return false;
            if (t.toUpperCase() === "N/A") return false;
            return true;
          }
          if (typeof v === "number") return Number.isFinite(v);
          return true;
        }
        function metricStatus(v, opts) {
          const o = opts || {};
          if (!isMetricOkValue(v)) return "na";
          if (Array.isArray(o.degradedSources) && o.degradedSources.includes(String(v))) return "degraded";
          return "ok";
        }
        function metricValueHtml(v, opts) {
          const st = metricStatus(v, opts);
          const txt = (v === null || v === undefined || v === "") ? "N/A" : String(v);
          if (st === "ok") return '<span class="ok-text">' + esc(txt) + "</span>";
          if (st === "degraded") return '<span class="degraded-text">' + esc(txt) + "</span>";
          return '<span class="na-text">' + esc(txt) + "</span>";
        }
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
          let overrideSignalRows = 0;
          let unknownOverrideRows = 0;
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
                if (!ownershipBySide[side]) ownershipBySide[side] = { side: side, rows: 0, policy_kept: 0, overwritten: 0, override_signal_rows: 0, unknown_override_rows: 0 };
                const src = own[side] || {};
                ownershipBySide[side].rows += Number(src.rows || 0);
                ownershipBySide[side].policy_kept += Number(src.policy_kept || 0);
                ownershipBySide[side].overwritten += Number(src.overwritten || 0);
                ownershipBySide[side].override_signal_rows += Number(src.override_signal_rows || 0);
                ownershipBySide[side].unknown_override_rows += Number(src.unknown_override_rows || 0);
              }
              const ownSource = ((r || {}).eval_decision_summary || {}).decision_ownership_source || {};
              overrideSignalRows += Number(ownSource.override_signal_rows || 0);
              unknownOverrideRows += Number(ownSource.unknown_override_rows || 0);
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
                String(Math.round(Number(x.unknown_override_rows || 0))),
              ];
            });
          return {
            topPolicyActions: topPolicyActions,
            mctsOwnershipRows: mctsOwnershipRows,
            ownershipSourceSummary: {
              override_signal_rows: Math.round(overrideSignalRows),
              unknown_override_rows: Math.round(unknownOverrideRows),
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
              if (c && typeof c === "object" && c.__html) {
                return '<td style="border:1px solid #334155;padding:6px;">' + String(c.__html) + "</td>";
              }
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
            { __html: metricValueHtml(String(cov.status || "none"), { degradedSources: ["partial", "none", "unknown"] }) },
            String(Number(cov.available || 0)) + "/" + String(Number(cov.total || 0)),
            { __html: metricValueHtml(String(cov.reason || ""), { degradedSources: ["no eval telemetry for this head"] }) },
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
          '<div class="muted" style="margin-bottom:6px;">Use replay for step-level influence; ownership uses policy_overridden_by_mcts from current telemetry.</div>' +
          '<div class="muted" style="margin-bottom:6px;">Ownership source coverage: override_signal_rows=' + esc(String(intents.ownershipSourceSummary.override_signal_rows || 0)) + ', unknown_override_rows=' + esc(String(intents.ownershipSourceSummary.unknown_override_rows || 0)) + '</div>' +
          '<button id="headDiagOpenReplayBtn" style="padding:4px 8px;font-size:12px;">Open Match Replay (Decision Influence)</button>' +
          intentTable(
            "MCTS decision ownership by side",
            ["side", "rows", "policy_kept", "overwritten", "override_signal_rows", "unknown_override_rows"],
            intents.mctsOwnershipRows,
            "No MCTS ownership signals in eval diagnostics."
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
          ["eval_vp_immediate_capture_opportunity_steps (MOVE into capturable VP legal now)", fmtEvalNum(objectiveHeadMetric("eval_vp_immediate_capture_opportunity_steps"), 1)],
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
            ["vp_immediate_capture_opportunities (legal MOVE-into-VP window)", fmtEvalNum(objImmediateOpp, 1)],
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
          ["side", "rows", "policy_kept", "overwritten", "override_signal_rows", "unknown_override_rows"],
          intents.mctsOwnershipRows,
          "No MCTS ownership signals in eval diagnostics."
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
        const sourceRows = Array.isArray(filteredResultRows) ? filteredResultRows : [];
        const sideAllowedFn = (filterCtx && typeof filterCtx.sideAllowed === "function")
          ? filterCtx.sideAllowed
          : function () { return true; };
        const selectedSide = (filterCtx && filterCtx.side) || "__all__";
        const selectedController = (filterCtx && filterCtx.controller) || "__all__";
        function resultMatchesSideControllerFilters(resultRow) {
          if (selectedSide === "__all__" && selectedController === "__all__") return true;
          const sidesLocal = collectSidesFromResult(resultRow);
          if (!Array.isArray(sidesLocal) || !sidesLocal.length) return false;
          return sidesLocal.some(function (s) {
            return sideAllowedFn(resultRow, s, selectedSide, selectedController);
          });
        }
        const rowMap = {};
        const rowBySideMap = {};
        const colKeyMap = {};
        for (const er of sourceRows) {
          const results = Array.isArray(er.results) ? er.results : [];
          for (const r of results) {
            if (!r || typeof r !== "object") continue;
            const summary = (r && r.eval_decision_summary) || {};
            const by = summary.by_action_kind_and_side || {};
            for (const key of Object.keys(by || {})) {
              if (!Object.prototype.hasOwnProperty.call(by || {}, key)) continue;
              const src = by[key] || {};
              if (!src || typeof src !== "object") continue;
              const action = String(src.action_kind || "UNKNOWN");
              const side = String(src.unit_side || "UNK");
              if (!sideAllowedFn(r, side, selectedSide, selectedController)) continue;
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
              const colKey = side + "|" + ctrl;
              if (!colKeyMap[colKey]) colKeyMap[colKey] = { side: side, controller: ctrl };
            }
          }
        }
        const rows = Object.values(rowMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
        const rowsBySide = Object.values(rowBySideMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
        const colKeys = Object.keys(colKeyMap).sort((a, b) => {
          const aa = colKeyMap[a] || {};
          const bb = colKeyMap[b] || {};
          const sa = String(aa.side || "");
          const sb = String(bb.side || "");
          if (sa !== sb) return sa.localeCompare(sb);
          return String(aa.controller || "").localeCompare(String(bb.controller || ""));
        });
        const pivotMap = {};
        for (const row of rowsBySide) {
          const action = String(row.action || "UNKNOWN");
          const colKey = String(row.side || "UNK") + "|" + String(row.controller || "UNKNOWN");
          if (!pivotMap[action]) pivotMap[action] = {};
          pivotMap[action][colKey] = row;
        }
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
        html += '<h3 style="margin:12px 0 8px 0;">By Action x Side x Controller (Pivot)</h3>';
        html += '<div style="overflow-x:auto;"><table style="min-width:720px;width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;position:sticky;left:0;background:#0b1220;z-index:1;">action_kind</th>';
        for (const colKey of colKeys) {
          const colMeta = colKeyMap[colKey] || {};
          const label = String(colMeta.side || "UNK") + " x " + String(colMeta.controller || "UNKNOWN");
          html += '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">' + esc(label) + '</th>';
        }
        html += '</tr></thead><tbody>';
        if (!rows.length || !colKeys.length) {
          html += '<tr><td colspan="' + String(1 + colKeys.length) + '" style="border:1px solid #334155;padding:6px;" class="muted">No side/controller rows available.</td></tr>';
        } else {
          for (const actionRow of rows) {
            const action = String(actionRow.action || "UNKNOWN");
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;position:sticky;left:0;background:#0b1220;z-index:1;">' + esc(action) + '</td>';
            for (const colKey of colKeys) {
              const cell = ((pivotMap[action] || {})[colKey]) || null;
              if (!cell) {
                html += '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>';
              } else {
                html += '<td style="border:1px solid #334155;padding:6px;">' +
                  esc(String(cell.count || 0)) +
                  '<span class="muted"> | d:' + esc(Number(cell.damage || 0).toFixed(3)) + ' k:' + esc(Number(cell.kills || 0).toFixed(3)) + '</span>' +
                  '</td>';
              }
            }
            html += '</tr>';
          }
        }
        html += '</tbody></table></div>';
        const attackEff = {
          global: {},
          by_action_kind: {},
          by_unit: {},
          by_distance_bucket: {},
          by_cover_bucket: {},
          calibration_bins: {},
        };
        function metricFromStep(stepRow, keys, defaultValue) {
          const names = Array.isArray(keys) ? keys : [];
          for (const key of names) {
            if (!Object.prototype.hasOwnProperty.call(stepRow || {}, key)) continue;
            const raw = stepRow[key];
            if (raw === null || raw === undefined) continue;
            const n = Number(raw);
            if (Number.isFinite(n)) return n;
          }
          return Number(defaultValue || 0);
        }
        function distanceBucket(raw) {
          const v = Number(raw);
          if (!Number.isFinite(v) || v < 0) return "unknown";
          if (v < 1.5) return "0-1";
          if (v < 3.5) return "2-3";
          if (v < 6.5) return "4-6";
          return "7+";
        }
        function coverBucket(raw) {
          const v = Number(raw);
          if (!Number.isFinite(v) || v < 0) return "unknown";
          if (v < 0.25) return "low";
          if (v < 0.60) return "medium";
          return "high";
        }
        function probBucket(raw) {
          let p = Number(raw);
          if (!Number.isFinite(p)) p = 0;
          p = Math.max(0, Math.min(1, p));
          const lo = Math.floor(p * 5) / 5;
          const hi = Math.min(1, lo + 0.2);
          return "[" + lo.toFixed(1) + "," + hi.toFixed(1) + ")";
        }
        function isAttackLike(kindRaw) {
          const kind = String(kindRaw || "").trim().toUpperCase();
          return kind !== "" && kind !== "MOVE" && kind !== "WAIT" && kind !== "TIMEOUT" && kind !== "OPPORTUNITY_SKIP";
        }
        function mergeBucket(dst, src) {
          const out = Object.assign({}, dst || {});
          const keys = Object.keys(src || {});
          for (const k of keys) {
            const row = src[k] || {};
            const prev = out[k] || { count: 0 };
            const c0 = Number(prev.count || 0);
            const c1 = Number(row.count || 0);
            const den = c0 + c1;
            function mv(name) {
              const a = Number(prev[name] || 0);
              const b = Number(row[name] || 0);
              return den > 0 ? (((a * c0) + (b * c1)) / den) : 0;
            }
            out[k] = {
              count: den,
              empirical_expected_damage: mv("empirical_expected_damage"),
              damage_variance: mv("damage_variance"),
              exchange_win_rate: mv("exchange_win_rate"),
              attack_good_rate: mv("attack_good_rate"),
              attack_good_prob_mean: mv("attack_good_prob_mean"),
              attack_good_brier: mv("attack_good_brier"),
            };
          }
          return out;
        }
        function mergeAttackEffSummary(summaryEff) {
          const eff = summaryEff || {};
          const g = (eff && eff.global) || {};
          const gx = Number(g.count || 0);
          if (gx > 0) {
            const prevCount = Number(attackEff.global.count || 0);
            const nextCount = prevCount + gx;
            function wavg(prevVal, curVal) {
              const a = Number(prevVal || 0);
              const b = Number(curVal || 0);
              if (nextCount <= 0) return 0;
              return ((a * prevCount) + (b * gx)) / nextCount;
            }
            attackEff.global = {
              count: nextCount,
              empirical_expected_damage: wavg(attackEff.global.empirical_expected_damage, g.empirical_expected_damage),
              damage_variance: wavg(attackEff.global.damage_variance, g.damage_variance),
              exchange_win_rate: wavg(attackEff.global.exchange_win_rate, g.exchange_win_rate),
              attack_good_rate: wavg(attackEff.global.attack_good_rate, g.attack_good_rate),
              attack_good_prob_mean: wavg(attackEff.global.attack_good_prob_mean, g.attack_good_prob_mean),
              attack_good_brier: wavg(attackEff.global.attack_good_brier, g.attack_good_brier),
            };
          }
          attackEff.by_action_kind = mergeBucket(attackEff.by_action_kind, (eff && eff.by_action_kind) || {});
          attackEff.by_unit = mergeBucket(attackEff.by_unit, (eff && eff.by_unit) || {});
          attackEff.by_distance_bucket = mergeBucket(attackEff.by_distance_bucket, (eff && eff.by_distance_bucket) || {});
          attackEff.by_cover_bucket = mergeBucket(attackEff.by_cover_bucket, (eff && eff.by_cover_bucket) || {});
          const bins = (eff && eff.calibration_bins) || {};
          for (const k of Object.keys(bins)) {
            const row = bins[k] || {};
            const prev = attackEff.calibration_bins[k] || { count: 0, predicted_prob_mean: 0, empirical_attack_good_rate: 0, brier: 0 };
            const c0 = Number(prev.count || 0);
            const c1 = Number(row.count || 0);
            const den = c0 + c1;
            function bmv(name) {
              const a = Number(prev[name] || 0);
              const b = Number(row[name] || 0);
              return den > 0 ? (((a * c0) + (b * c1)) / den) : 0;
            }
            attackEff.calibration_bins[k] = {
              count: den,
              predicted_prob_mean: bmv("predicted_prob_mean"),
              empirical_attack_good_rate: bmv("empirical_attack_good_rate"),
              brier: bmv("brier"),
            };
          }
        }
        const attackAgg = {};
        const attackBins = {};
        function accAttackGroup(groupKey, dmg, kills, pGood, yGood) {
          if (!attackAgg[groupKey]) {
            attackAgg[groupKey] = {
              count: 0,
              damage_sum: 0,
              damage_sq_sum: 0,
              exchange_win_sum: 0,
              attack_good_label_sum: 0,
              attack_good_prob_sum: 0,
              brier_sum: 0,
            };
          }
          const g = attackAgg[groupKey];
          g.count += 1;
          g.damage_sum += Number(dmg || 0);
          g.damage_sq_sum += Number(dmg || 0) * Number(dmg || 0);
          g.exchange_win_sum += (Number(dmg || 0) > 0 || Number(kills || 0) > 0) ? 1 : 0;
          g.attack_good_label_sum += Number(yGood || 0);
          g.attack_good_prob_sum += Number(pGood || 0);
          g.brier_sum += (Number(pGood || 0) - Number(yGood || 0)) ** 2;
        }
        function accAttackBin(binKey, pGood, yGood) {
          if (!attackBins[binKey]) {
            attackBins[binKey] = { count: 0, prob_sum: 0, label_sum: 0, brier_sum: 0 };
          }
          const b = attackBins[binKey];
          b.count += 1;
          b.prob_sum += Number(pGood || 0);
          b.label_sum += Number(yGood || 0);
          b.brier_sum += (Number(pGood || 0) - Number(yGood || 0)) ** 2;
        }
        function finalizeAttackGroup(src) {
          const n = Number((src || {}).count || 0);
          if (n <= 0) {
            return {
              count: 0,
              empirical_expected_damage: 0,
              damage_variance: 0,
              exchange_win_rate: 0,
              attack_good_rate: 0,
              attack_good_prob_mean: 0,
              attack_good_brier: 0,
            };
          }
          const meanD = Number(src.damage_sum || 0) / n;
          const ex2 = Number(src.damage_sq_sum || 0) / n;
          return {
            count: n,
            empirical_expected_damage: meanD,
            damage_variance: Math.max(0, ex2 - (meanD * meanD)),
            exchange_win_rate: Number(src.exchange_win_sum || 0) / n,
            attack_good_rate: Number(src.attack_good_label_sum || 0) / n,
            attack_good_prob_mean: Number(src.attack_good_prob_sum || 0) / n,
            attack_good_brier: Number(src.brier_sum || 0) / n,
          };
        }
        let builtFromTransitions = false;
        for (const er of sourceRows) {
          const results = Array.isArray(er.results) ? er.results : [];
          for (const r of results) {
            if (!resultMatchesSideControllerFilters(r)) continue;
            const games = Array.isArray(r.match_games) ? r.match_games : [];
            let rowHasTransitions = false;
            for (const game of games) {
              const transitions = Array.isArray((game && game.transitions)) ? game.transitions : [];
              if (!transitions.length) continue;
              rowHasTransitions = true;
              for (const step of transitions) {
                const stepKind = String((step && step.action_kind) || "").trim().toUpperCase();
                if (!isAttackLike(stepKind)) continue;
                const stepSide = String((step && step.unit_side) || "").trim().toUpperCase() || "UNKNOWN";
                if (!sideAllowedFn(r, stepSide, selectedSide, selectedController)) continue;
                const dmg = metricFromStep(step, ["damage_dealt", "enemy_damage", "damage", "damage_sum"], 0);
                const kills = metricFromStep(step, ["kills_dealt", "enemy_kills", "kills", "kills_sum"], 0);
                let pGood = metricFromStep(step, ["chosen_action_prob", "policy_prior"], 0);
                pGood = Math.max(0, Math.min(1, pGood));
                const yGood = (dmg > 0 || kills > 0) ? 1 : 0;
                accAttackGroup("global", dmg, kills, pGood, yGood);
                accAttackGroup("kind::" + stepKind, dmg, kills, pGood, yGood);
                const unitKey = String((step && step.unit_label) || (step && step.unit_id) || "UNKNOWN");
                accAttackGroup("unit::" + unitKey, dmg, kills, pGood, yGood);
                accAttackGroup("distance::" + distanceBucket(step && step.attack_distance_mean), dmg, kills, pGood, yGood);
                accAttackGroup("cover::" + coverBucket(step && step.attack_target_cover_mean), dmg, kills, pGood, yGood);
                accAttackBin(probBucket(pGood), pGood, yGood);
                builtFromTransitions = true;
              }
            }
            if (!rowHasTransitions) {
              const summary = (r && r.eval_decision_summary) || {};
              mergeAttackEffSummary((summary && summary.attack_effectiveness) || {});
            }
          }
        }
        if (builtFromTransitions) {
          attackEff.global = finalizeAttackGroup(attackAgg.global || {});
          for (const key of Object.keys(attackAgg)) {
            const group = attackAgg[key] || {};
            if (String(key).indexOf("kind::") === 0) attackEff.by_action_kind[String(key).slice("kind::".length)] = finalizeAttackGroup(group);
            else if (String(key).indexOf("unit::") === 0) attackEff.by_unit[String(key).slice("unit::".length)] = finalizeAttackGroup(group);
            else if (String(key).indexOf("distance::") === 0) attackEff.by_distance_bucket[String(key).slice("distance::".length)] = finalizeAttackGroup(group);
            else if (String(key).indexOf("cover::") === 0) attackEff.by_cover_bucket[String(key).slice("cover::".length)] = finalizeAttackGroup(group);
          }
          for (const binKey of Object.keys(attackBins).sort()) {
            const src = attackBins[binKey] || {};
            const n = Number(src.count || 0);
            attackEff.calibration_bins[binKey] = {
              count: n,
              predicted_prob_mean: n > 0 ? (Number(src.prob_sum || 0) / n) : 0,
              empirical_attack_good_rate: n > 0 ? (Number(src.label_sum || 0) / n) : 0,
              brier: n > 0 ? (Number(src.brier_sum || 0) / n) : 0,
            };
          }
        }
        const g = attackEff.global || {};
        const hasAttackData = Number(g.count || 0) > 0;
        if (!hasAttackData) {
          html += '<div class="muted" style="margin:8px 0 6px 0;">No attack effectiveness rows for current filters.</div>';
        }
        html += '<h3 style="margin:12px 0 8px 0;">Attack Effectiveness (calibration)</h3>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">count</th>' +
          '<th style="border:1px solid #334155;padding:6px;">E[dmg]</th>' +
          '<th style="border:1px solid #334155;padding:6px;">Var[dmg]</th>' +
          '<th style="border:1px solid #334155;padding:6px;">exchange_win_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">attack_good_rate</th>' +
          '<th style="border:1px solid #334155;padding:6px;">pred_attack_good_mean</th>' +
          '<th style="border:1px solid #334155;padding:6px;">Brier</th>' +
          '</tr></thead><tbody>';
        if (!hasAttackData) {
          html += '<tr><td colspan="7" style="border:1px solid #334155;padding:6px;" class="muted">No attack effectiveness rows for current filters.</td></tr>';
        } else {
          html += '<tr>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Number(g.count || 0))) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(g.empirical_expected_damage || 0).toFixed(3)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(g.damage_variance || 0).toFixed(3)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(g.exchange_win_rate || 0).toFixed(3)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(g.attack_good_rate || 0).toFixed(3)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(g.attack_good_prob_mean || 0).toFixed(3)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(g.attack_good_brier || 0).toFixed(4)) + '</td>' +
            '</tr>';
        }
        html += '</tbody></table>';
        function bucketTable(title, bucket) {
          const rowsB = Object.keys(bucket || {}).map(function (k) {
            return { key: k, row: bucket[k] || {} };
          }).sort(function (a, b) { return Number((b.row || {}).count || 0) - Number((a.row || {}).count || 0); });
          let out = '<h4 style="margin:10px 0 6px 0;">' + esc(title) + '</h4><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
            '<th style="border:1px solid #334155;padding:6px;">bucket</th><th style="border:1px solid #334155;padding:6px;">count</th><th style="border:1px solid #334155;padding:6px;">E[dmg]</th><th style="border:1px solid #334155;padding:6px;">Var[dmg]</th><th style="border:1px solid #334155;padding:6px;">exchange_win_rate</th><th style="border:1px solid #334155;padding:6px;">Brier</th></tr></thead><tbody>';
          if (!rowsB.length) {
            out += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No rows.</td></tr>';
          } else {
            for (const rb of rowsB.slice(0, 30)) {
              const rr = rb.row || {};
              out += '<tr><td style="border:1px solid #334155;padding:6px;">' + esc(String(rb.key || "")) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Number(rr.count || 0))) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.empirical_expected_damage || 0).toFixed(3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.damage_variance || 0).toFixed(3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.exchange_win_rate || 0).toFixed(3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.attack_good_brier || 0).toFixed(4)) + '</td></tr>';
            }
          }
          out += '</tbody></table>';
          return out;
        }
        html += bucketTable("By attack kind", attackEff.by_action_kind || {});
        html += bucketTable("By distance bucket", attackEff.by_distance_bucket || {});
        html += bucketTable("By cover bucket", attackEff.by_cover_bucket || {});
        const calRows = Object.keys(attackEff.calibration_bins || {}).sort();
        html += '<h4 style="margin:10px 0 6px 0;">Calibration bins</h4><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">bin</th><th style="border:1px solid #334155;padding:6px;">count</th><th style="border:1px solid #334155;padding:6px;">pred_mean</th><th style="border:1px solid #334155;padding:6px;">empirical_rate</th><th style="border:1px solid #334155;padding:6px;">Brier</th></tr></thead><tbody>';
        if (!calRows.length) {
          html += '<tr><td colspan="5" style="border:1px solid #334155;padding:6px;" class="muted">No calibration bins.</td></tr>';
        } else {
          for (const k of calRows) {
            const rr = attackEff.calibration_bins[k] || {};
            html += '<tr><td style="border:1px solid #334155;padding:6px;">' + esc(String(k || "")) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(Number(rr.count || 0))) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.predicted_prob_mean || 0).toFixed(3)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.empirical_attack_good_rate || 0).toFixed(3)) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(rr.brier || 0).toFixed(4)) + '</td></tr>';
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
        const sideKeyMap = {};
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
              sideKeyMap[String(src.unit_side || "UNK")] = true;
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
              if (!ownership[s]) ownership[s] = { side: s, rows: 0, policy_kept: 0, overwritten: 0, override_signal_rows: 0, unknown_override_rows: 0 };
              ownership[s].rows += Number(o.rows || 0);
              ownership[s].policy_kept += Number(o.policy_kept || 0);
              ownership[s].overwritten += Number(o.overwritten || 0);
              ownership[s].override_signal_rows += Number(o.override_signal_rows || 0);
              ownership[s].unknown_override_rows += Number(o.unknown_override_rows || 0);
            }
          }
        }
        const rows = Object.values(rowMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
        const sideKeys = Object.keys(sideKeyMap).sort((a, b) => String(a || "").localeCompare(String(b || "")));
        const pivotRows = {};
        for (const row of rows) {
          const action = String(row.action_kind || "UNKNOWN");
          const side = String(row.side || "UNK");
          if (!pivotRows[action]) pivotRows[action] = {};
          pivotRows[action][side] = row;
        }
        const actionKeys = Object.keys(pivotRows).sort((a, b) => {
          let sumA = 0;
          const aRow = pivotRows[a] || {};
          for (const s of sideKeys) sumA += Number(((aRow[s] || {}).count) || 0);
          let sumB = 0;
          const bRow = pivotRows[b] || {};
          for (const s of sideKeys) sumB += Number(((bRow[s] || {}).count) || 0);
          return sumB - sumA;
        });
        const topRows = Object.values(topActions).sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 20);
        const ownRows = Object.values(ownership).sort((a, b) => String(a.side).localeCompare(String(b.side)));
        let html = '<h3 style="margin:8px 0;">Table A: Action Kind x Side (Pivot)</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th rowspan="2" style="border:1px solid #334155;padding:6px;">action_kind</th>';
        for (const side of sideKeys) {
          html += '<th colspan="3" style="border:1px solid #334155;padding:6px;white-space:nowrap;">' + esc(String(side || "UNK")) + '</th>';
        }
        html += '</tr><tr>';
        for (const _side of sideKeys) {
          html += '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">count</th>' +
            '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">damage</th>' +
            '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">kills</th>';
        }
        html += '</tr></thead><tbody>';
        if (!actionKeys.length || !sideKeys.length) {
          html += '<tr><td colspan="' + String(1 + sideKeys.length * 3) + '" style="border:1px solid #334155;padding:6px;" class="muted">No decision rows available.</td></tr>';
        } else {
          for (const action of actionKeys) {
            html += '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(action) + '</td>';
            for (const side of sideKeys) {
              const cell = ((pivotRows[action] || {})[side]) || null;
              if (!cell) {
                html += '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                  '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                  '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>';
              } else {
                html += '<td style="border:1px solid #334155;padding:6px;">' + esc(String(cell.count || 0)) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(cell.damage || 0).toFixed(3)) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(cell.kills || 0).toFixed(3)) + '</td>';
              }
            }
            html += '</tr>';
          }
        }
        html += '</tbody></table>';
        html += '<h3 style="margin:12px 0 8px 0;">Table B: Decision Ownership by Side</h3>' +
          '<div class="muted" style="margin:0 0 6px 0;">Source: policy_overridden_by_mcts (canonical ownership telemetry).</div>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">side</th>' +
          '<th style="border:1px solid #334155;padding:6px;">rows</th>' +
          '<th style="border:1px solid #334155;padding:6px;">policy_kept</th>' +
          '<th style="border:1px solid #334155;padding:6px;">overwritten</th>' +
          '<th style="border:1px solid #334155;padding:6px;">override_signal_rows</th>' +
          '<th style="border:1px solid #334155;padding:6px;">unknown_override_rows</th>' +
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
              '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.unknown_override_rows || 0)) + '</td>' +
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
        hoveredUnitId: "",
        hoverHitPoints: [],
        hoverHitRadius: 6,
        hoverCanvasBound: false,
        hoverCanvasEl: null,
        decisionCandidateSortKey: "decision_score",
        decisionCandidateSortDir: "desc",
        payloadCache: {},
        logCache: {},
        logDebounceTimer: null,
        resizeRafToken: null,
        sliderDebounceTimer: null,
        hoverDebounceTimer: null,
        drawRafToken: null,
        drawPending: false,
        drawForcePending: false,
        lastDrawStateKey: "",
        lastCanvasDrawKey: "",
        panelMemo: {},
        loadReplayLogFn: null,
        chunkSize: 80,
        transitionsTotal: 0,
        transitionsHasMore: false,
        episodesMetaRenderKey: "",
      };
      function setReplayLoadStatus(message, tone) {
        const host = document.getElementById("replayLoadStatus");
        if (!host) return;
        const msg = String(message || "").trim();
        const t = String(tone || "info");
        const color = t === "error" ? "#fca5a5" : (t === "ok" ? "#86efac" : "#93c5fd");
        host.style.color = color;
        host.textContent = msg || "";
      }
      function clearReplayLoadStatus() {
        setReplayLoadStatus("", "info");
      }
      function stopReplayTimer() {
        if (replayState.timer) {
          clearInterval(replayState.timer);
          replayState.timer = null;
        }
        replayState.playing = false;
      }
      function replayPayloadCacheKey(evalSourcePath, episodeIdx) {
        return String(evalSourcePath || "") + "::" + String(Math.max(0, Number(episodeIdx || 0)));
      }
      function replayLogCacheKey(evalSourcePath, episodeIdx, uptoStep, unitId) {
        return [
          String(evalSourcePath || ""),
          String(Math.max(0, Number(episodeIdx || 0))),
          String(Math.max(0, Number(uptoStep || 0))),
          String(unitId || "__all__"),
        ].join("::");
      }
      function scheduleReplayLogLoad(delayMs) {
        const delay = Math.max(0, Number(delayMs || 0));
        if (replayState.logDebounceTimer) clearTimeout(replayState.logDebounceTimer);
        replayState.logDebounceTimer = setTimeout(function () {
          replayState.logDebounceTimer = null;
          if (typeof replayState.loadReplayLogFn === "function") {
            replayState.loadReplayLogFn();
          }
        }, delay);
      }
      function renderMatchReplay(filteredResultRows) {
        try {
        const host = document.getElementById("replayRoot");
        if (!host) return;
        host.innerHTML = '<div class="muted">Loading replay...</div>';
        const sourceRows = Array.isArray(filteredResultRows)
          ? filteredResultRows.filter(function (r) { return r && typeof r === "object"; })
          : [];
        if (!sourceRows.length) {
          stopReplayTimer();
          replayState.evalId = "__all__";
          replayState.payload = null;
          replayState.step = 0;
          replayState.episodeIndex = 0;
          host.innerHTML = '<div class="muted">No match games for current filters. Adjust filters to load replay.</div>';
          return;
        }
        let rows = [];
        try {
          rows = Array.isArray(sourceRows)
            ? sourceRows
                .map(function (r) {
                  return Object.assign({}, r, { eval_source_path: String((r && (r.eval_source_path || r.source_path)) || "") });
                })
                .filter(r => String(r.eval_source_path || "").trim())
            : [];
        } catch (e) {
          host.innerHTML = '<div class="muted">Replay rows parse error: ' + esc(String((e && e.message) || e || "unknown")) + '</div>';
          return;
        }
        if (!rows.length) {
          stopReplayTimer();
          replayState.payload = null;
          replayState.step = 0;
          replayState.episodeIndex = 0;
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
        replayState.hoverCanvasBound = false;
        replayState.hoverCanvasEl = null;
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
            <span id="replayLoadStatus" class="muted" style="min-width:220px;"></span>
          </div>
          <div id="replaySummary" class="replay-kv"></div>
          <div class="replay-grid">
            <div class="replay-panel">
              <h3>Map Snapshot</h3>
              <canvas id="replayCanvas" width="980" height="540" class="replay-canvas"></canvas>
              <div id="replayHoverLegend" class="replay-hover-legend">
                <span><span class="replay-hover-legend-chip replay-hover-legend-move"></span>reachable move hexes</span>
                <span><span class="replay-hover-legend-chip replay-hover-legend-attack"></span>attackable hexes</span>
              </div>
            </div>
            <div class="replay-side-col" style="grid-template-rows:auto auto minmax(0,1fr);">
              <div class="replay-panel">
                <h3>Hovered Unit Actions</h3>
                <div id="replayHoverActionsHost" class="list"></div>
              </div>
              <div class="replay-details-grid">
                <div class="replay-panel">
                  <h3>Step Details</h3>
                  <div id="replayStepDetail" class="list"></div>
                </div>
                <div class="replay-panel">
                  <h3 style="margin-bottom:6px;">Controller by side</h3>
                  <div id="replayControllerBySide" class="list" style="margin-bottom:10px;"></div>
                  <h3>Units Snapshot</h3>
                  <div id="replayUnitsHost" class="list"></div>
                </div>
              </div>
              <div class="replay-panel">
                <h3>Decision Influence</h3>
                <div id="replayDecisionInfluenceHost" class="list"></div>
              </div>
            </div>
            <div class="replay-side-col" style="grid-template-rows:auto minmax(0,1fr);">
              <div class="replay-panel">
                <h3>Head Diagnostics (per step)</h3>
                <div id="replayHeadDiagnosticsHost" class="list"></div>
              </div>
              <div class="replay-panel" style="min-height:0;display:flex;flex-direction:column;">
                <h3>Execution Log</h3>
                <pre id="replayLogHost" style="white-space:pre-wrap;word-break:break-word;background:#0b1220;border:1px solid #334155;border-radius:6px;padding:8px;font-size:12px;line-height:1.35;overflow:auto;max-height:520px;min-height:280px;">Loading...</pre>
              </div>
            </div>
          </div>
        `;
        async function loadReplay() {
          const t0 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
          setReplayLoadStatus("Loading replay: preparing request...", "info");
          stopReplayTimer();
          replayState.hoveredUnitId = "";
          replayState.hoverHitPoints = [];
          replayState.hoverHitRadius = 6;
          replayState.hoverCanvasBound = false;
          replayState.hoverCanvasEl = null;
          const details = document.getElementById("replayStepDetail");
          if (details) details.innerHTML = '<div class="muted">Loading replay payload...</div>';
          const evalSel = document.getElementById("replayEvalSelect");
          const epSel = document.getElementById("replayEpisodeSelect");
          replayState.evalId = String((((evalSel || {}).value) || replayState.evalId || ""));
          const row = evalRows.find(r => String(r.eval_id || "") === String(replayState.evalId || "")) || activeRow;
          const episodeIdx = Math.max(0, Number(
            (epSel && Number.isFinite(Number(epSel.selectedIndex)) && Number(epSel.selectedIndex) >= 0)
              ? epSel.selectedIndex
              : ((((epSel || {}).value) || replayState.episodeIndex || 0))
          ));
          replayState.episodeIndex = episodeIdx;
          if (!row || !String(row.eval_source_path || "").trim()) {
            replayState.payload = null;
            drawReplay();
            setReplayLoadStatus("Replay load failed: missing eval source path.", "error");
            return;
          }
          async function fetchReplayPayload(evalSourcePath, epIndex, chunkOffset, chunkLimit) {
            const cacheKey = replayPayloadCacheKey(evalSourcePath, epIndex) + "::" + String(Math.max(0, Number(chunkOffset || 0))) + "::" + String(Math.max(1, Number(chunkLimit || 80)));
            if (Object.prototype.hasOwnProperty.call(replayState.payloadCache, cacheKey)) {
              setReplayLoadStatus("Loading replay: cache hit...", "info");
              return replayState.payloadCache[cacheKey];
            }
            setReplayLoadStatus("Loading replay: fetching chunk...", "info");
            const url = `/api/muzero-replay?eval_source_path=${encodeURIComponent(String(evalSourcePath || ""))}&episode_index=${encodeURIComponent(String(epIndex || 0))}&chunk_offset=${encodeURIComponent(String(Math.max(0, Number(chunkOffset || 0))))}&chunk_limit=${encodeURIComponent(String(Math.max(1, Number(chunkLimit || 80))))}`;
            const resp = await fetch(url);
            setReplayLoadStatus("Loading replay: parsing payload...", "info");
            const payload = await resp.json();
            replayState.payloadCache[cacheKey] = payload;
            return payload;
          }
          try {
            setReplayLoadStatus("Loading replay: first chunk...", "info");
            replayState.payload = await fetchReplayPayload(String(row.eval_source_path || ""), episodeIdx, 0, replayState.chunkSize);
            const firstTransitions = Array.isArray(replayState.payload && replayState.payload.transitions)
              ? replayState.payload.transitions
              : [];
            // Some eval artifacts expose sparse/invalid episode indexes in UI state.
            // If selected episode is empty, retry episode 0 automatically.
            if (!firstTransitions.length && Number(episodeIdx) > 0) {
              setReplayLoadStatus("Loading replay: retrying episode 0...", "info");
              const fallbackPayload = await fetchReplayPayload(String(row.eval_source_path || ""), 0, 0, replayState.chunkSize);
              const fallbackTransitions = Array.isArray(fallbackPayload && fallbackPayload.transitions)
                ? fallbackPayload.transitions
                : [];
              if (fallbackTransitions.length) {
                replayState.payload = fallbackPayload;
                replayState.episodeIndex = 0;
                const epSelect = document.getElementById("replayEpisodeSelect");
                if (epSelect) epSelect.value = "0";
              }
            }
            if (replayState.payload && replayState.payload.error) {
              if (details) details.innerHTML = '<div class="muted">Replay payload error: ' + esc(String(replayState.payload.error)) + '</div>';
            }
            replayState.transitionsTotal = Math.max(0, Number((replayState.payload && replayState.payload.transitions_total) || 0));
            replayState.transitionsHasMore = Boolean(replayState.payload && replayState.payload.transitions_has_more);
            // Auto-load all chunks for the selected episode so replay navigation
            // does not depend on manual "Load More" interactions.
            let chunkGuard = 0;
            while (replayState.transitionsHasMore && chunkGuard < 1000) {
              chunkGuard += 1;
              const existing = Array.isArray(replayState.payload && replayState.payload.transitions)
                ? replayState.payload.transitions
                : [];
              const chunkOffset = existing.length;
              setReplayLoadStatus(
                "Loading replay: transitions " + String(chunkOffset) + "/" + String(Math.max(chunkOffset, Number(replayState.transitionsTotal || 0))) + "...",
                "info"
              );
              const extra = await fetchReplayPayload(
                String(row.eval_source_path || ""),
                Math.max(0, Number(replayState.episodeIndex || episodeIdx || 0)),
                chunkOffset,
                replayState.chunkSize
              );
              const extraTransitions = Array.isArray(extra && extra.transitions) ? extra.transitions : [];
              if (!extraTransitions.length) {
                replayState.transitionsHasMore = false;
                break;
              }
              replayState.payload.transitions = existing.concat(extraTransitions);
              replayState.transitionsTotal = Math.max(
                replayState.payload.transitions.length,
                Number((extra && extra.transitions_total) || replayState.transitionsTotal || 0)
              );
              replayState.transitionsHasMore = Boolean(extra && extra.transitions_has_more);
            }
            replayState.step = 0;
          } catch (_e) {
            replayState.payload = null;
            if (details) details.innerHTML = '<div class="muted">Replay fetch failed.</div>';
            setReplayLoadStatus("Replay load failed.", "error");
          }
          drawReplay(true);
          scheduleReplayLogLoad(0);
          const t1 = (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
          const ms = Math.max(0, Math.round(Number(t1) - Number(t0)));
          const loaded = Array.isArray(replayState.payload && replayState.payload.transitions)
            ? replayState.payload.transitions.length
            : 0;
          const total = Math.max(loaded, Number(replayState.transitionsTotal || 0));
          setReplayLoadStatus("Replay loaded: " + String(loaded) + "/" + String(total) + " transitions (" + String(ms) + " ms)", "ok");
        }
        async function loadReplayLog() {
          const logHost = document.getElementById("replayLogHost");
          if (!logHost) return;
          try {
            const evalSel = document.getElementById("replayEvalSelect");
            const epSel = document.getElementById("replayEpisodeSelect");
            const evalId = String((((evalSel || {}).value) || replayState.evalId || ""));
            const epIdx = Math.max(0, Number(
              (epSel && Number.isFinite(Number(epSel.selectedIndex)) && Number(epSel.selectedIndex) >= 0)
                ? epSel.selectedIndex
                : ((((epSel || {}).value) || replayState.episodeIndex || 0))
            ));
            const row = evalRows.find(r => String(r.eval_id || "") === String(evalId)) || activeRow;
            const src = String((row && row.eval_source_path) || "");
            if (!src) {
              logHost.textContent = "No execution log: missing eval_source_path.";
              return;
            }
            const upto = Math.max(0, Number(replayState.step || 0));
            const selectedUnitId = String(replayState.unitFilter || "__all__");
            const cacheKey = replayLogCacheKey(src, epIdx, upto, selectedUnitId);
            if (Object.prototype.hasOwnProperty.call(replayState.logCache, cacheKey)) {
              logHost.textContent = String(replayState.logCache[cacheKey] || "");
              logHost.scrollTop = logHost.scrollHeight;
              return;
            }
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
              const unitId = selectedUnitId;
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
            replayState.logCache[cacheKey] = String(logHost.textContent || "");
            logHost.scrollTop = logHost.scrollHeight;
          } catch (e) {
            logHost.textContent = "Execution log unavailable: " + String((e && e.message) || e || "unknown error");
          }
        }
        replayState.loadReplayLogFn = loadReplayLog;
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
            // Defensive fallback: never use pixel width/height as cell counts.
            : Array.from({ length: 12 }, (_, rr) =>
                Array.from({ length: 18 }, (_, qq) => ({ q: qq, r: rr }))
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
        function drawHexCoordLabel(ctx, cx, cy, size, q, r) {
          const qn = Math.round(Number(q || 0));
          const rn = Math.round(Number(r || 0));
          ctx.fillStyle = "rgba(148,163,184,0.82)";
          ctx.font = String(Math.max(8, Math.floor(size * 0.28))) + "px sans-serif";
          ctx.textAlign = "left";
          ctx.textBaseline = "top";
          const labelX = cx - size * 0.62;
          const labelY = cy - size * 0.52;
          ctx.fillText("(" + String(qn) + "," + String(rn) + ")", labelX, labelY);
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
        function setReplayHoveredUnit(unitId) {
          const selectedUnitId = String(replayState.unitFilter || "__all__").trim();
          let nextId = String(unitId || "");
          if (selectedUnitId !== "__all__" && nextId && nextId !== selectedUnitId) nextId = "";
          const curr = String(replayState.hoveredUnitId || "");
          if (nextId === curr) return;
          replayState.hoveredUnitId = nextId;
          if (replayState.hoverDebounceTimer) clearTimeout(replayState.hoverDebounceTimer);
          replayState.hoverDebounceTimer = setTimeout(function () {
            replayState.hoverDebounceTimer = null;
            requestReplayDraw("hover", false);
          }, 24);
        }
        function replayActionKindFromId(actionId) {
          return String(actionId || "").split(":")[0].trim().toUpperCase();
        }
        function replayActionUnitFromId(actionId) {
          const parts = String(actionId || "").split(":");
          return String(parts.length > 1 ? parts[1] : "").trim();
        }
        function replayActionHexFromRaw(raw) {
          if (!raw || typeof raw !== "object") return null;
          const qKeys = ["target_q", "to_q", "action_target_q", "hex_q"];
          const rKeys = ["target_r", "to_r", "action_target_r", "hex_r"];
          for (let i = 0; i < Math.min(qKeys.length, rKeys.length); i += 1) {
            const q = Number(raw[qKeys[i]]);
            const r = Number(raw[rKeys[i]]);
            if (Number.isFinite(q) && Number.isFinite(r)) return { q, r };
          }
          const actionId = String(raw.action_id || raw.id || "");
          const parts = actionId.split(":");
          if (parts.length >= 4) {
            const q = Number(parts[2]);
            const r = Number(parts[3]);
            if (Number.isFinite(q) && Number.isFinite(r)) return { q, r };
          }
          return null;
        }
        function replayCollectCanonicalActionCandidates(stepRow) {
          const out = [];
          const pushActionLike = function (raw) {
            if (raw === null || raw === undefined) return;
            if (typeof raw === "string") {
              out.push({ action_id: raw });
              return;
            }
            if (raw && typeof raw === "object") out.push(raw);
          };
          const directLists = [
            stepRow && stepRow.legal_actions,
            stepRow && stepRow.legal_action_ids,
            stepRow && stepRow.mcts_action_candidates,
            stepRow && stepRow.why_action_vs_vp && stepRow.why_action_vs_vp.candidate_actions,
          ];
          for (const src of directLists) {
            if (!Array.isArray(src)) continue;
            for (const item of src) pushActionLike(item);
          }
          return out;
        }
        function replayCandidateActorUnit(cand) {
          if (!cand || typeof cand !== "object") return "";
          const actionId = String((cand && cand.action_id) || cand.id || "");
          const explicitActorUnits = [
            String((cand && cand.unit_id) || "").trim(),
            String((cand && cand.actor_unit_id) || "").trim(),
            String((cand && cand.source_unit_id) || "").trim(),
          ].filter(Boolean);
          const uniqueExplicit = Array.from(new Set(explicitActorUnits));
          if (uniqueExplicit.length > 1) return "";
          const explicitActor = uniqueExplicit.length ? uniqueExplicit[0] : "";
          const derivedActor = String(replayActionUnitFromId(actionId) || "").trim();
          if (derivedActor && explicitActor && derivedActor !== explicitActor) return "";
          return explicitActor || derivedActor;
        }
        function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {
          const wanted = String(hoveredUnitId || "").trim();
          const empty = { moveHexes: [], attackHexes: [] };
          if (!wanted || !stepRow || typeof stepRow !== "object") return empty;
          const moveMap = {};
          const attackMap = {};
          const addHex = function (bucket, q, r) {
            if (!Number.isFinite(Number(q)) || !Number.isFinite(Number(r))) return;
            const qn = Number(q);
            const rn = Number(r);
            bucket[String(qn) + "," + String(rn)] = { q: qn, r: rn };
          };
          const moveKind = function (kind) {
            const k = String(kind || "").toUpperCase();
            return k === "MOVE" || k === "ADVANCE" || k === "REDEPLOY";
          };
          const attackKind = function (kind) {
            const k = String(kind || "").toUpperCase();
            return k.indexOf("FIRE") >= 0 || k.indexOf("ATTACK") >= 0 || k.indexOf("MELEE") >= 0;
          };
          const actionCandidates = replayCollectCanonicalActionCandidates(stepRow);
          for (const cand of actionCandidates) {
            const actionId = String((cand && cand.action_id) || cand.id || "");
            const kind = String((cand && (cand.action_kind || cand.kind)) || replayActionKindFromId(actionId));
            const actionUnit = replayCandidateActorUnit(cand);
            if (!actionUnit || actionUnit !== wanted) continue;
            const hex = replayActionHexFromRaw(cand);
            if (!hex) continue;
            if (moveKind(kind)) addHex(moveMap, hex.q, hex.r);
            else if (attackKind(kind)) addHex(attackMap, hex.q, hex.r);
          }
          return {
            moveHexes: Object.values(moveMap),
            attackHexes: Object.values(attackMap),
          };
        }
        function replayBindCanvasHoverHandlers(canvas) {
          if (!canvas) return;
          if (replayState.hoverCanvasBound && replayState.hoverCanvasEl === canvas) return;
          canvas.onmousemove = function (ev) {
            const rectLocal = canvas.getBoundingClientRect();
            const mx = Number(ev.clientX || 0) - Number(rectLocal.left || 0);
            const my = Number(ev.clientY || 0) - Number(rectLocal.top || 0);
            const points = Array.isArray(replayState.hoverHitPoints) ? replayState.hoverHitPoints : [];
            const hitRadius = Math.max(6, Number(replayState.hoverHitRadius || 6));
            let hitUnit = "";
            for (const u of points) {
              const dx = Number(u.x || 0) - mx;
              const dy = Number(u.y || 0) - my;
              if ((dx * dx + dy * dy) <= (hitRadius * hitRadius)) {
                hitUnit = String(u.unit_id || "");
                break;
              }
            }
            setReplayHoveredUnit(hitUnit);
          };
          canvas.onmouseleave = function () {
            setReplayHoveredUnit("");
          };
          replayState.hoverCanvasEl = canvas;
          replayState.hoverCanvasBound = true;
        }
        function renderReplayHoveredActions(stepRow) {
          const host = document.getElementById("replayHoverActionsHost");
          if (!host) return;
          const fmtNum = function (v, digits) {
            if (v === null || v === undefined) return "N/A";
            const n = Number(v);
            if (!Number.isFinite(n)) return "N/A";
            const d = Number.isFinite(Number(digits)) ? Number(digits) : 3;
            return n.toFixed(d);
          };
          const hoveredUnitId = String(replayState.hoveredUnitId || "").trim();
          const selectedUnitId = String(replayState.unitFilter || "__all__").trim();
          const effectiveUnitId = hoveredUnitId || (selectedUnitId !== "__all__" ? selectedUnitId : "");
          if (!stepRow || typeof stepRow !== "object") {
            host.innerHTML = '<div class="muted">Hover a unit to inspect candidate actions.</div>';
            return;
          }
          if (!effectiveUnitId) {
            host.innerHTML = '<div class="muted">Hover a unit to inspect candidate actions.</div>';
            return;
          }
          const candidateRows = replayCollectCanonicalActionCandidates(stepRow);
          const why = (stepRow.why_action_vs_vp && typeof stepRow.why_action_vs_vp === "object") ? stepRow.why_action_vs_vp : {};
          const chosenActionId = String((why && why.chosen_action_id) || stepRow.action_id || "").trim();
          const vpBestActionId = String((why && why.vp_best_action_id) || "").trim();
          const filtered = [];
          for (const cand of candidateRows) {
            const actorUnitId = replayCandidateActorUnit(cand);
            if (!actorUnitId || actorUnitId !== effectiveUnitId) continue;
            const actionId = String((cand && cand.action_id) || cand.id || "").trim();
            const actionKind = String((cand && (cand.action_kind || cand.kind)) || replayActionKindFromId(actionId)).toUpperCase();
            const target = replayActionHexFromRaw(cand);
            const markers = [];
            if (actionId && chosenActionId && actionId === chosenActionId) markers.push("chosen");
            if (actionId && vpBestActionId && actionId === vpBestActionId) markers.push("vp-best");
            if (cand && cand.selected_action === true) markers.push("selected");
            filtered.push({
              actionId: actionId || "N/A",
              actionKind: actionKind || "N/A",
              unitId: actorUnitId,
              targetQr: target ? (String(Number(target.q)) + "," + String(Number(target.r))) : "-",
              vpDelta: (cand && cand.vp_progress_delta !== undefined && cand.vp_progress_delta !== null && Number.isFinite(Number(cand.vp_progress_delta)))
                ? Number(cand.vp_progress_delta)
                : null,
              vpDistanceAfter: (cand && cand.vp_distance_after !== undefined && cand.vp_distance_after !== null && Number.isFinite(Number(cand.vp_distance_after)))
                ? Number(cand.vp_distance_after)
                : null,
              markers: markers.length ? markers.join(", ") : "-",
              raw: cand,
            });
          }
          // Merge telemetry across duplicated action_id entries coming from
          // legal list + mcts candidates + why_action_vs_vp candidates.
          const mergedByAction = {};
          for (const row of filtered) {
            const key = String(row.actionId || "").trim();
            if (!key || key === "N/A") continue;
            if (!mergedByAction[key]) {
              mergedByAction[key] = {
                vpDelta: row.vpDelta,
                vpDistanceAfter: row.vpDistanceAfter,
              };
              continue;
            }
            if (mergedByAction[key].vpDelta === null && row.vpDelta !== null) {
              mergedByAction[key].vpDelta = row.vpDelta;
            }
            if (mergedByAction[key].vpDistanceAfter === null && row.vpDistanceAfter !== null) {
              mergedByAction[key].vpDistanceAfter = row.vpDistanceAfter;
            }
          }
          for (const row of filtered) {
            const key = String(row.actionId || "").trim();
            const merged = mergedByAction[key];
            if (!merged) continue;
            if (row.vpDelta === null && merged.vpDelta !== null) row.vpDelta = merged.vpDelta;
            if (row.vpDistanceAfter === null && merged.vpDistanceAfter !== null) row.vpDistanceAfter = merged.vpDistanceAfter;
          }
          const hasOwn = function (obj, key) {
            return !!obj && typeof obj === "object" && Object.prototype.hasOwnProperty.call(obj, key);
          };
          const hasMctsTelemetry = function (cand) {
            if (!cand || typeof cand !== "object") return false;
            return (
              hasOwn(cand, "real_decision_score") ||
              hasOwn(cand, "visit_count") ||
              hasOwn(cand, "decision_rank") ||
              hasOwn(cand, "mcts_q_value") ||
              hasOwn(cand, "mcts_u_value") ||
              hasOwn(cand, "policy_prior")
            );
          };
          const valueOrNA = function (value) {
            if (value === null || value === undefined) return "N/A";
            const txt = String(value).trim();
            return txt ? txt : "N/A";
          };
          const fmtTinyProb = function (value) {
            if (value === null || value === undefined) return "N/A";
            const n = Number(value);
            if (!Number.isFinite(n)) return "N/A";
            if (n === 0) return "0";
            if (Math.abs(n) < 1e-6) return "<1e-6 (" + n.toExponential(2) + ")";
            return fmtNum(n, 6);
          };
          const mctsRowsRaw = [];
          for (const row of filtered) {
            if (!hasMctsTelemetry(row.raw)) continue;
            const raw = row.raw || {};
            const scoreRaw = hasOwn(raw, "real_decision_score") ? raw.real_decision_score : null;
            const scoreNum = (scoreRaw === null || scoreRaw === undefined) ? null : Number(scoreRaw);
            const visitsRaw = hasOwn(raw, "visit_count") ? raw.visit_count : null;
            const visitsNum = (visitsRaw === null || visitsRaw === undefined) ? null : Number(visitsRaw);
            const rankRaw = hasOwn(raw, "decision_rank") ? raw.decision_rank : null;
            const qRaw = hasOwn(raw, "mcts_q_value") ? raw.mcts_q_value : null;
            const uRaw = hasOwn(raw, "mcts_u_value") ? raw.mcts_u_value : null;
            const priorRaw = hasOwn(raw, "policy_prior") ? raw.policy_prior : null;
            const selectionSourceRaw = hasOwn(raw, "selection_source") ? raw.selection_source : null;
            mctsRowsRaw.push({
              actionId: row.actionId,
              unitId: row.unitId,
              scoreNum: Number.isFinite(scoreNum) ? Number(scoreNum) : null,
              visitsNum: Number.isFinite(visitsNum) ? Number(visitsNum) : null,
              vpDelta: valueOrNA((row.vpDelta === null || row.vpDelta === undefined) ? null : fmtNum(row.vpDelta, 3)),
              vpDist: valueOrNA((row.vpDistanceAfter === null || row.vpDistanceAfter === undefined) ? null : fmtNum(row.vpDistanceAfter, 3)),
              score: valueOrNA(scoreNum === null || !Number.isFinite(scoreNum) ? null : fmtNum(scoreNum, 3)),
              visits: valueOrNA(visitsRaw),
              rank: valueOrNA(rankRaw),
              qValue: valueOrNA((qRaw === null || qRaw === undefined || !Number.isFinite(Number(qRaw))) ? null : fmtNum(Number(qRaw), 3)),
              uValue: valueOrNA((uRaw === null || uRaw === undefined || !Number.isFinite(Number(uRaw))) ? null : fmtNum(Number(uRaw), 3)),
              prior: valueOrNA((priorRaw === null || priorRaw === undefined || !Number.isFinite(Number(priorRaw))) ? null : fmtNum(Number(priorRaw), 3)),
              visitShare: valueOrNA(hasOwn(raw, "visit_share") ? fmtTinyProb(raw.visit_share) : null),
              chosenActionProb: valueOrNA(hasOwn(raw, "chosen_action_prob") ? fmtTinyProb(raw.chosen_action_prob) : null),
              selectionSource: valueOrNA(selectionSourceRaw),
            });
          }
          const byScoreOrder = mctsRowsRaw.slice().sort(function (a, b) {
            const as = Number.isFinite(Number(a.scoreNum)) ? Number(a.scoreNum) : -Infinity;
            const bs = Number.isFinite(Number(b.scoreNum)) ? Number(b.scoreNum) : -Infinity;
            if (bs !== as) return bs - as;
            return String(a.actionId || "").localeCompare(String(b.actionId || ""));
          });
          const byVisitsOrder = mctsRowsRaw.slice().sort(function (a, b) {
            const av = Number.isFinite(Number(a.visitsNum)) ? Number(a.visitsNum) : -1;
            const bv = Number.isFinite(Number(b.visitsNum)) ? Number(b.visitsNum) : -1;
            if (bv !== av) return bv - av;
            const as = Number.isFinite(Number(a.scoreNum)) ? Number(a.scoreNum) : -Infinity;
            const bs = Number.isFinite(Number(b.scoreNum)) ? Number(b.scoreNum) : -Infinity;
            if (bs !== as) return bs - as;
            return String(a.actionId || "").localeCompare(String(b.actionId || ""));
          });
          const rankByScore = {};
          const rankByVisits = {};
          byScoreOrder.forEach(function (r, idx) { rankByScore[String(r.actionId || "")] = idx + 1; });
          byVisitsOrder.forEach(function (r, idx) { rankByVisits[String(r.actionId || "")] = idx + 1; });
          const mctsRows = mctsRowsRaw.map(function (r) {
            return Object.assign({}, r, {
              rankByScore: valueOrNA(rankByScore[String(r.actionId || "")]),
              rankByVisits: valueOrNA(rankByVisits[String(r.actionId || "")]),
            });
          });
          const sourceLabel = hoveredUnitId ? "hover" : "selected";
          let html = '<div class="muted" style="margin-bottom:4px;">Hovered unit action candidates (producer-only strict) | unit=' + esc(effectiveUnitId) + ' | source=' + esc(sourceLabel) + '</div>';
          html += '<div style="margin:4px 0 6px 0;font-weight:600;">Legal actions (unit-scoped)</div>';
          html += '<div class="muted" style="margin-bottom:4px;">Producer legal list for hovered unit; no MCTS fields required.</div>';
          html += '<div id="replayHoverLegalTableWrap" class="replay-candidate-table-wrap"><table class="replay-candidate-table" style="width:100%;border-collapse:collapse;font-size:12px;">' +
            '<thead><tr>' +
            '<th style="border:1px solid #334155;padding:6px;">action_id</th>' +
            '<th style="border:1px solid #334155;padding:6px;">action_kind</th>' +
            '<th style="border:1px solid #334155;padding:6px;">unit_id</th>' +
            '<th style="border:1px solid #334155;padding:6px;">target_qr</th>' +
            '<th style="border:1px solid #334155;padding:6px;">vp_delta</th>' +
            '<th style="border:1px solid #334155;padding:6px;">vp_dist</th>' +
            '<th style="border:1px solid #334155;padding:6px;">markers</th>' +
            '</tr></thead><tbody>';
          if (!filtered.length) {
            html += '<tr><td colspan="7" style="border:1px solid #334155;padding:6px;" class="muted">No candidate actions for hovered unit in this step.</td></tr>';
          } else {
            for (const row of filtered) {
              const isChosen = String(row.markers || "").indexOf("chosen") >= 0;
              const isVpBest = String(row.markers || "").indexOf("vp-best") >= 0;
              const rowStyle = isChosen
                ? 'background:rgba(16,185,129,0.18);'
                : (isVpBest ? 'background:rgba(250,204,21,0.12);' : '');
              html += '<tr>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.actionId) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.actionKind) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.unitId) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.targetQr) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.vpDelta === null ? "N/A" : fmtNum(row.vpDelta, 3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.vpDistanceAfter === null ? "N/A" : fmtNum(row.vpDistanceAfter, 3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.markers) + '</td>' +
                '</tr>';
            }
          }
          html += '</tbody></table></div>';
          html += '<div style="margin:8px 0 6px 0;font-weight:600;">MCTS-evaluated actions</div>';
          html += '<div class="muted" style="margin-bottom:4px;">Rows below are producer-only strict; missing producer keys show as N/A. Tiny probs are shown as &lt;1e-6 (scientific).</div>';
          html += '<div id="replayHoverMctsTableWrap" class="replay-candidate-table-wrap"><table class="replay-candidate-table" style="width:100%;border-collapse:collapse;font-size:12px;">' +
            '<thead><tr>' +
            '<th style="border:1px solid #334155;padding:6px;">action_id</th>' +
            '<th style="border:1px solid #334155;padding:6px;">unit_id</th>' +
            '<th style="border:1px solid #334155;padding:6px;">vp_delta</th>' +
            '<th style="border:1px solid #334155;padding:6px;">vp_dist</th>' +
            '<th style="border:1px solid #334155;padding:6px;">score</th>' +
            '<th style="border:1px solid #334155;padding:6px;">visits</th>' +
            '<th style="border:1px solid #334155;padding:6px;">rank</th>' +
            '<th style="border:1px solid #334155;padding:6px;">rank_by_score</th>' +
            '<th style="border:1px solid #334155;padding:6px;">rank_by_visits</th>' +
            '<th style="border:1px solid #334155;padding:6px;">mcts_q</th>' +
            '<th style="border:1px solid #334155;padding:6px;">mcts_u</th>' +
            '<th style="border:1px solid #334155;padding:6px;">prior</th>' +
            '<th style="border:1px solid #334155;padding:6px;">visit_share</th>' +
            '<th style="border:1px solid #334155;padding:6px;">chosen_action_prob</th>' +
            '<th style="border:1px solid #334155;padding:6px;">selection_source</th>' +
            '</tr></thead><tbody>';
          if (!mctsRows.length) {
            html += '<tr><td colspan="15" style="border:1px solid #334155;padding:6px;" class="muted">No MCTS-evaluated actions for hovered unit in this step.</td></tr>';
          } else {
            for (const row of mctsRows) {
              const isChosen = String(row.actionId || "") === String(chosenActionId || "");
              const isVpBest = String(row.actionId || "") === String(vpBestActionId || "");
              const rowStyle = isChosen
                ? 'background:rgba(16,185,129,0.18);'
                : (isVpBest ? 'background:rgba(250,204,21,0.12);' : '');
              html += '<tr>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.actionId) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.unitId) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.vpDelta) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.vpDist) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.score) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.visits) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.rank) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.rankByScore) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.rankByVisits) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.qValue) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.uValue) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.prior) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.visitShare) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.chosenActionProb) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;' + rowStyle + '">' + esc(row.selectionSource) + '</td>' +
                '</tr>';
            }
          }
          html += '</tbody></table></div>';
          host.innerHTML = html;
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
          scheduleReplayLogLoad(90);
          if (!nav.moved) {
            if (String(replayState.unitFilter || "__all__") === "__all__") {
              const direction = Number(delta || 0) >= 0 ? "next" : "previous";
              setReplayStepNavFeedback("No " + direction + " step.");
            } else {
              if (Number(delta || 0) >= 0) setReplayStepNavFeedback("No next step for selected unit.");
              else setReplayStepNavFeedback("No previous step for selected unit.");
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
              replayState.hoveredUnitId = "";
              snapReplayStepToRelevantUnitActivity();
              setReplayStepNavFeedback("");
              drawReplay();
              scheduleReplayLogLoad(60);
            };
          }
          const clearBtn = document.getElementById("replayUnitFilterClearBtn");
          if (clearBtn) {
            clearBtn.onclick = function () {
              replayState.unitFilter = "__all__";
              replayState.hoveredUnitId = "";
              setReplayStepNavFeedback("");
              drawReplay();
              scheduleReplayLogLoad(60);
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
            function valueClass(v) {
              const s = String(v || "");
              if (s === "N/A" || s.indexOf("N/A") >= 0 || s === "unknown") return "na-text";
              return "ok-text";
            }
            return rows.map(function (r) {
              return '<tr><td style="border:1px solid #334155;padding:6px;">' + esc(String(r[0])) + '</td><td style="border:1px solid #334155;padding:6px;"><span class="' + valueClass(r[1]) + '">' + esc(String(r[1])) + "</span></td></tr>";
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
              ["mcts_total_visits", fmtNumber(stepRow.mcts_total_visits, 0)],
              ["active_actions_with_visits", fmtNumber(stepRow.mcts_active_actions, 0)],
              ["mcts_entropy_source", String(stepRow.mcts_entropy_source || "unknown")],
              ["mcts_entropy_collapse", String(stepRow.mcts_entropy_collapse_label || "unknown")]
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
          const unitPrefilterEnabled = safeNum(stepRow.unit_prefilter_enabled);
          const unitPrefilterSelectedUnitId = String(stepRow.unit_prefilter_selected_unit_id || "");
          const unitPrefilterConstrainedCount = safeNum(stepRow.unit_prefilter_constrained_count);
          const unitPrefilterGlobalCount = safeNum(stepRow.unit_prefilter_global_count);
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
            ["mcts metrics", "visits=" + fmtNum(stepRow.mcts_total_visits, 0) + " | active_actions_with_visits=" + fmtNum(stepRow.mcts_active_actions, 0) + " | margin=" + fmtNum(stepRow.mcts_margin, 3) + " | entropy=" + fmtNum(stepRow.mcts_entropy, 3) + " | chosen_prob=" + fmtPct(stepRow.chosen_action_prob, 1) + " | collapse=" + String(stepRow.mcts_entropy_collapse_label || "unknown")],
            ["unit prefilter", "enabled=" + (unitPrefilterEnabled === null ? "N/A" : String(Math.round(unitPrefilterEnabled))) + " | selected_unit_id=" + (unitPrefilterSelectedUnitId || "N/A") + " | constrained=" + fmtNum(unitPrefilterConstrainedCount, 0) + " | global=" + fmtNum(unitPrefilterGlobalCount, 0)],
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
          const candidateSourceLists = [
            Array.isArray(whyBlock.candidate_actions) ? whyBlock.candidate_actions : [],
            Array.isArray(stepRow.mcts_action_candidates) ? stepRow.mcts_action_candidates : [],
            Array.isArray(stepRow.legal_actions) ? stepRow.legal_actions : [],
            Array.isArray(stepRow.legal_action_ids) ? stepRow.legal_action_ids : [],
          ];
          const candidateRowsRawMap = {};
          const candidateRowsRaw = [];
          const pushCandidateRaw = function (raw) {
            if (raw === null || raw === undefined) return;
            const obj = (typeof raw === "string") ? { action_id: String(raw) } : ((raw && typeof raw === "object") ? Object.assign({}, raw) : null);
            if (!obj) return;
            const actionId = String(obj.action_id || obj.id || "").trim();
            if (!actionId) return;
            if (!candidateRowsRawMap[actionId]) {
              candidateRowsRawMap[actionId] = obj;
              candidateRowsRaw.push(obj);
              return;
            }
            const prev = candidateRowsRawMap[actionId];
            candidateRowsRawMap[actionId] = Object.assign({}, prev, obj);
            const idx = candidateRowsRaw.findIndex(function (c) { return String((c && c.action_id) || "") === actionId; });
            if (idx >= 0) candidateRowsRaw[idx] = candidateRowsRawMap[actionId];
          };
          for (const srcList of candidateSourceLists) {
            for (const item of srcList) pushCandidateRaw(item);
          }
          const normalizeDecisionCandidate = function (raw, chosenActionId) {
            const hasOwn = function (obj, key) {
              return !!obj && typeof obj === "object" && Object.prototype.hasOwnProperty.call(obj, key);
            };
            const c = (raw && typeof raw === "object") ? Object.assign({}, raw) : {};
            const actionId = String(c.action_id || "");
            const actionParts = actionId.split(":");
            if (!c.unit_id && actionParts.length > 1) c.unit_id = String(actionParts[1] || "").trim();
            c.real_decision_score = hasOwn(c, "real_decision_score") ? safeNum(c.real_decision_score) : null;
            c.visit_count = hasOwn(c, "visit_count") ? safeNum(c.visit_count) : null;
            c.decision_rank = hasOwn(c, "decision_rank") ? safeNum(c.decision_rank) : null;
            c.mcts_q_value = hasOwn(c, "mcts_q_value") ? safeNum(c.mcts_q_value) : null;
            c.mcts_u_value = hasOwn(c, "mcts_u_value") ? safeNum(c.mcts_u_value) : null;
            c.policy_prior = hasOwn(c, "policy_prior") ? safeNum(c.policy_prior) : null;
            c.selection_source = hasOwn(c, "selection_source") ? String(c.selection_source || "") : null;
            c.selected_action = c.selected_action === true || (actionId && actionId === String(chosenActionId || ""));
            c.missing_producer_fields = [];
            if (c.real_decision_score === null) c.missing_producer_fields.push("real_decision_score");
            if (c.visit_count === null) c.missing_producer_fields.push("visit_count");
            if (c.decision_rank === null) c.missing_producer_fields.push("decision_rank");
            if (c.mcts_q_value === null) c.missing_producer_fields.push("mcts_q_value");
            if (c.mcts_u_value === null) c.missing_producer_fields.push("mcts_u_value");
            if (c.policy_prior === null) c.missing_producer_fields.push("policy_prior");
            if (!c.decision_components || typeof c.decision_components !== "object") {
              c.missing_producer_fields.push("decision_components");
            }
            return c;
          };
          const candidateRows = candidateRowsRaw
            .map(function (c) { return normalizeDecisionCandidate(c, whyBlock.chosen_action_id || finalAction); });
          const decisionCandidateSortKey = String(replayState.decisionCandidateSortKey || "decision_score");
          const decisionCandidateSortDir = String(replayState.decisionCandidateSortDir || "desc");
          const candidateSortMultiplier = decisionCandidateSortDir === "asc" ? 1 : -1;
          const candidateSortValue = function (c, key) {
            if (!c || typeof c !== "object") return null;
            if (key === "action_id") return String(c.action_id || "");
            if (key === "unit_id") return String(c.unit_id || c.actor_unit_id || "");
            if (key === "decision_rank") return safeNum(c.decision_rank);
            if (key === "decision_score") return safeNum(c.real_decision_score);
            return null;
          };
          const sortedCandidateRows = candidateRows.slice().sort(function (a, b) {
            const av = candidateSortValue(a, decisionCandidateSortKey);
            const bv = candidateSortValue(b, decisionCandidateSortKey);
            const aNum = typeof av === "number" && Number.isFinite(av);
            const bNum = typeof bv === "number" && Number.isFinite(bv);
            if (aNum && bNum) return candidateSortMultiplier * (av - bv);
            if (aNum && !bNum) return -1;
            if (!aNum && bNum) return 1;
            return candidateSortMultiplier * String(av || "").localeCompare(String(bv || ""));
          });
          const chosenActionWhy = String(whyBlock.chosen_action_id || finalAction || "");
          const vpBestActionWhy = String(whyBlock.vp_best_action_id || "");
          const deltaScoreWhy = safeNum(whyBlock.delta_score);
          const whyShortText = String(stepRow.why_action_vs_vp_text || whyBlock.explanation || "N/A");
          const whyComponents = Array.isArray(whyBlock.score_components_priority) ? whyBlock.score_components_priority : [];
          const hasMctsTelemetry = function (c) {
            if (!c || typeof c !== "object") return false;
            const hasScore = Number.isFinite(Number(c.real_decision_score));
            const hasVisit = Number.isFinite(Number(c.visit_count));
            const hasRank = Number.isFinite(Number(c.decision_rank));
            const hasQ = Number.isFinite(Number(c.mcts_q_value));
            const hasU = Number.isFinite(Number(c.mcts_u_value));
            const hasPrior = Number.isFinite(Number(c.policy_prior));
            return hasScore || hasVisit || hasRank || hasQ || hasU || hasPrior;
          };
          const candidateRowsMcts = sortedCandidateRows.filter(hasMctsTelemetry);
          const candidateRowsLegalOnly = sortedCandidateRows.filter(function (c) { return !hasMctsTelemetry(c); });
          const whyRowsFromCandidates = function (rowsIn) {
            return rowsIn.map(function (c) {
            const actionId = String((c && c.action_id) || "");
            const unitId = String((c && (c.unit_id || c.actor_unit_id)) || "");
            const badges = [];
            if (actionId && actionId === chosenActionWhy) badges.push("chosen");
            if (actionId && actionId === vpBestActionWhy) badges.push("vp-best");
            const vpProgSrc = String((c && c.vp_progress_source) || "unknown");
            const vpProgKnown = vpProgSrc !== "unknown" && !vpProgSrc.startsWith("unavailable_");
            const vpProgDisplay = vpProgKnown ? fmtNum(c ? c.vp_progress_delta : null, 3) : "N/A";
            const realDecisionScore = (c && c.real_decision_score !== undefined && c.real_decision_score !== null)
              ? fmtNum(c.real_decision_score, 3)
              : "N/A";
            const decisionRank = (c && c.decision_rank !== undefined && c.decision_rank !== null)
              ? String(Math.max(1, Number(c.decision_rank || 0)))
              : "N/A";
            const visitCount = (c && c.visit_count !== undefined && c.visit_count !== null)
              ? String(Math.max(0, Number(c.visit_count || 0)))
              : "N/A";
            const selectionSource = String((c && c.selection_source) || "N/A");
            const dc = (c && c.decision_components && typeof c.decision_components === "object") ? c.decision_components : {};
            const dcEntries = Object.keys(dc).length
              ? Object.keys(dc).map(function (k) { return k + "=" + fmtNum(dc[k], 3); }).join(", ")
              : "N/A";
            const missingProducer = (c && Array.isArray(c.missing_producer_fields) && c.missing_producer_fields.length)
              ? (" | missing_producer_fields=" + c.missing_producer_fields.join(","))
              : "";
            return [
              (actionId || "N/A") + (badges.length ? (" [" + badges.join(", ") + "]") : ""),
              unitId || "N/A",
              "real_decision_score=" + realDecisionScore +
              " | decision_rank=" + decisionRank +
              " | visits=" + visitCount +
              " | selection_source=" + selectionSource +
              " | prior=" + fmtNum(c ? c.policy_prior : null, 3) +
              " | Q=" + fmtNum(c ? c.mcts_q_value : null, 3) +
              " | U=" + fmtNum(c ? c.mcts_u_value : null, 3) +
              " | decision_components=" + dcEntries +
              " | vp_prog=" + vpProgDisplay +
              " | vp_prog_src=" + vpProgSrc +
              missingProducer
            ];
            });
          };
          const whyRowsMcts = whyRowsFromCandidates(candidateRowsMcts);
          const whyRowsLegal = whyRowsFromCandidates(candidateRowsLegalOnly);
          const whySummaryRows = [
            ["chosen_action", chosenActionWhy || "N/A"],
            ["vp_best_action", vpBestActionWhy || "N/A"],
            ["delta_score (chosen - vp_best)", deltaScoreWhy === null ? "N/A" : deltaScoreWhy.toFixed(4)],
            ["decision_win_basis", String(stepRow.decision_win_basis || "N/A")],
            ["real_decision_score (selected)", fmtNum(stepRow.real_decision_score, 3)],
            ["selection_source (selected)", String(stepRow.selection_source || "N/A")],
            ["dominant components", whyComponents.length ? whyComponents.join(", ") : "N/A"],
            ["opportunity_vp_weighting_label", String(stepRow.opportunity_vp_weighting_label || "N/A")],
            ["opportunity_fire_no_progress", fmtNum(stepRow.opportunity_fire_no_progress, 3)],
            ["opportunity_skip_capture_preserve", fmtNum(stepRow.opportunity_skip_capture_preserve, 3)],
            ["unit_prefilter_enabled", unitPrefilterEnabled === null ? "N/A" : String(Math.round(unitPrefilterEnabled))],
            ["unit_prefilter_selected_unit_id", unitPrefilterSelectedUnitId || "N/A"],
            ["unit_prefilter_constrained_count", fmtNum(unitPrefilterConstrainedCount, 0)],
            ["unit_prefilter_global_count", fmtNum(unitPrefilterGlobalCount, 0)],
            ["step explanation", whyShortText || "N/A"],
          ];
          const tableHtml = function (rowsIn, emptyMsg) {
            if (!rowsIn.length) return '<tr><td colspan="2" style="border:1px solid #334155;padding:6px;" class="muted">' + esc(emptyMsg) + '</td></tr>';
            const classifyCell = function (txt) {
              const s = String(txt || "");
              if (s === "N/A" || s.indexOf("N/A") >= 0 || s.indexOf("unknown") >= 0 || s.indexOf("WARN") >= 0) return "degraded-text";
              return "ok-text";
            };
            return rowsIn.map(function (r) {
              const value = String(r[1]);
              return '<tr><td style="border:1px solid #334155;padding:6px;width:38%;">' + esc(String(r[0])) + '</td><td style="border:1px solid #334155;padding:6px;"><span class="' + classifyCell(value) + '">' + esc(value) + "</span></td></tr>";
            }).join("");
          };
          const decisionSortArrow = function (key) {
            if (String(replayState.decisionCandidateSortKey || "") !== String(key || "")) return "";
            return String(replayState.decisionCandidateSortDir || "desc") === "asc" ? " ▲" : " ▼";
          };
          host.innerHTML =
            '<div class="muted" style="margin-bottom:6px;">' +
            'step_coverage=<span class="' + (stepCoverage === "complete" ? "ok-text" : "degraded-text") + '">' + esc(stepCoverage) + '</span>' +
            ' | episode_coverage=<span class="' + (episodeCoverage === "complete" ? "ok-text" : "degraded-text") + '">' + esc(episodeCoverage) + "</span>" +
            ' | step_dominance=<span class="ok-text">' + esc(dominantLabel) + "</span>" +
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
            '<div class="muted" style="margin-bottom:4px;">MCTS-evaluated actions (producer-only strict)</div>' +
            '<div id="replayDecisionMctsTableWrap" class="replay-candidate-table-wrap"><table class="replay-candidate-table" style="margin-bottom:8px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;"><button class="replay-candidate-sort-btn" data-candidate-sort-key="action_id">candidate action' + esc(decisionSortArrow("action_id")) + '</button></th>' +
              '<th style="border:1px solid #334155;padding:6px;"><button class="replay-candidate-sort-btn" data-candidate-sort-key="unit_id">unit_id' + esc(decisionSortArrow("unit_id")) + '</button></th>' +
              '<th style="border:1px solid #334155;padding:6px;"><button class="replay-candidate-sort-btn" data-candidate-sort-key="decision_score">score breakdown' + esc(decisionSortArrow("decision_score")) + '</button></th>' +
              '<th style="border:1px solid #334155;padding:6px;"><button class="replay-candidate-sort-btn" data-candidate-sort-key="decision_rank">decision rank' + esc(decisionSortArrow("decision_rank")) + '</button></th>' +
            '</tr></thead><tbody>' + (whyRowsMcts.length
              ? whyRowsMcts.map(function (r) {
                const detailVal = String(r[2]);
                const classifyCell = function (txt) {
                  const s = String(txt || "");
                  if (s === "N/A" || s.indexOf("N/A") >= 0 || s.indexOf("unknown") >= 0 || s.indexOf("WARN") >= 0) return "degraded-text";
                  return "ok-text";
                };
                const rankMatch = detailVal.match(/decision_rank=([^|]+)/);
                const rankText = rankMatch ? String(rankMatch[1] || "").trim() : "N/A";
                return '<tr>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r[0])) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r[1])) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;"><span class="' + classifyCell(detailVal) + '">' + esc(detailVal) + '</span></td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(rankText) + '</td>' +
                '</tr>';
              }).join("")
              : '<tr><td colspan="4" style="border:1px solid #334155;padding:6px;" class="muted">No MCTS-evaluated actions available.</td></tr>') + '</tbody></table></div>' +
            '<div class="muted" style="margin:8px 0 4px 0;">Legal/non-evaluated actions (no MCTS telemetry)</div>' +
            '<div id="replayDecisionLegalTableWrap" class="replay-candidate-table-wrap"><table class="replay-candidate-table" style="margin-bottom:8px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">candidate action</th>' +
              '<th style="border:1px solid #334155;padding:6px;">unit_id</th>' +
              '<th style="border:1px solid #334155;padding:6px;">score breakdown</th>' +
              '<th style="border:1px solid #334155;padding:6px;">decision rank</th>' +
            '</tr></thead><tbody>' + (whyRowsLegal.length
              ? whyRowsLegal.map(function (r) {
                const detailVal = String(r[2]);
                const classifyCell = function (txt) {
                  const s = String(txt || "");
                  if (s === "N/A" || s.indexOf("N/A") >= 0 || s.indexOf("unknown") >= 0 || s.indexOf("WARN") >= 0) return "degraded-text";
                  return "ok-text";
                };
                const rankMatch = detailVal.match(/decision_rank=([^|]+)/);
                const rankText = rankMatch ? String(rankMatch[1] || "").trim() : "N/A";
                return '<tr>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r[0])) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r[1])) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;"><span class="' + classifyCell(detailVal) + '">' + esc(detailVal) + '</span></td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(rankText) + '</td>' +
                '</tr>';
              }).join("")
              : '<tr><td colspan="4" style="border:1px solid #334155;padding:6px;" class="muted">No legal/non-evaluated actions in this step.</td></tr>') + '</tbody></table></div>' +
            '<div class="muted" style="margin-bottom:4px;">Episode aggregation</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">metric</th>' +
              '<th style="border:1px solid #334155;padding:6px;">value</th>' +
            '</tr></thead><tbody>' + tableHtml(episodeRows, "No episode aggregation available.") + '</tbody></table>';
          const sortButtons = host.querySelectorAll("[data-candidate-sort-key]");
          sortButtons.forEach(function (btn) {
            btn.onclick = function () {
              const key = String((btn && btn.getAttribute("data-candidate-sort-key")) || "");
              if (!key) return;
              if (String(replayState.decisionCandidateSortKey || "") === key) {
                replayState.decisionCandidateSortDir = String(replayState.decisionCandidateSortDir || "desc") === "asc" ? "desc" : "asc";
              } else {
                replayState.decisionCandidateSortKey = key;
                replayState.decisionCandidateSortDir = (key === "action_id" || key === "unit_id") ? "asc" : "desc";
              }
              renderDecisionInfluence(stepRow, transitions);
            };
          });
        }
        function replayStateKey() {
          const payload = (replayState && replayState.payload && typeof replayState.payload === "object") ? replayState.payload : {};
          const transitions = Array.isArray(payload.transitions) ? payload.transitions : [];
          return [
            String(replayState.evalId || ""),
            String(Math.max(0, Number(replayState.episodeIndex || 0))),
            String(Math.max(0, Number(replayState.step || 0))),
            String(replayState.unitFilter || "__all__"),
            String(replayState.hoveredUnitId || ""),
            String(replayState.decisionCandidateSortKey || "decision_score"),
            String(replayState.decisionCandidateSortDir || "desc"),
            String(Math.max(1, Math.min(10, Number(replayState.headTopK || 5)))),
            String(transitions.length || 0),
            String(payload.run_id || ""),
          ].join("::");
        }
        function replayMemoRender(hostId, key, renderFn) {
          const host = document.getElementById(hostId);
          if (!host) return;
          const memo = replayState.panelMemo[hostId] || { key: "", html: "" };
          if (memo.key === key) {
            if (memo.html && host.innerHTML !== memo.html) host.innerHTML = memo.html;
            return;
          }
          renderFn();
          memo.key = key;
          memo.html = String(host.innerHTML || "");
          replayState.panelMemo[hostId] = memo;
        }
        function requestReplayDraw(_reason, force) {
          if (force) replayState.drawForcePending = true;
          if (replayState.drawPending) return;
          replayState.drawPending = true;
          replayState.drawRafToken = requestAnimationFrame(function () {
            replayState.drawPending = false;
            replayState.drawRafToken = null;
            const forceDraw = !!replayState.drawForcePending;
            replayState.drawForcePending = false;
            drawReplay(forceDraw);
          });
        }
        function drawReplay(forceDraw) {
          const payloadObj = (replayState.payload && typeof replayState.payload === "object") ? replayState.payload : {};
          const rawEpMeta = Array.isArray(payloadObj.episodes_meta) ? payloadObj.episodes_meta : [];
          const epMeta = rawEpMeta.length
            ? rawEpMeta
            : [{
              episode_index: Math.max(0, Number(payloadObj.selected_episode_index || replayState.episodeIndex || 0)),
              seed: Number(payloadObj.selected_seed || 0),
            }];
          const epSel = document.getElementById("replayEpisodeSelect");
          if (epSel) {
            const epMetaKey = JSON.stringify(epMeta.map(function (e) {
              return [Number(e.episode_index || 0), Number(e.seed || 0)];
            }));
            if (epMetaKey !== replayState.episodesMetaRenderKey) {
              epSel.innerHTML = epMeta.map(function (e, idx) {
                const ordinal = Math.max(0, Number(idx || 0));
                const isSelected = ordinal === Math.max(0, Number(replayState.episodeIndex || 0));
                return `<option value="${esc(String(ordinal))}" ${isSelected ? "selected" : ""}>ep ${esc(String(e.episode_index || ordinal))} seed ${esc(String(e.seed || ""))}</option>`;
              }).join("");
              replayState.episodesMetaRenderKey = epMetaKey;
            }
            if (!epSel.options.length) {
              const fallbackEpisode = Math.max(0, Number(replayState.episodeIndex || 0));
              epSel.innerHTML = `<option value="${esc(String(fallbackEpisode))}">ep ${esc(String(fallbackEpisode))}</option>`;
              replayState.episodesMetaRenderKey = "__fallback__::" + String(fallbackEpisode);
            }
            const desiredEpisodeValue = String(Math.max(0, Number(replayState.episodeIndex || 0)));
            const hasDesiredEpisode = Array.from(epSel.options || []).some(function (opt) {
              return String((opt && opt.value) || "") === desiredEpisodeValue;
            });
            if (hasDesiredEpisode) {
              epSel.value = desiredEpisodeValue;
            } else if (epSel.options.length) {
              epSel.value = String((epSel.options[0] && epSel.options[0].value) || "0");
              replayState.episodeIndex = Math.max(0, Number(epSel.value || 0));
            }
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
          if (
            replayState.hoveredUnitId &&
            !unitOptions.some(function (u) { return String((u && u.unit_id) || "") === String(replayState.hoveredUnitId || ""); })
          ) {
            replayState.hoveredUnitId = "";
          }
          renderReplayUnitFilter(unitOptions);
          const maxStep = Math.max(0, transitions.length - 1);
          replayState.step = Math.max(0, Math.min(maxStep, Number(replayState.step || 0)));
          const stepRowRaw = transitions[replayState.step];
          const stepRow = (stepRowRaw && typeof stepRowRaw === "object") ? stepRowRaw : null;
          const stepRowSafe = stepRow || {};
          const stateKey = replayStateKey();
          if (!forceDraw && stateKey === replayState.lastDrawStateKey) {
            return;
          }
          replayState.lastDrawStateKey = stateKey;
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
            const loadedTransitions = Array.isArray(src.transitions) ? src.transitions.length : 0;
            const totalTransitions = Math.max(loadedTransitions, Number(replayState.transitionsTotal || 0));
            const chunkLabel = totalTransitions > loadedTransitions
              ? (String(loadedTransitions) + "/" + String(totalTransitions))
              : String(loadedTransitions);
            summary.innerHTML =
              "<div><span>Run:</span> <b>" + esc(String(src.run_id || "")) + "</b></div>" +
              "<div><span>Eval:</span> <b>" + esc(String(replayState.evalId || "")) + "</b></div>" +
              "<div><span>Scenario:</span> <b>" + esc(String(src.scenario_id || "")) + "</b></div>" +
              "<div><span>Transitions:</span> <b>" + esc(chunkLabel) + "</b></div>";
          }
          const replayControllerBySide = document.getElementById("replayControllerBySide");
          if (replayControllerBySide) {
            const resolveReplayResultRow = function (evalRow) {
              const rowObj = (evalRow && typeof evalRow === "object") ? evalRow : {};
              const results = Array.isArray(rowObj.results) ? rowObj.results : [];
              if (results.length > 0) {
                // Prefer first concrete result row; eval wrapper rows often
                // do not carry side/controller metadata directly.
                return results[0];
              }
              return rowObj;
            };
            const evalSel = document.getElementById("replayEvalSelect");
            const evalId = String((((evalSel || {}).value) || replayState.evalId || ""));
            const replayEvalRow = evalRows.find(r => String(r.eval_id || "") === String(evalId)) || activeRow || {};
            const replayResultRow = resolveReplayResultRow(replayEvalRow);
            const matchLabel = String(replayResultRow.matchup_profile || replayResultRow.agent_name || "Unknown match");
            const controllerRows = controllerBySideFromResult(replayResultRow);
            const episodeLabel = "ep " + String(Number(replayState.episodeIndex || 0));
            let bySideHtml = '<div class="muted" style="margin-bottom:4px;">match=' + esc(matchLabel) + ' | ' + esc(episodeLabel) + '</div>' +
              '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
              '<th style="border:1px solid #334155;padding:6px;">side</th>' +
              '<th style="border:1px solid #334155;padding:6px;">controller</th>' +
              '<th style="border:1px solid #334155;padding:6px;">source</th>' +
              '</tr></thead><tbody>';
            for (const item of controllerRows) {
              bySideHtml += '<tr>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(String(item.side || "Unlabeled side")) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(String(item.controller || "Unknown/Unlabeled")) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(String(item.source || "fallback")) + '</td>' +
                '</tr>';
            }
            bySideHtml += '</tbody></table>';
            replayControllerBySide.innerHTML = bySideHtml;
          }
          const details = document.getElementById("replayStepDetail");
          if (details) {
            if (!stepRow) {
              details.innerHTML = '<div class="muted">No replay loaded.</div>';
            } else {
              function fmtQrPair(q, r) {
                if (!Number.isFinite(Number(q)) || !Number.isFinite(Number(r))) return "-";
                return String(Number(q)) + "," + String(Number(r));
              }
              function readQrFromObject(obj, keysQ, keysR) {
                if (!obj || typeof obj !== "object") return null;
                const qKeys = Array.isArray(keysQ) ? keysQ : [];
                const rKeys = Array.isArray(keysR) ? keysR : [];
                for (let i = 0; i < Math.min(qKeys.length, rKeys.length); i += 1) {
                  const q = obj[qKeys[i]];
                  const r = obj[rKeys[i]];
                  if (Number.isFinite(Number(q)) && Number.isFinite(Number(r))) {
                    return { q: Number(q), r: Number(r) };
                  }
                }
                return null;
              }
              function readUnitQrFromCollection(collection, unitId) {
                if (!Array.isArray(collection) || !unitId) return null;
                const wanted = String(unitId || "");
                const unit = collection.find(function (u) { return String((u && u.unit_id) || "") === wanted; });
                if (!unit || typeof unit !== "object") return null;
                return readQrFromObject(unit, ["q", "hex_q", "target_q", "to_q", "current_q"], ["r", "hex_r", "target_r", "to_r", "current_r"]);
              }
              function readActionDestination(step) {
                if (!step || typeof step !== "object") return null;
                const direct = readQrFromObject(step, ["target_q", "to_q", "action_target_q"], ["target_r", "to_r", "action_target_r"]);
                if (direct) return direct;
                const parts = String(step.action_id || "").split(":");
                if (parts.length < 4) return null;
                const q = Number(parts[2]);
                const r = Number(parts[3]);
                if (!Number.isFinite(q) || !Number.isFinite(r)) return null;
                return { q, r };
              }
              function deriveStepPositions(step, transitions, stepIdx) {
                const unitId = String((step && step.unit_id) || "");
                const currentCandidates = [
                  readActionDestination(step),
                  readQrFromObject(step, ["current_q", "to_q", "q"], ["current_r", "to_r", "r"]),
                  readUnitQrFromCollection(step && step.units, unitId),
                ];
                const current = currentCandidates.find(Boolean) || null;
                const previousCandidates = [
                  readQrFromObject(step, ["previous_q", "from_q", "pre_q"], ["previous_r", "from_r", "pre_r"]),
                  readQrFromObject(step && step.unit_before, ["q", "hex_q", "current_q"], ["r", "hex_r", "current_r"]),
                  readQrFromObject(step && step.pre_step_unit, ["q", "hex_q", "current_q"], ["r", "hex_r", "current_r"]),
                  readQrFromObject(step && step.unit_snapshot_before, ["q", "hex_q", "current_q"], ["r", "hex_r", "current_r"]),
                ];
                const prevRow = (Array.isArray(transitions) && Number.isFinite(Number(stepIdx)) && Number(stepIdx) > 0)
                  ? transitions[Number(stepIdx) - 1]
                  : null;
                previousCandidates.push(readUnitQrFromCollection(prevRow && prevRow.units, unitId));
                previousCandidates.push(readQrFromObject(prevRow, ["target_q", "current_q", "to_q"], ["target_r", "current_r", "to_r"]));
                const previous = previousCandidates.find(Boolean) || null;
                return {
                  previousPosition: fmtQrPair(previous && previous.q, previous && previous.r),
                  currentPosition: fmtQrPair(current && current.q, current && current.r),
                };
              }
              const tq = (stepRow.target_q === undefined || stepRow.target_q === null) ? "-" : String(stepRow.target_q);
              const tr = (stepRow.target_r === undefined || stepRow.target_r === null) ? "-" : String(stepRow.target_r);
              const targetQr = tq + "," + tr;
              const positions = deriveStepPositions(stepRow, transitions, replayState.step);
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
                    '<tr><td style="border:1px solid #334155;padding:6px;">previous_position</td><td style="border:1px solid #334155;padding:6px;">' + esc(positions.previousPosition) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">current_position</td><td style="border:1px solid #334155;padding:6px;">' + esc(positions.currentPosition) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">reward</td><td style="border:1px solid #334155;padding:6px;">' + esc(Number(stepRow.reward || 0).toFixed(4)) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">damage / kills</td><td style="border:1px solid #334155;padding:6px;">' + esc(dmgKills) + '</td></tr>' +
                    '<tr><td style="border:1px solid #334155;padding:6px;">telemetry_coverage</td><td style="border:1px solid #334155;padding:6px;">' + esc(coverageTxt) + '</td></tr>' +
                  '</tbody>' +
                '</table>';
            }
          }
          try {
            replayMemoRender("replayHeadDiagnosticsHost", "head::" + stateKey, function () {
              renderReplayHeadDiagnostics(stepRowSafe);
            });
          } catch (_e) {
            const hostHead = document.getElementById("replayHeadDiagnosticsHost");
            if (hostHead) hostHead.innerHTML = '<div class="muted">Head Diagnostics render error.</div>';
          }
          try {
            replayMemoRender("replayDecisionInfluenceHost", "decision::" + stateKey, function () {
              renderDecisionInfluence(stepRowSafe, transitions);
            });
          } catch (_e) {
            const hostDecision = document.getElementById("replayDecisionInfluenceHost");
            if (hostDecision) hostDecision.innerHTML = '<div class="muted">Decision Influence render error.</div>';
          }
          const canvas = document.getElementById("replayCanvas");
          if (canvas && canvas.getContext) {
            replayBindCanvasHoverHandlers(canvas);
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
                  requestReplayDraw("layout-retry", true);
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
              const canvasKey = [
                stateKey,
                String(cssW),
                String(cssH),
                String(dpr),
              ].join("::");
              if (!forceDraw && replayState.lastCanvasDrawKey === canvasKey) {
                // Skip redundant canvas redraw when both state and size are unchanged.
              } else {
                replayState.lastCanvasDrawKey = canvasKey;
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
              const hasStepObj = !!stepRow && typeof stepRow === "object";
              const rawTargetQ = hasStepObj ? stepRow.target_q : null;
              const rawTargetR = hasStepObj ? stepRow.target_r : null;
              const tQ = Number.isFinite(Number(rawTargetQ)) ? Number(rawTargetQ) : null;
              const tR = Number.isFinite(Number(rawTargetR)) ? Number(rawTargetR) : null;
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
              }
              if (!baseCells.length && shape.length >= 2 && Number(shape[0]) > 0 && Number(shape[1]) > 0) {
                const wCells = Math.max(1, Number(shape[0]));
                const hCells = Math.max(1, Number(shape[1]));
                for (let r = 0; r < hCells; r += 1) {
                  for (let q = 0; q < wCells; q += 1) {
                    baseCells.push({ q, r });
                  }
                }
              }
              if (!baseCells.length) {
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
                drawHexCoordLabel(ctx, p.x, p.y, size, c.q, c.r);
              }
              const hoverUnitId = String(replayState.hoveredUnitId || "").trim();
              const overlayHexes = replayCollectUnitHexCandidates(stepRow, hoverUnitId);
              const moveHexes = Array.isArray(overlayHexes.moveHexes) ? overlayHexes.moveHexes : [];
              const attackHexes = Array.isArray(overlayHexes.attackHexes) ? overlayHexes.attackHexes : [];
              for (const hx of moveHexes) {
                const q = Number(hx && hx.q);
                const r = Number(hx && hx.r);
                if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
                const p = proj.toPixel(q, r);
                drawHex(ctx, p.x, p.y, size * 1.03, "#22c55e", "rgba(34,197,94,0.24)");
              }
              for (const hx of attackHexes) {
                const q = Number(hx && hx.q);
                const r = Number(hx && hx.r);
                if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
                const p = proj.toPixel(q, r);
                drawHex(ctx, p.x, p.y, size * 1.03, "#ef4444", "rgba(239,68,68,0.20)");
              }
              const points = [];
              for (const u of unitCoords) {
                const px = proj.toPixel(u.q, u.r);
                points.push(Object.assign({}, u, px));
              }
              replayState.hoverHitPoints = points;
              replayState.hoverHitRadius = Math.max(6, size * 0.58);
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
                hasStepObj &&
                Number.isFinite(Number(rawTargetQ)) &&
                Number.isFinite(Number(rawTargetR)) &&
                Number((stepRow.attack_distance_mean === undefined || stepRow.attack_distance_mean === null) ? -1 : stepRow.attack_distance_mean) >= 0
              ) {
                const t = proj.toPixel(Number(rawTargetQ), Number(rawTargetR));
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
              const legend = document.getElementById("replayHoverLegend");
              if (legend) {
                if (hoverUnitId) {
                  legend.title = "hover unit=" + hoverUnitId + " | move=" + String(moveHexes.length) + " | attack=" + String(attackHexes.length);
                } else {
                  legend.title = "Hover a unit to preview move/attack hexes";
                }
              }
              }
            }
          }
          replayMemoRender("replayHoverActionsHost", "hover::" + stateKey, function () {
            renderReplayHoveredActions(stepRowSafe);
          });
          const unitsHost = document.getElementById("replayUnitsHost");
          if (unitsHost) {
            const parseSuppressedValue = function (raw) {
              if (raw === null || raw === undefined || raw === "") return null;
              if (typeof raw === "boolean") return raw;
              if (typeof raw === "number") return Number.isFinite(raw) ? (raw !== 0) : null;
              const txt = String(raw).trim().toLowerCase();
              if (!txt) return null;
              if (txt === "1" || txt === "true" || txt === "yes" || txt === "y" || txt === "on") return true;
              if (txt === "0" || txt === "false" || txt === "no" || txt === "n" || txt === "off") return false;
              return null;
            };
            const formatSuppressedLabel = function (value) {
              return value === null ? "N/A" : (value ? "yes" : "no");
            };
            const suppressedValueForUnit = function (stepRowObj, unitObj) {
              const unitId = String((unitObj && unitObj.unit_id) || "").trim();
              const mapRaw = (stepRowObj && typeof stepRowObj === "object")
                ? stepRowObj.unit_suppressed_map
                : null;
              if (mapRaw && typeof mapRaw === "object" && unitId && Object.prototype.hasOwnProperty.call(mapRaw, unitId)) {
                const mapped = parseSuppressedValue(mapRaw[unitId]);
                if (mapped !== null) return mapped;
              }
              if (!unitObj || typeof unitObj !== "object") return null;
              const producerKeys = ["suppressed", "is_suppressed", "pinned", "is_pinned"];
              for (const key of producerKeys) {
                if (!Object.prototype.hasOwnProperty.call(unitObj, key)) continue;
                const parsed = parseSuppressedValue(unitObj[key]);
                if (parsed !== null) return parsed;
              }
              return null;
            };
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
              '<th style="border:1px solid #334155;padding:6px;">suppressed</th>' +
              '</tr></thead><tbody>';
            if (!units.length) {
              unitsHtml += '<tr><td colspan="7" style="border:1px solid #334155;padding:6px;" class="muted">No units for selected filter.</td></tr>';
            } else {
              for (const u of units) {
                const hex = String(u.q) + "," + String(u.r);
                const unitWithId = String(u.unit_id || "") + " - " + String(u.unit_label || u.unit_key || "");
                const suppressedLabel = formatSuppressedLabel(suppressedValueForUnit(stepRow, u));
                unitsHtml += '<tr>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(u.side) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(u.unit_id) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(unitWithId) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(hex) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(u.hp || 0).toFixed(1)) + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(Boolean(u.alive) ? "yes" : "no") + '</td>' +
                  '<td style="border:1px solid #334155;padding:6px;">' + esc(suppressedLabel) + '</td>' +
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
        };
        const epSelect = document.getElementById("replayEpisodeSelect");
        if (epSelect) epSelect.onchange = async () => {
          replayState.episodeIndex = Math.max(0, Number(
            (Number.isFinite(Number(epSelect.selectedIndex)) && Number(epSelect.selectedIndex) >= 0)
              ? epSelect.selectedIndex
              : (epSelect.value || 0)
          ));
          await loadReplay();
        };
        const loadBtn = document.getElementById("replayLoadBtn");
        if (loadBtn) loadBtn.onclick = async () => {
          await loadReplay();
        };
        const replayRangeInput = document.getElementById("replayStepRange");
        if (replayRangeInput) replayRangeInput.oninput = () => {
          replayState.step = Math.max(0, Number(replayRangeInput.value || 0));
          setReplayStepNavFeedback("");
          drawReplay();
          scheduleReplayLogLoad(120);
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
        window.onresize = () => {
          if (replayState.resizeRafToken) cancelAnimationFrame(replayState.resizeRafToken);
          replayState.resizeRafToken = requestAnimationFrame(() => {
            replayState.resizeRafToken = null;
            drawReplay();
          });
        };
        drawReplay();
        setTimeout(() => drawReplay(), 0);
        setTimeout(() => drawReplay(), 60);
        scheduleReplayLogLoad(0);
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

        const resultRows = (flowRows || [])
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
      ["tabTrainDetailBtn", "tabTrainHeadDiagnosticsBtn", "tabObjectiveRewardConfigBtn", "tabMuzeroVpsBtn", "tabHeadDiagnosticsBtn", "tabEvalMetricsBtn", "tabUnifiedBtn", "tabEvalDecisionsBtn", "tabReplayBtn", "tabOverviewBtn"].forEach(id => {
        const n = el(id);
        if (!n) return;
        const sec = n.getAttribute("data-section");
        n.style.display = (sec === section) ? "" : "none";
      });
      const filtersHost = el("analysisFiltersHost");
      if (filtersHost) filtersHost.style.display = (section === "eval") ? "block" : "none";
      if (section === "train" && activeTab !== "train-detail" && activeTab !== "train-head-diagnostics" && activeTab !== "objective-reward-config") switchTab("train-detail");
      if (section === "eval" && activeTab !== "vps" && activeTab !== "head-diagnostics" && activeTab !== "eval-metrics" && activeTab !== "unified" && activeTab !== "eval-decisions" && activeTab !== "replay") switchTab("vps");
      if (section === "meta" && activeTab !== "overview") switchTab("overview");
    }

    function switchTab(tab) {
      activeTab = tab;
      const tOverviewBtn = el("tabOverviewBtn");
      const tVpsBtn = el("tabMuzeroVpsBtn");
      const tHeadDiagBtn = el("tabHeadDiagnosticsBtn");
      const tEvalMetricsBtn = el("tabEvalMetricsBtn");
      const tUnifiedBtn = el("tabUnifiedBtn");
      const tDecisionsBtn = el("tabEvalDecisionsBtn");
      const tReplayBtn = el("tabReplayBtn");
      const tTrainDetailBtn = el("tabTrainDetailBtn");
      const tTrainHeadDiagBtn = el("tabTrainHeadDiagnosticsBtn");
      const tObjectiveRewardConfigBtn = el("tabObjectiveRewardConfigBtn");
      const pOverview = el("tabOverview");
      const pVps = el("tabMuzeroVps");
      const pHeadDiag = el("tabHeadDiagnostics");
      const pEvalMetrics = el("tabEvalMetrics");
      const pUnified = el("tabUnified");
      const pDecisions = el("tabEvalDecisions");
      const pReplay = el("tabReplay");
      const pTrainDetail = el("tabTrainDetail");
      const pTrainHeadDiag = el("tabTrainHeadDiagnostics");
      const pObjectiveRewardConfig = el("tabObjectiveRewardConfig");
      if (tOverviewBtn) tOverviewBtn.classList.toggle("active", tab === "overview");
      if (tVpsBtn) tVpsBtn.classList.toggle("active", tab === "vps");
      if (tHeadDiagBtn) tHeadDiagBtn.classList.toggle("active", tab === "head-diagnostics");
      if (tEvalMetricsBtn) tEvalMetricsBtn.classList.toggle("active", tab === "eval-metrics");
      if (tUnifiedBtn) tUnifiedBtn.classList.toggle("active", tab === "unified");
      if (tDecisionsBtn) tDecisionsBtn.classList.toggle("active", tab === "eval-decisions");
      if (tReplayBtn) tReplayBtn.classList.toggle("active", tab === "replay");
      if (tTrainDetailBtn) tTrainDetailBtn.classList.toggle("active", tab === "train-detail");
      if (tTrainHeadDiagBtn) tTrainHeadDiagBtn.classList.toggle("active", tab === "train-head-diagnostics");
      if (tObjectiveRewardConfigBtn) tObjectiveRewardConfigBtn.classList.toggle("active", tab === "objective-reward-config");
      if (pOverview) pOverview.classList.toggle("active", tab === "overview");
      if (pVps) pVps.classList.toggle("active", tab === "vps");
      if (pHeadDiag) pHeadDiag.classList.toggle("active", tab === "head-diagnostics");
      if (pEvalMetrics) pEvalMetrics.classList.toggle("active", tab === "eval-metrics");
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
    const nTabEvalMetrics = el("tabEvalMetricsBtn");
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
    if (nTabEvalMetrics) nTabEvalMetrics.onclick = () => switchTab("eval-metrics");
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
                chunk_offset = max(0, int(qs.get("chunk_offset", ["0"])[0] or 0))
                chunk_limit = max(1, int(qs.get("chunk_limit", ["80"])[0] or 80))
                rp = _resolve_replay_path(eval_source_path=eval_source_path, explicit_replay_path=replay_path)
                payload: dict = {
                    "replay_path": str(rp) if rp is not None else "",
                    "episodes_meta": [],
                    "transitions": [],
                    "transitions_total": 0,
                    "transitions_offset": int(chunk_offset),
                    "transitions_limit": int(chunk_limit),
                    "transitions_has_more": False,
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
                            all_transitions = list(selected.get("transitions", []) or [])
                            total = int(len(all_transitions))
                            start = max(0, min(int(chunk_offset), total))
                            end = max(start, min(total, start + int(chunk_limit)))
                            payload["transitions_total"] = total
                            payload["transitions"] = all_transitions[start:end]
                            payload["transitions_has_more"] = bool(end < total)
                    except Exception as exc:
                        payload["error"] = f"failed to load replay: {exc}"
                else:
                    payload["error"] = "replay file not found"
                    src_raw = str(eval_source_path or "").strip()
                    if src_raw:
                        src = Path(src_raw).expanduser().resolve()
                        if src.exists():
                            try:
                                raw_eval = json.loads(src.read_text(encoding="utf-8"))
                                results = list(raw_eval.get("results", []) or [])
                                selected_row = next(
                                    (
                                        r
                                        for r in results
                                        if isinstance(r, dict)
                                        and str(r.get("agent_name", "") or "").strip().lower() == "muzero_stub"
                                    ),
                                    None,
                                )
                                if selected_row is None:
                                    selected_row = next((r for r in results if isinstance(r, dict)), None)
                                step_rows = []
                                if isinstance(selected_row, dict):
                                    step_rows = list(selected_row.get("eval_decision_steps_top", []) or [])
                                if step_rows:
                                    payload["error"] = ""
                                    payload["schema_version"] = "bench_eval_fallback_v1"
                                    payload["run_id"] = str(raw_eval.get("run_id", "") or "")
                                    payload["scenario_id"] = str(raw_eval.get("scenario_id", "") or "")
                                    payload["bench_id"] = str(src.stem or "")
                                    payload["scenario_overlay"] = _load_scenario_overlay(
                                        repo_root=repo_root,
                                        scenario_id=str(raw_eval.get("scenario_id", "") or ""),
                                    )
                                    payload["episodes_meta"] = [
                                        {
                                            "episode_index": 0,
                                            "seed": 0,
                                            "agent_name": str((selected_row or {}).get("agent_name", "") or ""),
                                            "transitions": int(len(step_rows)),
                                        }
                                    ]
                                    payload["selected_episode_index"] = 0
                                    payload["selected_seed"] = 0
                                    payload["selected_agent_name"] = str(
                                        (selected_row or {}).get("agent_name", "") or ""
                                    )
                                    total = int(len(step_rows))
                                    start = max(0, min(int(chunk_offset), total))
                                    end = max(start, min(total, start + int(chunk_limit)))
                                    payload["transitions_total"] = total
                                    payload["transitions"] = step_rows[start:end]
                                    payload["transitions_has_more"] = bool(end < total)
                            except Exception as exc:
                                payload["error"] = f"failed to load eval fallback: {exc}"
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
