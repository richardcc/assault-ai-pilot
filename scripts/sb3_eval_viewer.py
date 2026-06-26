from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_rows(report: dict) -> list[dict]:
    rows: list[dict] = []
    by_side = report.get("by_side_and_scenario", {}) or {}
    for side, scenarios in by_side.items():
        for scenario, payload in (scenarios or {}).items():
            summary = payload.get("summary", {}) or {}
            mission = payload.get("mission", {}) or {}
            captured_final_counts = summary.get("captured_final_counts", {}) or {}
            captured_final_total = 0.0
            captured_final_n = 0.0
            for k, v in captured_final_counts.items():
                try:
                    bucket = float(k)
                    count = float(v)
                except Exception:
                    continue
                captured_final_total += bucket * count
                captured_final_n += count
            rows.append(
                {
                    "side": str(side),
                    "scenario": str(scenario),
                    "score_win_rate": _safe_float(
                        summary.get("win_score_rate", summary.get("win_rate", 0.0))
                    ),
                    "true_win_rate": _safe_float(summary.get("true_win_rate", 0.0)),
                    "draw_rate": _safe_float(summary.get("draw_rate", 0.0)),
                    "loss_rate": _safe_float(summary.get("loss_rate", 0.0)),
                    "avg_vp": _safe_float(summary.get("avg_vp", 0.0)),
                    "avg_steps": _safe_float(summary.get("avg_steps", 0.0)),
                    "vp_entry_conversion_rate": _safe_float(
                        mission.get("vp_entry_conversion_rate", 0.0)
                    ),
                    "capture_conversion_after_contact": _safe_float(
                        mission.get("capture_conversion_after_contact", 0.0)
                    ),
                    "capture_attempt_success_rate": _safe_float(
                        mission.get("capture_attempt_success_rate", 0.0)
                    ),
                    "vp_entries_taken": _safe_float(
                        mission.get("vp_entries_taken", 0.0)
                    ),
                    "captured_final_avg": (
                        (captured_final_total / captured_final_n) if captured_final_n > 0 else 0.0
                    ),
                    "sb3_kept": _safe_float(
                        (mission.get("source_mix_rates", {}) or {}).get("sb3_kept", 0.0)
                    ),
                    "finalizer_override": _safe_float(
                        (mission.get("source_mix_rates", {}) or {}).get(
                            "finalizer_override", 0.0
                        )
                    ),
                    "planner_override": _safe_float(
                        (mission.get("source_mix_rates", {}) or {}).get(
                            "planner_override", 0.0
                        )
                    ),
                    "finalizer_override_reason_counts": mission.get(
                        "finalizer_override_reason_counts", {}
                    )
                    or {},
                }
            )
    return rows


def _build_details(report: dict) -> list[dict]:
    details: list[dict] = []
    by_side = report.get("by_side_and_scenario", {}) or {}
    for side, scenarios in by_side.items():
        for scenario, payload in (scenarios or {}).items():
            details.append(
                {
                    "side": str(side),
                    "scenario": str(scenario),
                    "summary": payload.get("summary", {}) or {},
                    "combat": payload.get("combat", {}) or {},
                    "advanced": payload.get("advanced", {}) or {},
                    "mission": payload.get("mission", {}) or {},
                    "policy_alignment": payload.get("policy_alignment", {}) or {},
                    "action_execution": payload.get("action_execution", {}) or {},
                    "units": payload.get("units", {}) or {},
                    "strategy": payload.get("strategy", {}) or {},
                }
            )
    return details


def _build_history_points(
    reports_dir: Path,
    limit: int = 60,
    side_filter: str = "",
    scenario_filter: str = "",
) -> list[dict]:
    files = sorted(
        reports_dir.glob("metrics_sb3_report_*.json"),
        key=lambda p: p.stat().st_mtime,
    )[-max(1, int(limit)) :]
    points: list[dict] = []
    for p in files:
        try:
            data = _read_json(p)
            meta = data.get("meta", {}) or {}
            rows = _build_rows(data)
            if side_filter:
                rows = [r for r in rows if str(r.get("side", "")).upper() == side_filter.upper()]
            if scenario_filter:
                rows = [r for r in rows if str(r.get("scenario", "")) == scenario_filter]
            if not rows:
                continue
            n = len(rows)
            agg = {
                "score_win_rate": sum(_safe_float(r.get("score_win_rate", 0.0)) for r in rows) / n,
                "loss_rate": sum(_safe_float(r.get("loss_rate", 0.0)) for r in rows) / n,
                "vp_entry_conversion_rate": sum(
                    _safe_float(r.get("vp_entry_conversion_rate", 0.0)) for r in rows
                )
                / n,
                "capture_conversion_after_contact": sum(
                    _safe_float(r.get("capture_conversion_after_contact", 0.0)) for r in rows
                )
                / n,
                "vp_entries_taken": sum(
                    _safe_float(r.get("vp_entries_taken", 0.0)) for r in rows
                )
                / n,
                "captured_final_avg": sum(
                    _safe_float(r.get("captured_final_avg", 0.0)) for r in rows
                )
                / n,
                "sb3_kept": sum(_safe_float(r.get("sb3_kept", 0.0)) for r in rows) / n,
                "finalizer_override": sum(
                    _safe_float(r.get("finalizer_override", 0.0)) for r in rows
                )
                / n,
            }
            points.append(
                {
                    "report": p.name,
                    "timestamp": str(meta.get("timestamp") or ""),
                    "seed": meta.get("seed"),
                    **agg,
                }
            )
        except Exception:
            continue
    return points


def _latest_report_path(reports_dir: Path) -> Path | None:
    files = sorted(reports_dir.glob("metrics_sb3_report_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _page_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>SB3 Eval Viewer</title>
  <style>
    :root { color-scheme: dark; --bg:#0f1117; --panel:#171a23; --txt:#e6e8ef; --muted:#a7afc0; --ok:#2ecc71; --warn:#f1c40f; --bad:#e74c3c; --border:#2a3040; --accent:#4aa3ff; }
    body { margin:0; padding:20px; background:var(--bg); color:var(--txt); font:14px/1.35 Segoe UI, Inter, system-ui, sans-serif; }
    h1 { margin:0 0 12px; font-size:22px; }
    .top { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
    .panel { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:12px; }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; margin:12px 0; }
    .card h3 { margin:0; font-size:12px; color:var(--muted); font-weight:600; }
    .card .v { margin-top:6px; font-size:24px; font-weight:700; }
    .ok { color:var(--ok);} .warn { color:var(--warn);} .bad { color:var(--bad);}
    table { width:100%; border-collapse:collapse; }
    th,td { padding:8px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }
    th { color:var(--muted); font-weight:600; font-size:12px; }
    .bar { height:8px; background:#242a38; border-radius:999px; overflow:hidden; margin-top:4px; }
    .bar > span { display:block; height:100%; background:var(--accent); }
    .sub { color:var(--muted); font-size:12px; }
    .reason { font-family:Consolas, monospace; font-size:12px; display:block; margin:2px 0; }
    button, select { background:#1f2532; color:var(--txt); border:1px solid var(--border); border-radius:8px; padding:8px 10px; }
    .tabs { display:flex; gap:8px; margin:12px 0; flex-wrap:wrap; }
    .tab-btn { cursor:pointer; }
    .tab-btn.active { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) inset; }
    .tab-content { display:none; }
    .tab-content.active { display:block; }
    .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:8px; }
    .kv .k { color:var(--muted); font-size:12px; }
    .kv .v { font-weight:600; font-size:16px; margin-top:2px; }
    .hist-grid { display:grid; grid-template-columns:1fr; gap:10px; }
    .sparkline { width:100%; height:72px; background:#10141d; border:1px solid var(--border); border-radius:8px; padding:8px; box-sizing:border-box; }
    .units-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:10px; }
  </style>
</head>
<body>
  <h1>SB3 Eval Viewer</h1>
  <div class="top panel">
    <label>Report:
      <select id="reportSelect"></select>
    </label>
    <button id="reloadBtn">Reload</button>
    <span id="meta" class="sub"></span>
  </div>

  <div class="cards" id="cards"></div>

  <div class="tabs">
    <button class="tab-btn active" data-tab="overview">Overview</button>
    <button class="tab-btn" data-tab="training">Training</button>
    <button class="tab-btn" data-tab="mission">Mission</button>
    <button class="tab-btn" data-tab="vps">VPs</button>
    <button class="tab-btn" data-tab="combats">Combats</button>
    <button class="tab-btn" data-tab="overrides">Overrides</button>
    <button class="tab-btn" data-tab="actions">Actions</button>
    <button class="tab-btn" data-tab="units">Units/Side</button>
    <button class="tab-btn" data-tab="strategy">Strategies</button>
    <button class="tab-btn" data-tab="history">History</button>
  </div>

  <div id="tab-overview" class="tab-content active panel">
    <h3 style="margin-top:0">By Side / Scenario</h3>
    <table id="rowsTable">
      <thead>
        <tr>
          <th>Side</th><th>Scenario</th><th>Score Win</th><th>Loss</th>
          <th>VP Entry Conv</th><th>Capture Conv After Contact</th>
          <th>VP Captured (run)</th><th>VP Captured Final</th>
          <th>SB3 Kept</th><th>Finalizer Override</th><th>Top Finalizer Reasons</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div id="tab-training" class="tab-content panel">
    <h3 style="margin-top:0">Training & Outcome Details</h3>
    <div id="trainingDetail" class="kv"></div>
  </div>

  <div id="tab-mission" class="tab-content panel">
    <h3 style="margin-top:0">Mission Metrics Details</h3>
    <div id="missionDetail" class="kv"></div>
  </div>

  <div id="tab-vps" class="tab-content panel">
    <h3 style="margin-top:0">VP Details</h3>
    <div id="vpDetail" class="kv"></div>
    <div id="vpTables" style="margin-top:10px"></div>
  </div>

  <div id="tab-combats" class="tab-content panel">
    <h3 style="margin-top:0">All Combats</h3>
    <div id="combatsDetail" class="kv"></div>
    <div id="combatsTables" style="margin-top:10px"></div>
  </div>

  <div id="tab-overrides" class="tab-content panel">
    <h3 style="margin-top:0">Override Breakdown</h3>
    <table id="overrideTable">
      <thead><tr><th>Reason</th><th>Count</th><th>Rate</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>

  <div id="tab-actions" class="tab-content panel">
    <h3 style="margin-top:0">Action Execution</h3>
    <div id="actionsDetail"></div>
  </div>

  <div id="tab-units" class="tab-content panel">
    <h3 style="margin-top:0">Unit Analysis by Side</h3>
    <div id="unitsDetail" class="units-grid"></div>
  </div>

  <div id="tab-strategy" class="tab-content panel">
    <h3 style="margin-top:0">Strategy Analysis</h3>
    <div id="strategyDetail"></div>
  </div>

  <div id="tab-history" class="tab-content panel">
    <h3 style="margin-top:0">History (latest reports)</h3>
    <div class="top" style="margin-bottom:8px">
      <label>Points: <select id="historyLimit">
        <option value="20">20</option>
        <option value="40" selected>40</option>
        <option value="80">80</option>
      </select></label>
      <label>Side:
        <select id="historySide">
          <option value="">(all)</option>
          <option value="US">US</option>
          <option value="IT">IT</option>
        </select>
      </label>
      <label>Scenario:
        <input id="historyScenario" placeholder="battaglia_cittadina_2_1" style="min-width:260px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:8px 10px;" />
      </label>
      <button id="historyReloadBtn">Reload History</button>
      <button id="historyExportBtn">Export CSV</button>
    </div>
    <div id="historyCharts" class="hist-grid"></div>
    <table id="historyTable" style="margin-top:10px">
      <thead>
        <tr>
          <th>Report</th><th>Timestamp</th><th>Loss</th><th>VP Entry Conv</th>
          <th>Capture Conv</th><th>VP Captured (run)</th><th>VP Captured Final</th>
          <th>SB3 Kept</th><th>Finalizer Override</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

<script>
function clsByRate(v, goodHigh=true){
  if (goodHigh) return v>=0.30?'ok':(v>=0.20?'warn':'bad');
  return v<=0.40?'ok':(v<=0.60?'warn':'bad');
}
function pct(v){ return (100*v).toFixed(1)+'%'; }
function asVpCount(v){ return Number(v||0).toFixed(2); }
function capturedFinalAvgFromSummary(summary){
  const counts = (summary && summary.captured_final_counts) ? summary.captured_final_counts : {};
  let total = 0;
  let n = 0;
  for (const [k,v] of Object.entries(counts)){
    const bucket = Number(k);
    const count = Number(v||0);
    if (!Number.isFinite(bucket) || !Number.isFinite(count)) continue;
    total += bucket * count;
    n += count;
  }
  return n > 0 ? (total / n) : 0;
}
async function getJson(url){ const r=await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }
let currentDetails = [];
let historyPoints = [];

function firstDetail(){
  return (currentDetails && currentDetails.length) ? currentDetails[0] : null;
}

async function loadReports() {
  const data = await getJson('/api/reports');
  const sel = document.getElementById('reportSelect');
  const prev = sel.value;
  sel.innerHTML = '';
  for (const name of data.reports){
    const o=document.createElement('option'); o.value=name; o.textContent=name; sel.appendChild(o);
  }
  if (prev && data.reports.includes(prev)) sel.value=prev;
  else if (data.latest) sel.value=data.latest;
}

function renderCards(rows){
  const n = rows.length || 1;
  const agg = rows.reduce((a,r)=>({
    score_win_rate:a.score_win_rate+r.score_win_rate,
    loss_rate:a.loss_rate+r.loss_rate,
    vp_entry_conversion_rate:a.vp_entry_conversion_rate+r.vp_entry_conversion_rate,
    capture_conversion_after_contact:a.capture_conversion_after_contact+r.capture_conversion_after_contact,
    vp_entries_taken:a.vp_entries_taken+r.vp_entries_taken,
    captured_final_avg:a.captured_final_avg+r.captured_final_avg,
    sb3_kept:a.sb3_kept+r.sb3_kept,
    finalizer_override:a.finalizer_override+r.finalizer_override
  }), {score_win_rate:0,loss_rate:0,vp_entry_conversion_rate:0,capture_conversion_after_contact:0,vp_entries_taken:0,captured_final_avg:0,sb3_kept:0,finalizer_override:0});
  for (const k in agg) agg[k]/=n;
  const cards = [
    ['Score Win Rate', agg.score_win_rate, true],
    ['Loss Rate', agg.loss_rate, false],
    ['VP Entry Conversion', agg.vp_entry_conversion_rate, true],
    ['Capture Conversion', agg.capture_conversion_after_contact, true],
    ['VP Captured (run)', agg.vp_entries_taken/3.0, true],
    ['VP Captured Final', agg.captured_final_avg/3.0, true],
    ['SB3 Kept', agg.sb3_kept, true],
    ['Finalizer Override', agg.finalizer_override, false],
  ];
  const root = document.getElementById('cards');
  root.innerHTML = '';
  for (const [name,val,goodHigh] of cards){
    const c = document.createElement('div');
    c.className='panel card';
    const isCountCard = name.startsWith('VP Captured');
    const display = isCountCard ? asVpCount(val*3.0) : pct(val);
    c.innerHTML = `<h3>${name}</h3><div class="v ${clsByRate(val,goodHigh)}">${display}</div><div class="bar"><span style="width:${Math.max(0,Math.min(100,val*100))}%"></span></div>`;
    root.appendChild(c);
  }
}

function renderRows(rows){
  const tb = document.querySelector('#rowsTable tbody');
  tb.innerHTML='';
  for (const r of rows){
    const topReasons = Object.entries(r.finalizer_override_reason_counts||{})
      .sort((a,b)=>b[1]-a[1]).slice(0,4)
      .map(([k,v])=>`<span class="reason">${k}: ${v}</span>`).join('') || '<span class="sub">-</span>';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r.side}</td>
      <td>${r.scenario}</td>
      <td class="${clsByRate(r.score_win_rate,true)}">${pct(r.score_win_rate)}</td>
      <td class="${clsByRate(r.loss_rate,false)}">${pct(r.loss_rate)}</td>
      <td class="${clsByRate(r.vp_entry_conversion_rate,true)}">${pct(r.vp_entry_conversion_rate)}</td>
      <td class="${clsByRate(r.capture_conversion_after_contact,true)}">${pct(r.capture_conversion_after_contact)}</td>
      <td>${asVpCount(r.vp_entries_taken)}</td>
      <td>${asVpCount(r.captured_final_avg)}</td>
      <td>${pct(r.sb3_kept)}</td>
      <td>${pct(r.finalizer_override)}</td>
      <td>${topReasons}</td>`;
    tb.appendChild(tr);
  }
}

function renderKV(rootId, items){
  const root = document.getElementById(rootId);
  root.innerHTML = '';
  for (const [k,v] of items){
    const d = document.createElement('div');
    d.className = 'panel';
    d.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
    root.appendChild(d);
  }
}

function renderTraining(){
  const d = firstDetail();
  if (!d){ renderKV('trainingDetail', [['No data','-']]); return; }
  const s = d.summary || {};
  const c = d.combat || {};
  const a = d.advanced || {};
  const capturedFinalAvg = capturedFinalAvgFromSummary(s);
  renderKV('trainingDetail', [
    ['Score Win Rate', pct(Number(s.win_score_rate||s.win_rate||0))],
    ['True Win Rate', pct(Number(s.true_win_rate||0))],
    ['Draw Rate', pct(Number(s.draw_rate||0))],
    ['Loss Rate', pct(Number(s.loss_rate||0))],
    ['Avg VP', Number(s.avg_vp||0).toFixed(3)],
    ['VP Captured Final Avg', asVpCount(capturedFinalAvg)],
    ['Avg Steps', Number(s.avg_steps||0).toFixed(1)],
    ['Damage Ratio', Number(c.damage_ratio||0).toFixed(3)],
    ['Trade Mean', Number(c.trade_mean||0).toFixed(3)],
    ['Good Trade Rate', pct(Number(a.good_trade_rate||0))],
    ['Zero Damage Rate', pct(Number(a.zero_dmg_rate||0))]
  ]);
}

function renderMission(){
  const d = firstDetail();
  if (!d){ renderKV('missionDetail', [['No data','-']]); return; }
  const m = d.mission || {};
  renderKV('missionDetail', [
    ['VP Entry Conversion', pct(Number(m.vp_entry_conversion_rate||0))],
    ['VP Captured (run)', asVpCount(Number(m.vp_entries_taken||0))],
    ['Capture Conv After Contact', pct(Number(m.capture_conversion_after_contact||0))],
    ['Capture Attempt Success', pct(Number(m.capture_attempt_success_rate||0))],
    ['VP Contact Rate', pct(Number(m.vp_contact_rate||0))],
    ['VP Missed Rate', pct(Number(m.vp_entry_missed_rate||0))],
    ['Plan Progress Rate', pct(Number(m.plan_progress_rate||0))],
    ['Capture Attempted', String(m.capture_attempted ?? '-')],
    ['Capture Committed', String(m.capture_committed ?? '-')],
    ['Capture Cancelled by Finalizer', String(m.capture_cancelled_by_finalizer ?? '-')],
    ['Capture Readiness', String(m.capture_readiness ?? '-')]
  ]);
}

function renderVPs(){
  const d = firstDetail();
  const kvRoot = document.getElementById('vpDetail');
  const tablesRoot = document.getElementById('vpTables');
  kvRoot.innerHTML = '';
  tablesRoot.innerHTML = '';
  if (!d){
    renderKV('vpDetail', [['No data','-']]);
    return;
  }
  const m = d.mission || {};
  const s = d.summary || {};
  const capturedFinalAvg = capturedFinalAvgFromSummary(s);

  renderKV('vpDetail', [
    ['VP Entry Opportunities', String(m.vp_entry_opportunities ?? '-')],
    ['VP Entries Taken', String(m.vp_entries_taken ?? '-')],
    ['VP Entry Conversion', pct(Number(m.vp_entry_conversion_rate||0))],
    ['VP Missed Rate', pct(Number(m.vp_entry_missed_rate||0))],
    ['VP Control Turns Share', pct(Number(m.vp_control_turns_share||0))],
    ['VP Control AUC', Number(m.vp_control_auc||0).toFixed(3)],
    ['VP Net Progress', Number(m.vp_net_progress||0).toFixed(3)],
    ['VP Captured Final Avg', asVpCount(capturedFinalAvg)],
    ['First VP Entry Turn p50', String(m.first_vp_entry_turn_p50 ?? '-')],
    ['First VP Entry Turn p90', String(m.first_vp_entry_turn_p90 ?? '-')],
    ['VP Control After Entry p50', String(m.vp_control_after_entry_turns_p50 ?? '-')],
    ['VP Control After Entry p90', String(m.vp_control_after_entry_turns_p90 ?? '-')],
  ]);

  const finalCounts = s.captured_final_counts || {};
  const finalRows = Object.entries(finalCounts)
    .sort((a,b)=>Number(a[0])-Number(b[0]))
    .map(([k,v])=>`<tr><td>${k}</td><td>${Number(v||0)}</td></tr>`)
    .join('');
  const panelFinal = document.createElement('div');
  panelFinal.className = 'panel';
  panelFinal.innerHTML = `<h4 style="margin-top:0">Captured Objectives (Final)</h4>
    <table><thead><tr><th>Captured VP Bucket</th><th>Episodes</th></tr></thead>
    <tbody>${finalRows || '<tr><td colspan="2" class="sub">No data</td></tr>'}</tbody></table>`;
  tablesRoot.appendChild(panelFinal);

  const attempts = m.per_unit_vp_entry_attempts || {};
  const success = m.per_unit_vp_entry_success || {};
  const unitRows = Object.keys(attempts)
    .map((uid)=>({
      uid,
      att: Number(attempts[uid]||0),
      ok: Number(success[uid]||0)
    }))
    .sort((a,b)=>b.att-a.att)
    .map((u)=>`<tr><td>${u.uid}</td><td>${u.ok}</td><td>${u.att}</td><td>${u.att>0 ? pct(u.ok/u.att) : '0.0%'}</td></tr>`)
    .join('');
  const panelUnits = document.createElement('div');
  panelUnits.className = 'panel';
  panelUnits.style.marginTop = '10px';
  panelUnits.innerHTML = `<h4 style="margin-top:0">Per-Unit VP Entry Success</h4>
    <table><thead><tr><th>Unit</th><th>Success</th><th>Attempts</th><th>Rate</th></tr></thead>
    <tbody>${unitRows || '<tr><td colspan="4" class="sub">No unit VP data</td></tr>'}</tbody></table>`;
  tablesRoot.appendChild(panelUnits);
}

function renderCombats(){
  const d = firstDetail();
  const kvRoot = document.getElementById('combatsDetail');
  const tablesRoot = document.getElementById('combatsTables');
  kvRoot.innerHTML = '';
  tablesRoot.innerHTML = '';
  if (!d){
    renderKV('combatsDetail', [['No data','-']]);
    return;
  }
  const ae = d.action_execution || {};
  const us = ae.RL || {};
  const other = ae.ENEMY || {};

  const NON_COMBAT = new Set(['MOVE', 'WAIT']);
  const allTypes = Array.from(new Set([...Object.keys(us), ...Object.keys(other)]))
    .filter((t)=>!NON_COMBAT.has(String(t).toUpperCase()))
    .sort();
  const sumCounts = (obj)=>Object.entries(obj||{}).reduce((a,[k,v])=>{
    if (NON_COMBAT.has(String(k).toUpperCase())) return a;
    return a + Number((v||{}).count||0);
  },0);
  const sumDamage = (obj)=>Object.entries(obj||{}).reduce((a,[k,v])=>{
    if (NON_COMBAT.has(String(k).toUpperCase())) return a;
    return a + Number((v||{}).count||0)*Number((v||{}).damage_per_action||0);
  },0);
  const usCount = sumCounts(us);
  const otherCount = sumCounts(other);
  const usDamage = sumDamage(us);
  const otherDamage = sumDamage(other);
  const meleeUS = Number((us.ASSAULT_MELEE||{}).count||0);
  const meleeOther = Number((other.ASSAULT_MELEE||{}).count||0);

  renderKV('combatsDetail', [
    ['Combat actions US', String(usCount)],
    ['Combat actions OTHER', String(otherCount)],
    ['Estimated combat damage US', Number(usDamage||0).toFixed(2)],
    ['Estimated combat damage OTHER', Number(otherDamage||0).toFixed(2)],
    ['Melee assaults US', String(meleeUS)],
    ['Melee assaults OTHER', String(meleeOther)],
    ['Melee share US', usCount>0 ? pct(meleeUS/usCount) : '0.0%'],
    ['Melee share OTHER', otherCount>0 ? pct(meleeOther/otherCount) : '0.0%'],
  ]);

  const rows = allTypes.map((t)=>{
    const u = us[t] || {};
    const o = other[t] || {};
    const uc = Number(u.count||0), oc = Number(o.count||0);
    const ud = Number(u.damage_per_action||0), od = Number(o.damage_per_action||0);
    const ut = uc*ud, ot = oc*od;
    return `<tr>
      <td>${t}</td>
      <td>${uc}</td><td>${ud.toFixed(3)}</td><td>${ut.toFixed(2)}</td>
      <td>${oc}</td><td>${od.toFixed(3)}</td><td>${ot.toFixed(2)}</td>
    </tr>`;
  }).join('');

  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.innerHTML = `<h4 style="margin-top:0">Combat Breakdown by Type</h4>
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th>US count</th><th>US dmg/action</th><th>US dmg total(est)</th>
          <th>OTHER count</th><th>OTHER dmg/action</th><th>OTHER dmg total(est)</th>
        </tr>
      </thead>
      <tbody>${rows || '<tr><td colspan="7" class="sub">No combat data</td></tr>'}</tbody>
    </table>`;
  tablesRoot.appendChild(panel);
}

function renderOverrides(){
  const d = firstDetail();
  const tb = document.querySelector('#overrideTable tbody');
  tb.innerHTML = '';
  if (!d){ return; }
  const m = d.mission || {};
  const counts = m.finalizer_override_reason_counts || {};
  const rates = m.finalizer_override_reason_rates || {};
  const entries = Object.entries(counts).sort((a,b)=>Number(b[1])-Number(a[1]));
  if (!entries.length){
    tb.innerHTML = '<tr><td colspan="3" class="sub">No override reasons found</td></tr>';
    return;
  }
  for (const [k,v] of entries){
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${k}</td><td>${v}</td><td>${pct(Number(rates[k]||0))}</td>`;
    tb.appendChild(tr);
  }
}

function renderActions(){
  const d = firstDetail();
  const root = document.getElementById('actionsDetail');
  root.innerHTML = '';
  if (!d){ root.textContent='No data'; return; }
  const ae = d.action_execution || {};
  const sections = [['US', ae.RL||{}], ['OTHER', ae.ENEMY||{}]];
  for (const [label,data] of sections){
    const panel = document.createElement('div');
    panel.className='panel';
    const rows = Object.entries(data).map(([k,v])=>`<tr><td>${k}</td><td>${v.count??0}</td><td>${Number(v.damage_per_action||0).toFixed(3)}</td></tr>`).join('');
    panel.innerHTML = `<h4 style="margin-top:0">${label}</h4><table><thead><tr><th>Type</th><th>Count</th><th>Damage/Action</th></tr></thead><tbody>${rows||'<tr><td colspan="3" class="sub">No data</td></tr>'}</tbody></table>`;
    root.appendChild(panel);
  }
}

function renderUnits(){
  const d = firstDetail();
  const root = document.getElementById('unitsDetail');
  root.innerHTML = '';
  if (!d){ root.textContent='No data'; return; }

  const units = d.units || {};
  const bySide = units.by_side || {};
  const byUnit = units.by_unit || {};

  const sections = [
    ['US', bySide.RL || {}, byUnit.RL || []],
    ['OTHER', bySide.ENEMY || {}, byUnit.ENEMY || []],
  ];

  for (const [label, summary, rows] of sections){
    const panel = document.createElement('div');
    panel.className='panel';
    const summaryHtml = `
      <div class="sub" style="margin-bottom:8px">
        units=${Number(summary.unit_count||0)} |
        attacks=${Number(summary.total_attacks||0)} |
        damage=${Number(summary.total_damage||0).toFixed(1)} |
        kills=${Number(summary.total_kills||0)} |
        dmg/atk=${Number(summary.damage_per_attack||0).toFixed(3)}
      </div>`;
    const bodyRows = (rows || []).map((u)=>`
      <tr>
        <td>${u.unit_id || '-'}</td>
        <td>${u.category || '-'}</td>
        <td>${u.classification || '-'}</td>
        <td>${Number(u.damage||0).toFixed(1)}</td>
        <td>${Number(u.attacks||0)}</td>
        <td>${Number(u.kills||0)}</td>
        <td>${Number(u.damage_per_attack||0).toFixed(3)}</td>
      </tr>`).join('');
    panel.innerHTML = `
      <h4 style="margin-top:0">${label}</h4>
      ${summaryHtml}
      <table>
        <thead><tr><th>Unit</th><th>Category</th><th>Class</th><th>Dmg</th><th>Atk</th><th>Kills</th><th>Dmg/Atk</th></tr></thead>
        <tbody>${bodyRows || '<tr><td colspan="7" class="sub">No unit data in this report</td></tr>'}</tbody>
      </table>`;
    root.appendChild(panel);
  }
}

function renderStrategies(){
  const d = firstDetail();
  const root = document.getElementById('strategyDetail');
  root.innerHTML = '';
  if (!d){ root.textContent='No data'; return; }
  const s = d.strategy || {};
  const m = d.mission || {};
  const l2 = s.l2_policy_performance || {};
  const l3 = s.l3_policy_performance || {};
  const map = s.strategy_to_option_map || {};
  const vpConv = Number(m.vp_entry_conversion_rate || 0);
  const capConv = Number(m.capture_conversion_after_contact || 0);

  let capStatus = 'bad';
  if (vpConv >= 0.30 && capConv >= 0.10) capStatus = 'ok';
  else if (vpConv >= 0.20 && capConv >= 0.05) capStatus = 'warn';

  const statusPanel = document.createElement('div');
  statusPanel.className = 'panel';
  statusPanel.innerHTML = `
    <h4 style="margin-top:0">Strategy Health (Traffic Lights)</h4>
    <table>
      <thead><tr><th>Signal</th><th>Value</th><th>Status</th><th>Rule</th></tr></thead>
      <tbody>
        <tr>
          <td>CAPTURE effectiveness</td>
          <td>vp_entry=${pct(vpConv)} | capture_after_contact=${pct(capConv)}</td>
          <td class="${capStatus}">${capStatus.toUpperCase()}</td>
          <td>green: vp>=30% and cap>=10%; yellow: vp>=20% and cap>=5%</td>
        </tr>
      </tbody>
    </table>`;
  root.appendChild(statusPanel);

  const panelL2 = document.createElement('div');
  panelL2.className = 'panel';
  panelL2.style.marginTop = '10px';
  panelL2.innerHTML = `<h4 style="margin-top:0">L2 Policy Performance</h4>
    <table><thead><tr><th>Option</th><th>Usage</th><th>Dmg/Atk</th><th>Kills/Atk</th></tr></thead><tbody>${
      Object.entries(l2).sort((a,b)=>Number((b[1]||{}).usage||0)-Number((a[1]||{}).usage||0)).map(([k,v])=>`
      <tr><td>${k}</td><td>${Number(v.usage||0)}</td><td>${Number(v.damage_per_attack||0).toFixed(3)}</td><td>${Number(v.kills_per_attack||0).toFixed(3)}</td></tr>`).join('') || '<tr><td colspan="4" class="sub">No data</td></tr>'
    }</tbody></table>`;
  root.appendChild(panelL2);

  const panelL3 = document.createElement('div');
  panelL3.className = 'panel';
  panelL3.style.marginTop = '10px';
  panelL3.innerHTML = `<h4 style="margin-top:0">L3 Strategy Performance</h4>
    <table><thead><tr><th>Strategy</th><th>Usage</th><th>Dmg/Atk</th><th>Kills/Atk</th><th>Status</th></tr></thead><tbody>${
      Object.entries(l3).sort((a,b)=>Number((b[1]||{}).usage||0)-Number((a[1]||{}).usage||0)).map(([k,v])=>{
        const dpa = Number(v.damage_per_attack||0);
        const kpa = Number(v.kills_per_attack||0);
        let rowStatus = 'bad';
        if (dpa >= 0.25 && kpa >= 0.08) rowStatus = 'ok';
        else if (dpa >= 0.15 && kpa >= 0.04) rowStatus = 'warn';
        return `<tr><td>${k}</td><td>${Number(v.usage||0)}</td><td>${dpa.toFixed(3)}</td><td>${kpa.toFixed(3)}</td><td class="${rowStatus}">${rowStatus.toUpperCase()}</td></tr>`;
      }).join('') || '<tr><td colspan="5" class="sub">No data</td></tr>'
    }</tbody></table>`;
  root.appendChild(panelL3);

  const panelMap = document.createElement('div');
  panelMap.className = 'panel';
  panelMap.style.marginTop = '10px';
  panelMap.innerHTML = `<h4 style="margin-top:0">Strategy → Option Map</h4>
    <table><thead><tr><th>Strategy</th><th>Option</th><th>Count</th><th>Ratio</th></tr></thead><tbody>${
      Object.entries(map).flatMap(([strat, opts]) =>
        Object.entries(opts || {}).map(([opt, tuple]) => {
          const count = Array.isArray(tuple) ? Number(tuple[0]||0) : Number((tuple||{}).count||0);
          const ratio = Array.isArray(tuple) ? Number(tuple[1]||0) : Number((tuple||{}).ratio||0);
          return `<tr><td>${strat}</td><td>${opt}</td><td>${count}</td><td>${pct(ratio)}</td></tr>`;
        })
      ).join('') || '<tr><td colspan="4" class="sub">No data</td></tr>'
    }</tbody></table>`;
  root.appendChild(panelMap);
}

function renderDetailTabs(){
  renderTraining();
  renderMission();
  renderVPs();
  renderCombats();
  renderOverrides();
  renderActions();
  renderUnits();
  renderStrategies();
}

function polylinePoints(values, w, h, pad){
  if (!values.length) return '';
  const min = Math.min(...values), max = Math.max(...values);
  const den = (max-min) || 1e-9;
  return values.map((v,i)=>{
    const x = pad + (i*(w-2*pad))/Math.max(1,values.length-1);
    const y = h - pad - ((v-min)/den)*(h-2*pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function thresholdY(values, threshold, h, pad){
  if (!values.length) return null;
  const min = Math.min(...values), max = Math.max(...values);
  const den = (max-min) || 1e-9;
  const t = Number(threshold);
  const y = h - pad - ((t-min)/den)*(h-2*pad);
  return Math.max(pad, Math.min(h-pad, y));
}

function renderHistoryCharts(points){
  const root = document.getElementById('historyCharts');
  root.innerHTML = '';
  const metrics = [
    ['Loss Rate', 'loss_rate', false, 0.80, 'max'],
    ['VP Entry Conversion', 'vp_entry_conversion_rate', true, 0.30, 'min'],
    ['Capture Conversion', 'capture_conversion_after_contact', true, 0.0000001, 'min'],
    ['VP Captured (run)', 'vp_entries_taken', true, 2.0, 'min'],
    ['VP Captured Final', 'captured_final_avg', true, 2.0, 'min'],
    ['SB3 Kept', 'sb3_kept', true, 0.45, 'min'],
    ['Finalizer Override', 'finalizer_override', false, 0.55, 'max'],
  ];
  const width=900, height=72, pad=8;
  for (const [title,key,_goodHigh,thr,rule] of metrics){
    const vals = points.map(p=>Number(p[key]||0));
    const last = vals.length ? vals[vals.length-1] : 0;
    const poly = polylinePoints(vals,width,height,pad);
    const ty = thresholdY(vals, thr, height, pad);
    const pass = rule === 'min' ? last >= thr : last <= thr;
    const thrColor = pass ? '#2ecc71' : '#e74c3c';
    const thrLabel = rule === 'min' ? `>= ${thr}` : `<= ${thr}`;
    const panel = document.createElement('div');
    panel.className='panel';
    const isCountMetric = key === 'vp_entries_taken' || key === 'captured_final_avg';
    panel.innerHTML = `<div class="k">${title}</div>
      <div class="v ${pass ? 'ok' : 'bad'}">${isCountMetric ? asVpCount(last) : pct(last)}</div>
      <div class="sub">threshold ${thrLabel}</div>
      <svg class="sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        ${ty===null ? '' : `<line x1="${pad}" y1="${ty}" x2="${width-pad}" y2="${ty}" stroke="${thrColor}" stroke-width="1.5" stroke-dasharray="5 4" />`}
        <polyline fill="none" stroke="#4aa3ff" stroke-width="2" points="${poly}" />
      </svg>`;
    root.appendChild(panel);
  }
}

function renderHistoryTable(points){
  const tb = document.querySelector('#historyTable tbody');
  tb.innerHTML = '';
  const rev = [...points].reverse();
  for (const p of rev){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${p.report}</td>
      <td>${p.timestamp||'-'}</td>
      <td>${pct(Number(p.loss_rate||0))}</td>
      <td>${pct(Number(p.vp_entry_conversion_rate||0))}</td>
      <td>${pct(Number(p.capture_conversion_after_contact||0))}</td>
      <td>${asVpCount(Number(p.vp_entries_taken||0))}</td>
      <td>${asVpCount(Number(p.captured_final_avg||0))}</td>
      <td>${pct(Number(p.sb3_kept||0))}</td>
      <td>${pct(Number(p.finalizer_override||0))}</td>`;
    tb.appendChild(tr);
  }
}

async function loadHistory(){
  const limit = document.getElementById('historyLimit').value || '40';
  const side = document.getElementById('historySide').value || '';
  const scenario = document.getElementById('historyScenario').value || '';
  const qs = new URLSearchParams({limit, side, scenario});
  const data = await getJson('/api/history?'+qs.toString());
  historyPoints = data.points || [];
  renderHistoryCharts(historyPoints);
  renderHistoryTable(historyPoints);
}

function exportHistoryCsv(){
  if (!historyPoints.length) return;
  const headers = [
    'report','timestamp','seed','score_win_rate','loss_rate',
    'vp_entry_conversion_rate','capture_conversion_after_contact',
    'vp_entries_taken','captured_final_avg','sb3_kept','finalizer_override'
  ];
  const lines = [headers.join(',')];
  for (const p of historyPoints){
    const row = headers.map(h => {
      const v = (p[h] ?? '');
      const s = String(v).replaceAll('"','""');
      return `"${s}"`;
    }).join(',');
    lines.push(row);
  }
  const blob = new Blob([lines.join('\\n')], {type:'text/csv;charset=utf-8;'});
  const a = document.createElement('a');
  const now = new Date().toISOString().replaceAll(':','-');
  a.href = URL.createObjectURL(blob);
  a.download = `sb3_history_${now}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function setupTabs(){
  const buttons = [...document.querySelectorAll('.tab-btn')];
  for (const b of buttons){
    b.addEventListener('click', ()=>{
      const tab = b.dataset.tab;
      for (const x of buttons) x.classList.remove('active');
      b.classList.add('active');
      for (const c of document.querySelectorAll('.tab-content')) c.classList.remove('active');
      document.getElementById(`tab-${tab}`).classList.add('active');
    });
  }
}

async function loadSelected() {
  const name = document.getElementById('reportSelect').value;
  if (!name) return;
  const data = await getJson('/api/report?name='+encodeURIComponent(name));
  document.getElementById('meta').textContent = `timestamp=${data.meta?.timestamp||'-'} seed=${data.meta?.seed??'-'} episodes=${data.meta?.episodes??'-'}`;
  const rows = data.rows || [];
  currentDetails = data.details || [];
  renderCards(rows);
  renderRows(rows);
  renderDetailTabs();
}

document.getElementById('reloadBtn').addEventListener('click', async ()=>{ await loadReports(); await loadSelected(); });
document.getElementById('reportSelect').addEventListener('change', loadSelected);
document.getElementById('historyReloadBtn').addEventListener('click', loadHistory);
document.getElementById('historyExportBtn').addEventListener('click', exportHistoryCsv);
setupTabs();

(async ()=>{ await loadReports(); await loadSelected(); await loadHistory(); })();
</script>
</body>
</html>
"""


def build_handler(reports_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, payload: dict, status: int = 200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, body: str):
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._html(_page_html())
            if parsed.path == "/api/reports":
                files = sorted(
                    reports_dir.glob("metrics_sb3_report_*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                return self._json(
                    {
                        "reports": [p.name for p in files],
                        "latest": files[0].name if files else None,
                    }
                )
            if parsed.path == "/api/report":
                qs = parse_qs(parsed.query)
                name = (qs.get("name") or [""])[0]
                if not name:
                    return self._json({"error": "missing 'name'"}, status=400)
                path = reports_dir / name
                if not path.exists() or path.suffix.lower() != ".json":
                    return self._json({"error": "report not found"}, status=404)
                data = _read_json(path)
                rows = _build_rows(data)
                details = _build_details(data)
                return self._json(
                    {
                        "name": path.name,
                        "meta": data.get("meta", {}),
                        "rows": rows,
                        "details": details,
                    }
                )
            if parsed.path == "/api/history":
                qs = parse_qs(parsed.query)
                limit_raw = (qs.get("limit") or ["40"])[0]
                side = (qs.get("side") or [""])[0].strip()
                scenario = (qs.get("scenario") or [""])[0].strip()
                try:
                    limit = max(1, min(300, int(limit_raw)))
                except Exception:
                    limit = 40
                points = _build_history_points(
                    reports_dir=reports_dir,
                    limit=limit,
                    side_filter=side,
                    scenario_filter=scenario,
                )
                return self._json({"points": points})
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args):
            # Keep server quiet in terminal.
            return

    return Handler


def main():
    repo_root = Path(__file__).resolve().parents[1]
    default_reports_dir = repo_root / "assault_sim" / "session" / "reports" / "sb3_eval"
    parser = argparse.ArgumentParser(description="Run local SB3 eval viewer.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reports-dir", default=str(default_reports_dir))
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    latest = _latest_report_path(reports_dir)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(reports_dir))
    print(f"SB3 Eval Viewer: http://{args.host}:{args.port}")
    print(f"Reports dir: {reports_dir}")
    print(f"Latest report: {latest.name if latest else '(none yet)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

