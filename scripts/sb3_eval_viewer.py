from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


class ServiceController:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self._ecosystem_path = self.repo_root / "ecosystem.config.cjs"
        self._specs: dict[str, dict] = {
            "backend_api": {
                "name": "Backend API",
                "description": "FastAPI game backend",
                "pm2_name": "assault-backend",
                "health_url": "http://127.0.0.1:8001/health",
            },
            "frontend_ui": {
                "name": "Frontend UI",
                "description": "React tactical UI (dev server)",
                "pm2_name": "assault-frontend",
                "health_url": "http://127.0.0.1:5173/",
            },
            "sb3_eval_viewer": {
                "name": "SB3 Eval Viewer",
                "description": "Report viewer and control panel",
                "pm2_name": "assault-sb3-viewer",
                "health_url": "http://127.0.0.1:8765/",
            },
            "orchestrator_loop": {
                "name": "Orchestrator Loop",
                "description": "Prefect-based queue loop",
                "pm2_name": "assault-orchestrator-loop",
                "health_url": "http://127.0.0.1:4200/",
            },
            "orchestrator_prefect_server": {
                "name": "Orchestrator Prefect Server",
                "description": "Prefect API/UI server",
                "pm2_name": "assault-orchestrator-prefect-server",
                "health_url": "http://127.0.0.1:4200/",
            },
            "orchestrator_mlflow": {
                "name": "Orchestrator MLflow",
                "description": "MLflow tracking UI",
                "pm2_name": "assault-orchestrator-mlflow",
                "health_url": "http://127.0.0.1:5001/",
            },
        }

    def _pm2_cmd(self) -> str:
        return "pm2.cmd" if os.name == "nt" else "pm2"

    def _run_pm2(self, *args: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self._pm2_cmd(), *args],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            ok = result.returncode == 0
            out = (result.stdout or "") + (result.stderr or "")
            out = re.sub(r"\x1b\[[0-9;]*m", "", out)
            return ok, out.strip()
        except FileNotFoundError:
            return False, "pm2 not found in PATH"
        except Exception as e:
            return False, str(e)

    def _start_from_ecosystem(self, pm2_name: str) -> tuple[bool, str]:
        if not self._ecosystem_path.exists():
            return False, f"ecosystem file not found: {self._ecosystem_path}"
        return self._run_pm2("start", str(self._ecosystem_path), "--only", pm2_name)

    def _pm2_jlist(self) -> tuple[bool, list[dict], str]:
        ok, out = self._run_pm2("jlist")
        if not ok:
            return False, [], out
        try:
            payload = json.loads(out or "[]")
            if isinstance(payload, list):
                return True, payload, ""
            return False, [], "invalid pm2 jlist payload"
        except Exception as e:
            return False, [], f"failed to parse pm2 jlist: {e}"

    def _health_ok(self, url: str) -> bool:
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=1.5) as resp:
                return 200 <= int(resp.status) < 500
        except Exception:
            return False

    def _tail_file(self, path: str, max_lines: int = 300) -> str:
        file_path = Path(str(path or "").strip())
        if not file_path.exists():
            return "(log file not found)"
        if not file_path.is_file():
            return "(log path is not a file)"
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            clipped = lines[-max(1, int(max_lines)) :]
            return "".join(clipped).strip() or "(log file is empty)"
        except Exception as e:
            return f"(failed reading log: {e})"

    def list_status(self) -> list[dict]:
        out: list[dict] = []
        now = time.time()
        ok_pm2, jlist, pm2_error = self._pm2_jlist()
        pm2_by_name: dict[str, dict] = {}
        if ok_pm2:
            for app in jlist:
                name = str(app.get("name", "")).strip()
                if name:
                    pm2_by_name[name] = app
        for key, spec in self._specs.items():
            pm2_name = str(spec.get("pm2_name", "")).strip()
            app = pm2_by_name.get(pm2_name, {})
            pm2_env = app.get("pm2_env", {}) if isinstance(app, dict) else {}
            pm2_status = str(pm2_env.get("status", "")).strip().lower()
            alive = pm2_status == "online"
            health = self._health_ok(spec.get("health_url", ""))
            pm_uptime_ms = int(pm2_env.get("pm_uptime", 0) or 0) if isinstance(pm2_env, dict) else 0
            uptime_s = int(max(0.0, (now * 1000 - pm_uptime_ms) / 1000.0)) if pm_uptime_ms > 0 else 0
            pid = app.get("pid") if isinstance(app, dict) else None
            out.append(
                {
                    "id": key,
                    "name": spec.get("name"),
                    "description": spec.get("description"),
                    "pm2_name": pm2_name,
                    "health_url": spec.get("health_url"),
                    "managed_running": alive,
                    "reachable": health,
                    "pid": int(pid) if isinstance(pid, int) and pid > 0 else None,
                    "uptime_s": uptime_s,
                    "last_exit_code": pm2_env.get("exit_code"),
                    "status": ("running" if alive else ("reachable" if health else "stopped")),
                    "pm2_available": ok_pm2,
                    "pm2_error": (pm2_error if not ok_pm2 else ""),
                }
            )
        return out

    def read_service_logs(self, key: str, max_lines: int = 300) -> dict:
        if key not in self._specs:
            return {"ok": False, "error": f"unknown service: {key}"}
        pm2_name = str(self._specs[key].get("pm2_name", "")).strip()
        ok_pm2, jlist, pm2_error = self._pm2_jlist()
        if not ok_pm2:
            return {"ok": False, "error": pm2_error or "pm2 unavailable"}
        app = next((a for a in jlist if str(a.get("name", "")).strip() == pm2_name), None)
        if not isinstance(app, dict):
            return {"ok": False, "error": f"pm2 app not found: {pm2_name}"}
        pm2_env = app.get("pm2_env", {}) if isinstance(app.get("pm2_env", {}), dict) else {}
        out_path = str(pm2_env.get("pm_out_log_path", "") or "").strip()
        err_path = str(pm2_env.get("pm_err_log_path", "") or "").strip()
        return {
            "ok": True,
            "service_id": key,
            "service_name": self._specs[key].get("name"),
            "pm2_name": pm2_name,
            "out_path": out_path,
            "err_path": err_path,
            "out_tail": self._tail_file(out_path, max_lines=max_lines) if out_path else "(stdout log path unavailable)",
            "err_tail": self._tail_file(err_path, max_lines=max_lines) if err_path else "(stderr log path unavailable)",
        }

    def start(self, key: str) -> dict:
        if key not in self._specs:
            return {"ok": False, "error": f"unknown service: {key}"}
        spec = self._specs[key]
        pm2_name = str(spec.get("pm2_name", "")).strip()
        if not pm2_name:
            return {"ok": False, "error": f"service {key} has no pm2_name"}
        # Use delete+start to ensure the process definition is refreshed.
        self._run_pm2("delete", pm2_name)
        ok, out = self._start_from_ecosystem(pm2_name)
        if ok:
            return {"ok": True, "message": f"started {pm2_name}"}
        return {"ok": False, "error": out}

    def stop(self, key: str) -> dict:
        if key not in self._specs:
            return {"ok": False, "error": f"unknown service: {key}"}
        pm2_name = str(self._specs[key].get("pm2_name", "")).strip()
        if not pm2_name:
            return {"ok": False, "error": f"service {key} has no pm2_name"}
        ok, out = self._run_pm2("stop", pm2_name)
        if ok:
            return {"ok": True, "message": f"stopped {pm2_name}"}
        return {"ok": False, "error": out}

    def restart(self, key: str) -> dict:
        if key not in self._specs:
            return {"ok": False, "error": f"unknown service: {key}"}
        pm2_name = str(self._specs[key].get("pm2_name", "")).strip()
        if not pm2_name:
            return {"ok": False, "error": f"service {key} has no pm2_name"}
        # Robust restart on Windows: remove stale entry then start from ecosystem.
        self._run_pm2("delete", pm2_name)
        ok2, out2 = self._start_from_ecosystem(pm2_name)
        if ok2:
            return {"ok": True, "message": f"restarted {pm2_name}"}
        return {"ok": False, "error": out2}


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
                    "reaction_fire_count": _safe_float(
                        mission.get("reaction_fire_count", 0.0)
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
        reports_dir.rglob("metrics_sb3_report_*.json"),
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
                "reaction_fire_count": sum(
                    _safe_float(r.get("reaction_fire_count", 0.0)) for r in rows
                )
                / n,
                "vp_entries_taken": sum(
                    _safe_float(r.get("vp_entries_taken", 0.0)) for r in rows
                )
                / n,
                "reaction_fire_count": sum(
                    _safe_float(r.get("reaction_fire_count", 0.0)) for r in rows
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
    files = sorted(reports_dir.rglob("metrics_sb3_report_*.json"), key=lambda p: p.stat().st_mtime)
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
    a { color:#8ec5ff; text-decoration:none; }
    a:hover { text-decoration:underline; color:#b7dbff; }
    .reason { font-family:Consolas, monospace; font-size:12px; display:block; margin:2px 0; }
    button, select { background:#1f2532; color:var(--txt); border:1px solid var(--border); border-radius:8px; padding:8px 10px; transition: background-color .16s ease, border-color .16s ease, transform .08s ease, box-shadow .16s ease, opacity .16s ease; }
    button:hover { background:#273146; border-color:#4aa3ff; box-shadow:0 0 0 1px rgba(74,163,255,.45) inset; transform:translateY(-1px); cursor:pointer; }
    button:active { transform:translateY(0px) scale(.98); background:#1d2536; }
    button:focus-visible { outline:none; box-shadow:0 0 0 2px rgba(74,163,255,.55); border-color:#4aa3ff; }
    button:disabled { opacity:.55; cursor:not-allowed; transform:none; box-shadow:none; }
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

  <div class="panel" style="margin-bottom:12px">
    <h3 style="margin:0 0 8px">Service URLs</h3>
    <div class="sub" style="display:flex;gap:12px;flex-wrap:wrap">
      <a href="http://127.0.0.1:8765" target="_blank" rel="noopener">SB3 Viewer (8765)</a>
      <a href="http://127.0.0.1:5173" target="_blank" rel="noopener">Frontend UI (5173)</a>
      <a href="http://127.0.0.1:8001/docs" target="_blank" rel="noopener">Backend API Docs (8001)</a>
      <a href="http://127.0.0.1:4200" target="_blank" rel="noopener">Prefect UI (4200)</a>
      <a href="http://127.0.0.1:5001" target="_blank" rel="noopener">MLflow UI (5001)</a>
    </div>
  </div>

  <div class="cards" id="cards"></div>

  <div class="tabs">
    <button class="tab-btn active" data-tab="overview">Overview</button>
    <button class="tab-btn" data-tab="howto">How-To</button>
    <button class="tab-btn" data-tab="training">Training</button>
    <button class="tab-btn" data-tab="mission">Mission</button>
    <button class="tab-btn" data-tab="vps">VPs</button>
    <button class="tab-btn" data-tab="combats">Combats</button>
    <button class="tab-btn" data-tab="overrides">Overrides</button>
    <button class="tab-btn" data-tab="actions">Actions</button>
    <button class="tab-btn" data-tab="units">Units/Side</button>
    <button class="tab-btn" data-tab="strategy">Strategies</button>
    <button class="tab-btn" data-tab="rag">RAG Copilot</button>
    <button class="tab-btn" data-tab="history">History</button>
    <button class="tab-btn" data-tab="control">Control</button>
  </div>

  <div id="tab-overview" class="tab-content active panel">
    <h3 style="margin-top:0">By Side / Scenario</h3>
    <table id="rowsTable">
      <thead>
        <tr>
          <th>Side</th><th>Scenario</th><th>Score Win</th><th>Loss</th>
          <th>VP Entry Conv</th><th>Capture Conv After Contact</th>
          <th>Reaction Fire</th><th>VP Captured (run)</th><th>VP Captured Final</th>
          <th>SB3 Kept</th><th>Finalizer Override</th><th>Top Finalizer Reasons</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div id="tab-howto" class="tab-content panel">
    <h3 style="margin-top:0">How To Interpret This Run</h3>
    <div id="howtoSummary" class="panel" style="margin-bottom:10px"></div>
    <div id="howtoChecks"></div>
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
    <div id="overrideSummary" class="sub" style="margin-bottom:8px"></div>
    <h4 style="margin:8px 0 6px 0">Override Source Mix</h4>
    <table id="overrideSourceTable">
      <thead><tr><th>Source</th><th>Count</th><th>Rate</th></tr></thead>
      <tbody></tbody>
    </table>
    <h4 style="margin:8px 0 6px 0">Finalizer Overrides</h4>
    <table id="overrideTable">
      <thead><tr><th>Reason</th><th>Count</th><th>Rate</th></tr></thead>
      <tbody></tbody>
    </table>
    <h4 style="margin:12px 0 6px 0">Capture Override Reasons</h4>
    <table id="captureOverrideTable">
      <thead><tr><th>Reason</th><th>Count</th><th>Rate vs Capture Attempts</th></tr></thead>
      <tbody></tbody>
    </table>
    <h4 style="margin:12px 0 6px 0">Capture Move Block Profile</h4>
    <table id="captureBlockTable">
      <thead><tr><th>Profile</th><th>Count</th><th>Rate vs Capture Attempts</th></tr></thead>
      <tbody></tbody>
    </table>
    <h4 style="margin:12px 0 6px 0">Hard Gate Step-in Breakdown</h4>
    <table id="hardGateTable">
      <thead><tr><th>Hard Gate Detail</th><th>Count</th><th>Rate vs Hard Gate</th></tr></thead>
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

  <div id="tab-rag" class="tab-content panel">
    <h3 style="margin-top:0">RAG Copilot (Eval)</h3>
    <div id="ragDetail"></div>
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
          <th>Capture Conv</th><th>Reaction Fire</th><th>VP Captured (run)</th><th>VP Captured Final</th>
          <th>SB3 Kept</th><th>Finalizer Override</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div id="tab-control" class="tab-content panel">
    <h3 style="margin-top:0">Service Control</h3>
    <div class="top" style="margin-bottom:8px">
      <button id="controlRefreshBtn">Refresh Status</button>
      <span class="sub">Start/stop/restart local services from this viewer.</span>
    </div>
    <table id="controlTable">
      <thead>
        <tr>
          <th>Service</th><th>Status</th><th>PID</th><th>Uptime</th><th>Reachable</th><th>URL</th><th>Actions</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
    <div id="controlLogPanel" class="panel" style="margin-top:10px; display:none;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
        <strong id="controlLogTitle">Service Logs</strong>
        <button id="controlLogCloseBtn">Close</button>
      </div>
      <div class="sub" id="controlLogMeta" style="margin:6px 0 10px;"></div>
      <div style="display:grid;grid-template-columns:1fr;gap:10px;">
        <div>
          <div class="sub" style="margin-bottom:4px;">STDOUT</div>
          <pre id="controlLogStdout" style="margin:0;max-height:280px;overflow:auto;background:#10141d;border:1px solid var(--border);border-radius:8px;padding:8px;white-space:pre-wrap;"></pre>
        </div>
        <div>
          <div class="sub" style="margin-bottom:4px;">STDERR</div>
          <pre id="controlLogStderr" style="margin:0;max-height:280px;overflow:auto;background:#10141d;border:1px solid var(--border);border-radius:8px;padding:8px;white-space:pre-wrap;"></pre>
        </div>
      </div>
    </div>
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
let currentRows = [];
let controlRenderInFlight = false;

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
    reaction_fire_count:a.reaction_fire_count+r.reaction_fire_count,
    vp_entries_taken:a.vp_entries_taken+r.vp_entries_taken,
    captured_final_avg:a.captured_final_avg+r.captured_final_avg,
    sb3_kept:a.sb3_kept+r.sb3_kept,
    finalizer_override:a.finalizer_override+r.finalizer_override
  }), {score_win_rate:0,loss_rate:0,vp_entry_conversion_rate:0,capture_conversion_after_contact:0,reaction_fire_count:0,vp_entries_taken:0,captured_final_avg:0,sb3_kept:0,finalizer_override:0});
  for (const k in agg) agg[k]/=n;
  const cards = [
    ['Score Win Rate', agg.score_win_rate, true],
    ['Loss Rate', agg.loss_rate, false],
    ['VP Entry Conversion', agg.vp_entry_conversion_rate, true],
    ['Capture Conversion', agg.capture_conversion_after_contact, true],
    ['Reaction Fire (run)', agg.reaction_fire_count/3.0, true],
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
    const isCountCard = name.startsWith('VP Captured') || name.startsWith('Reaction Fire');
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
      <td>${asVpCount(r.reaction_fire_count)}</td>
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
  const lastFailureCounts = m.plan_last_failure_reason_counts || {};
  const topLastFailure = Object.entries(lastFailureCounts)
    .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))[0];
  const topLastFailureLabel = topLastFailure ? `${topLastFailure[0]} (${Number(topLastFailure[1]||0)})` : '-';
  renderKV('missionDetail', [
    ['VP Entry Conversion', pct(Number(m.vp_entry_conversion_rate||0))],
    ['VP Captured (run)', asVpCount(Number(m.vp_entries_taken||0))],
    ['Capture Conv After Contact', pct(Number(m.capture_conversion_after_contact||0))],
    ['Capture Attempt Success', pct(Number(m.capture_attempt_success_rate||0))],
    ['VP Contact Rate', pct(Number(m.vp_contact_rate||0))],
    ['VP Missed Rate', pct(Number(m.vp_entry_missed_rate||0))],
    ['Plan Progress Rate', pct(Number(m.plan_progress_rate||0))],
    ['Plan Stuck Steps (mean)', Number(m.plan_stuck_steps_mean||0).toFixed(2)],
    ['Plan Stuck Steps (p90)', Number(m.plan_stuck_steps_p90||0).toFixed(2)],
    ['Plan Steps Since Progress (mean)', Number(m.plan_steps_since_progress_mean||0).toFixed(2)],
    ['Plan Steps Since Progress (p90)', Number(m.plan_steps_since_progress_p90||0).toFixed(2)],
    ['Planned Target Set Rate', pct(Number(m.plan_planned_target_set_rate||0))],
    ['Planned Target Switch Count', String(m.plan_planned_target_switch_count ?? '-')],
    ['Team Turn Plan Progress (mean)', Number(m.plan_team_turn_progress_mean||0).toFixed(2)],
    ['Team Units Committed (mean)', Number(m.plan_team_units_committed_mean||0).toFixed(2)],
    ['Team Focus VP Set Rate', pct(Number(m.plan_team_focus_vp_set_rate||0))],
    ['Advanced Planner Enabled Rate', pct(Number(m.plan_advanced_enabled_rate||0))],
    ['Advanced Planner Horizon (mean)', Number(m.plan_advanced_horizon_mean||0).toFixed(2)],
    ['Top Plan Last Failure Reason', topLastFailureLabel],
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
  const capturedDeltaAvg = Number(s.captured_delta_avg || 0);
  const capturedDeltaGainRate = Number(s.captured_delta_gain_rate || 0);
  const capturedDeltaFlatRate = Number(s.captured_delta_flat_rate || 0);
  const capturedDeltaLossRate = Number(s.captured_delta_loss_rate || 0);

  renderKV('vpDetail', [
    ['VP Entry Opportunities', String(m.vp_entry_opportunities ?? '-')],
    ['VP Entries Taken', String(m.vp_entries_taken ?? '-')],
    ['VP Entry Conversion', pct(Number(m.vp_entry_conversion_rate||0))],
    ['VP Missed Rate', pct(Number(m.vp_entry_missed_rate||0))],
    ['VP Control Turns Share', pct(Number(m.vp_control_turns_share||0))],
    ['VP Control AUC', Number(m.vp_control_auc||0).toFixed(3)],
    ['VP Net Progress', Number(m.vp_net_progress||0).toFixed(3)],
    ['VP Captured Final Avg', asVpCount(capturedFinalAvg)],
    ['Captured Delta Avg', capturedDeltaAvg.toFixed(3)],
    ['Captured Delta Gain Rate', pct(capturedDeltaGainRate)],
    ['Captured Delta Flat Rate', pct(capturedDeltaFlatRate)],
    ['Captured Delta Loss Rate', pct(capturedDeltaLossRate)],
    ['First VP Entry Turn p50', String(m.first_vp_entry_turn_p50 ?? '-')],
    ['First VP Entry Turn p90', String(m.first_vp_entry_turn_p90 ?? '-')],
    ['VP Control After Entry p50', String(m.vp_control_after_entry_turns_p50 ?? '-')],
    ['VP Control After Entry p90', String(m.vp_control_after_entry_turns_p90 ?? '-')],
    ['Reaction Fire Count', String(m.reaction_fire_count ?? 0)],
    ['Reaction Fire Rate', pct(Number(m.reaction_fire_rate||0))],
    ['Reaction Window Count', String(m.reaction_window_count ?? 0)],
    ['Reaction Fire Skipped Count', String(m.reaction_fire_skipped_count ?? 0)],
  ]);

  const finalCounts = s.captured_final_counts || {};
  const deltaCounts = s.captured_delta_counts || {};
  const finalKeys = Object.keys(finalCounts || {});
  const deltaKeys = Object.keys(deltaCounts || {});
  const finalBuckets = finalKeys.sort((a,b)=>Number(a)-Number(b));
  const deltaBuckets = deltaKeys.sort((a,b)=>Number(a)-Number(b));
  const epsTotal = Number(s.episodes || 0);
  const finalRows = finalBuckets
    .map((k) => {
      const f = Number(finalCounts[k] || 0);
      const fp = epsTotal > 0 ? pct(f / epsTotal) : "0.0%";
      return `<tr><td>${k}</td><td>${f}</td><td>${fp}</td></tr>`;
    })
    .join('');
  const deltaRows = deltaBuckets
    .map((k) => {
      const d = Number(deltaCounts[k] || 0);
      const dp = epsTotal > 0 ? pct(d / epsTotal) : "0.0%";
      return `<tr><td>${k}</td><td>${d}</td><td>${dp}</td></tr>`;
    })
    .join('');

  const compareWrap = document.createElement('div');
  compareWrap.style.display = 'flex';
  compareWrap.style.gap = '10px';
  compareWrap.style.flexWrap = 'wrap';
  compareWrap.style.alignItems = 'flex-start';

  const panelFinal = document.createElement('div');
  panelFinal.className = 'panel';
  panelFinal.style.flex = '1 1 440px';
  panelFinal.innerHTML = `<h4 style="margin-top:0">Captured Objectives (Final)</h4>
    <table><thead><tr><th>Final Bucket</th><th>Episodes</th><th>Rate</th></tr></thead>
    <tbody>${finalRows || '<tr><td colspan="3" class="sub">No data</td></tr>'}</tbody></table>`;

  const panelDelta = document.createElement('div');
  panelDelta.className = 'panel';
  panelDelta.style.flex = '1 1 440px';
  panelDelta.innerHTML = `<h4 style="margin-top:0">Captured Objectives (Delta)</h4>
    <table><thead><tr><th>Delta Bucket</th><th>Episodes</th><th>Rate</th></tr></thead>
    <tbody>${deltaRows || '<tr><td colspan="3" class="sub">No data</td></tr>'}</tbody></table>`;

  compareWrap.appendChild(panelFinal);
  compareWrap.appendChild(panelDelta);
  tablesRoot.appendChild(compareWrap);

  const vpOpp = Number(m.vp_entry_opportunities || 0);
  const vpTaken = Number(m.vp_entries_taken || 0);
  const vpNotTaken = Math.max(0, vpOpp - vpTaken);
  const vpContact = Number(m.vp_contact_steps || 0);
  const captureAfterContact = Number(m.contact_to_capture_success || 0);
  const stage1 = vpOpp;
  const stage2 = vpTaken;
  const stage3 = captureAfterContact;
  const funnelMax = Math.max(1, stage1, stage2, stage3);
  const funnelWidthPct = (v) => Math.max(20, (Number(v || 0) / funnelMax) * 100);
  const blockReasons = m.vp_stepin_block_reason_counts || {};
  const overrideReasons = m.capture_override_reason_counts || {};
  const reasonRows = Object.entries(blockReasons)
    .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
    .map(([k,v]) => {
      const n = Number(v || 0);
      const rate = vpOpp > 0 ? pct(n / vpOpp) : '0.0%';
      return `<tr><td>${k}</td><td>${n}</td><td>${rate}</td></tr>`;
    })
    .join('');
  const overrideRows = Object.entries(overrideReasons)
    .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
    .map(([k,v]) => `<tr><td>${k}</td><td>${Number(v||0)}</td></tr>`)
    .join('');

  const panelReasons = document.createElement('div');
  panelReasons.className = 'panel';
  panelReasons.style.marginTop = '10px';
  panelReasons.innerHTML = `<h4 style="margin-top:0">VP Entry Breakdown (why not taken)</h4>
    <div class="sub" style="margin-bottom:8px">Funnel VP (opportunity -> taken -> captured after contact)</div>
    <div style="display:flex;flex-direction:column;align-items:center;gap:6px;margin-bottom:10px;">
      <div style="width:${funnelWidthPct(stage1).toFixed(1)}%;max-width:760px;min-width:240px;padding:8px 12px;background:rgba(122,197,255,0.22);border:1px solid rgba(122,197,255,0.55);clip-path:polygon(4% 0,96% 0,100% 100%,0 100%);text-align:center;">
        <b>Opportunities</b> - ${stage1}
      </div>
      <div style="width:${funnelWidthPct(stage2).toFixed(1)}%;max-width:700px;min-width:210px;padding:8px 12px;background:rgba(255,179,92,0.22);border:1px solid rgba(255,179,92,0.55);clip-path:polygon(6% 0,94% 0,98% 100%,2% 100%);text-align:center;">
        <b>Entries Taken</b> - ${stage2}
      </div>
      <div style="width:${funnelWidthPct(stage3).toFixed(1)}%;max-width:640px;min-width:190px;padding:8px 12px;background:rgba(123,240,168,0.20);border:1px solid rgba(123,240,168,0.50);clip-path:polygon(8% 0,92% 0,96% 100%,4% 100%);text-align:center;">
        <b>Captured After Contact</b> - ${stage3}
      </div>
    </div>
    <div class="sub" style="margin-bottom:8px">opportunities=${vpOpp} | taken=${vpTaken} | not_taken=${vpNotTaken}</div>
    <table><thead><tr><th>Block Reason</th><th>Count</th><th>Rate vs Opportunities</th></tr></thead>
    <tbody>${reasonRows || '<tr><td colspan="3" class="sub">No VP block reasons reported</td></tr>'}</tbody></table>
    <div class="sub" style="margin:10px 0 6px 0">Capture override reasons</div>
    <table><thead><tr><th>Override Reason</th><th>Count</th></tr></thead>
    <tbody>${overrideRows || '<tr><td colspan="2" class="sub">No capture override reasons reported</td></tr>'}</tbody></table>`;
  tablesRoot.appendChild(panelReasons);

  const finalContribution = m.per_unit_vp_final_contribution || {};
  const unitRows = Object.entries(finalContribution)
    .map(([uid, val]) => ({ uid, eps: Number(val || 0) }))
    .sort((a,b)=>b.eps-a.eps)
    .map((u)=>`<tr><td>${u.uid}</td><td>${u.eps}</td><td>${Number(s.episodes||0)>0 ? pct(u.eps/Number(s.episodes||1)) : '0.0%'}</td></tr>`)
    .join('');
  const panelUnits = document.createElement('div');
  panelUnits.className = 'panel';
  panelUnits.style.marginTop = '10px';
  panelUnits.innerHTML = `<h4 style="margin-top:0">Per-Unit Final VP Ownership Contribution</h4>
    <table><thead><tr><th>Unit</th><th>Episodes Contributing</th><th>Rate</th></tr></thead>
    <tbody>${unitRows || '<tr><td colspan="3" class="sub">No unit final VP contribution data</td></tr>'}</tbody></table>`;
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
  const m = d.mission || {};
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
    ['Reaction Fire Count', String(m.reaction_fire_count ?? 0)],
    ['Reaction Fire Rate', pct(Number(m.reaction_fire_rate||0))],
    ['Reaction Fire by Side', Object.entries(m.reaction_fire_by_side || {}).map(([k,v])=>`${k}:${v}`).join(' | ') || '-'],
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
  const captureTb = document.querySelector('#captureOverrideTable tbody');
  const blockTb = document.querySelector('#captureBlockTable tbody');
  const hardGateTb = document.querySelector('#hardGateTable tbody');
  const sourceTb = document.querySelector('#overrideSourceTable tbody');
  const summary = document.getElementById('overrideSummary');
  tb.innerHTML = '';
  if (captureTb) captureTb.innerHTML = '';
  if (blockTb) blockTb.innerHTML = '';
  if (hardGateTb) hardGateTb.innerHTML = '';
  if (sourceTb) sourceTb.innerHTML = '';
  if (summary) summary.textContent = '';
  if (!d){ return; }
  const m = d.mission || {};
  const sourceCounts = m.source_mix_counts || {};
  const sourceRates = m.source_mix_rates || {};
  const sourceEntries = Object.entries(sourceCounts).sort((a,b)=>Number(b[1])-Number(a[1]));
  if (sourceTb){
    if (!sourceEntries.length){
      sourceTb.innerHTML = '<tr><td colspan="3" class="sub">No source mix data</td></tr>';
    } else {
      for (const [k,v] of sourceEntries){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${k}</td><td>${Number(v||0)}</td><td>${pct(Number(sourceRates[k]||0))}</td>`;
        sourceTb.appendChild(tr);
      }
    }
  }
  const finalizerCounts = m.finalizer_override_reason_counts || {};
  const finalizerRates = m.finalizer_override_reason_rates || {};
  const finalizerEntries = Object.entries(finalizerCounts).sort((a,b)=>Number(b[1])-Number(a[1]));
  if (!finalizerEntries.length){
    tb.innerHTML = '<tr><td colspan="3" class="sub">No finalizer override reasons found</td></tr>';
  } else for (const [k,v] of finalizerEntries){
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${k}</td><td>${v}</td><td>${pct(Number(finalizerRates[k]||0))}</td>`;
    tb.appendChild(tr);
  }

  const captureAttempts = Number(m.capture_attempted || 0);
  const captureOverrideCounts = m.capture_override_reason_counts || {};
  const captureOverrideEntries = Object.entries(captureOverrideCounts).sort((a,b)=>Number(b[1])-Number(a[1]));
  if (captureTb){
    if (!captureOverrideEntries.length){
      captureTb.innerHTML = '<tr><td colspan="3" class="sub">No capture override reasons found</td></tr>';
    } else {
      for (const [k,v] of captureOverrideEntries){
        const n = Number(v || 0);
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${k}</td><td>${n}</td><td>${captureAttempts>0 ? pct(n/captureAttempts) : '0.0%'}</td>`;
        captureTb.appendChild(tr);
      }
    }
  }

  const captureMoveBlockProfile = m.capture_move_block_profile || {};
  const blockEntries = Object.entries(captureMoveBlockProfile).sort((a,b)=>Number(b[1])-Number(a[1]));
  if (blockTb){
    if (!blockEntries.length){
      blockTb.innerHTML = '<tr><td colspan="3" class="sub">No capture move block profile data</td></tr>';
    } else {
      for (const [k,v] of blockEntries){
        const n = Number(v || 0);
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${k}</td><td>${n}</td><td>${captureAttempts>0 ? pct(n/captureAttempts) : '0.0%'}</td>`;
        blockTb.appendChild(tr);
      }
    }
  }

  // Explicit hard-gate breakdown from detailed reason keys.
  // Supports both old flat key and new key with "|dist_before=..|enemy_pressure=..".
  if (hardGateTb){
    const hardGatePrefix = "hard_gate_step_into_uncaptured_vp";
    const hardGateRows = [];
    let hardGateTotal = 0;
    for (const [reason, rawCount] of captureOverrideEntries) {
      const reasonKey = String(reason || "");
      const n = Number(rawCount || 0);
      if (!reasonKey.startsWith(hardGatePrefix)) continue;
      hardGateTotal += n;
      let detail = "";
      if (reasonKey.includes("|")) {
        const parts = reasonKey.split("|").slice(1);
        const tags = [];
        for (const p of parts) {
          if (p.startsWith("dist_before=") || p.startsWith("enemy_pressure=")) {
            tags.push(p);
          }
        }
        detail = tags.length ? tags.join(" | ") : "";
      }
      // Skip legacy/non-detailed rows: user asked to hide them from report.
      if (detail) {
        hardGateRows.push({ detail, count: n });
      }
    }
    const agg = {};
    for (const r of hardGateRows) {
      agg[r.detail] = (agg[r.detail] || 0) + r.count;
    }
    const sortedHard = Object.entries(agg).sort((a,b)=>Number(b[1])-Number(a[1]));
    if (!sortedHard.length){
      hardGateTb.innerHTML = '<tr><td colspan="3" class="sub">No hard gate overrides found in this report</td></tr>';
    } else {
      for (const [detail, c] of sortedHard){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${detail}</td><td>${Number(c||0)}</td><td>${hardGateTotal>0 ? pct(Number(c||0)/hardGateTotal) : '0.0%'}</td>`;
        hardGateTb.appendChild(tr);
      }
    }
  }

  if (summary){
    const legalOverrides = Number(m.capture_legal_override_count || 0);
    const emergencyOverrides = Number(m.capture_emergency_override_count || 0);
    const plannerOverride = Number(sourceCounts.planner_override || 0);
    const finalizerOverride = Number(sourceCounts.finalizer_override || 0);
    const sb3Kept = Number(sourceCounts.sb3_kept || 0);
    summary.textContent = `sb3_kept=${sb3Kept} | planner_override=${plannerOverride} | finalizer_override=${finalizerOverride} | capture_attempted=${captureAttempts} | capture_legal_override=${legalOverrides} | capture_emergency_override=${emergencyOverrides}`;
  }
}

function renderActions(){
  const d = firstDetail();
  const root = document.getElementById('actionsDetail');
  root.innerHTML = '';
  if (!d){ root.textContent='No data'; return; }
  const ae = d.action_execution || {};
  const m = d.mission || {};
  const sections = [['US', ae.RL||{}], ['OTHER', ae.ENEMY||{}]];

  for (const [label,data] of sections){
    const panel = document.createElement('div');
    panel.className='panel';
    const rows = Object.entries(data).map(([k,v])=>`<tr><td>${k}</td><td>${v.count??0}</td><td>${Number(v.damage_per_action||0).toFixed(3)}</td></tr>`).join('');
    panel.innerHTML = `<h4 style="margin-top:0">${label}</h4><table><thead><tr><th>Type</th><th>Count</th><th>Damage/Action</th></tr></thead><tbody>${rows||'<tr><td colspan="3" class="sub">No data</td></tr>'}</tbody></table>`;
    root.appendChild(panel);
  }

  // Keep reaction metrics in the same visual format as other action panels.
  const reactionPanel = document.createElement('div');
  reactionPanel.className = 'panel';
  reactionPanel.innerHTML = `<h4 style="margin-top:0">REACTION</h4>
    <table>
      <thead><tr><th>Type</th><th>Count</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>REACTION_FIRE</td><td>${Number(m.reaction_fire_count||0)}</td><td>${pct(Number(m.reaction_fire_rate||0))}</td></tr>
        <tr><td>REACTION_WINDOW</td><td>${Number(m.reaction_window_count||0)}</td><td>-</td></tr>
        <tr><td>REACTION_FIRE_SKIPPED</td><td>${Number(m.reaction_fire_skipped_count||0)}</td><td>-</td></tr>
        <tr><td>REACTION_BY_SIDE</td><td>-</td><td>${Object.entries(m.reaction_fire_by_side || {}).map(([k,v])=>`${k}:${v}`).join(' | ') || '-'}</td></tr>
      </tbody>
    </table>`;
  root.appendChild(reactionPanel);
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
  const optionColor = (opt) => {
    const k = String(opt || '').toUpperCase();
    if (k === 'ADVANCE') return '#4aa3ff';
    if (k === 'ATTACK') return '#ff9f43';
    if (k === 'RETREAT') return '#a66cff';
    if (k === 'HOLD') return '#22c55e';
    return '#6b7280';
  };
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

  const perfGrid = document.createElement('div');
  perfGrid.style.display = 'grid';
  perfGrid.style.gridTemplateColumns = 'repeat(2, minmax(360px, 1fr))';
  perfGrid.style.gap = '10px';
  perfGrid.style.alignItems = 'start';
  panelL2.style.marginTop = '0';
  panelL3.style.marginTop = '0';
  perfGrid.appendChild(panelL2);
  perfGrid.appendChild(panelL3);
  root.appendChild(perfGrid);

  const panelMap = document.createElement('div');
  panelMap.className = 'panel';
  panelMap.style.marginTop = '10px';
  const transitions = Object.entries(map).flatMap(([strat, opts]) =>
    Object.entries(opts || {}).map(([opt, tuple]) => {
      const count = Array.isArray(tuple) ? Number(tuple[0]||0) : Number((tuple||{}).count||0);
      const ratio = Array.isArray(tuple) ? Number(tuple[1]||0) : Number((tuple||{}).ratio||0);
      return { strat, opt, count, ratio };
    })
  ).sort((a,b)=>b.count-a.count);
  const funnelData = transitions.map((t) => ({
    l3: t.strat,
    l2: t.opt,
    finalAction: "ALL_ACTIONS",
    count: t.count,
    key: `${t.strat}:${t.opt}`,
  }));
  const byL3 = funnelData.reduce((acc, row) => {
    const k = String(row.l3 || "UNKNOWN");
    if (!acc[k]) acc[k] = [];
    acc[k].push(row);
    return acc;
  }, {});
  const l3Funnels = Object.entries(byL3)
    .map(([l3Name, rows]) => ({ l3Name, rows }))
    .sort((a, b) => {
      const ta = a.rows.reduce((s, x) => s + Number(x.count || 0), 0);
      const tb = b.rows.reduce((s, x) => s + Number(x.count || 0), 0);
      return tb - ta;
    })
    ;
  const commonMaxRows = Math.max(
    1,
    ...l3Funnels.map(({ rows }) => {
      const l2Keys = new Set(rows.map((r) => String(r.l2 || "UNKNOWN")));
      return Math.max(rows.length, l2Keys.size);
    })
  );
  const commonRowGap = 68;
  const commonTopPad = 56;
  const commonBottomPad = 24;
  const commonSvgHeight = Math.max(220, commonTopPad + commonMaxRows * commonRowGap + commonBottomPad);

  const l3FunnelsHtml = l3Funnels.map(({ l3Name, rows }) => {
      const l3Total = rows.reduce((s, x) => s + Number(x.count || 0), 0);
      const maxCount = Math.max(1, ...rows.map((x) => Number(x.count || 0)));
      const sortedRows = rows.sort((a,b)=>Number(b.count||0)-Number(a.count||0));
      const l2Agg = sortedRows.reduce((acc, r) => {
        const k = String(r.l2 || "UNKNOWN");
        acc[k] = (acc[k] || 0) + Number(r.count || 0);
        return acc;
      }, {});
      const l2Nodes = Object.entries(l2Agg)
        .map(([name, count]) => ({ name, count: Number(count || 0) }))
        .sort((a,b)=>b.count-a.count);
      const finalNodes = sortedRows.map((r) => ({
        l2: String(r.l2 || "UNKNOWN"),
        finalAction: String(r.finalAction || "UNKNOWN"),
        count: Number(r.count || 0),
      }));

      const rowGap = commonRowGap;
      const svgHeight = commonSvgHeight;
      const xL3 = 90;
      const xL2 = 360;
      const xFinal = 690;
      const yForIndex = (i) => commonTopPad + i * rowGap;
      const linkPath = (x1, y1, x2, y2) => {
        const c1 = x1 + Math.max(40, (x2 - x1) * 0.35);
        const c2 = x2 - Math.max(40, (x2 - x1) * 0.35);
        return `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}`;
      };
      const l2Y = {};
      l2Nodes.forEach((n, idx) => { l2Y[n.name] = yForIndex(idx); });
      const finalY = {};
      finalNodes.forEach((n, idx) => { finalY[`${n.l2}__${n.finalAction}__${idx}`] = yForIndex(idx); });
      const l3Y = commonTopPad + ((commonMaxRows - 1) * rowGap) / 2;
      const l3R = Math.max(16, 16 + (l3Total / maxCount) * 4);

      const linksL3toL2 = l2Nodes.map((n) => {
        const y2 = l2Y[n.name];
        const scale = n.count / Math.max(1, l3Total);
        const strokeW = Math.max(2, 2 + scale * 14);
        const c = optionColor(n.name);
        return `<path d="${linkPath(xL3 + l3R, l3Y, xL2 - 12, y2)}" fill="none" stroke="${c}" stroke-opacity="0.6" stroke-width="${strokeW.toFixed(2)}"></path>`;
      }).join('');

      const linksL2toFinal = finalNodes.map((n, idx) => {
        const y1 = l2Y[n.l2];
        const y2 = finalY[`${n.l2}__${n.finalAction}__${idx}`];
        const scale = n.count / Math.max(1, l2Agg[n.l2] || 1);
        const strokeW = Math.max(1.5, 1.5 + scale * 10);
        const c = optionColor(n.l2);
        return `<path d="${linkPath(xL2 + 12, y1, xFinal - 12, y2)}" fill="none" stroke="${c}" stroke-opacity="0.62" stroke-width="${strokeW.toFixed(2)}"></path>`;
      }).join('');

      const nodeL3 = `
        <circle cx="${xL3}" cy="${l3Y}" r="${l3R.toFixed(1)}" fill="rgba(74,163,255,0.22)" stroke="rgba(74,163,255,0.75)"></circle>
        <text x="${xL3}" y="${l3Y+4}" text-anchor="middle" fill="#dbeafe" font-size="${Math.max(10, Math.round(l3R*0.62))}" font-weight="700">${l3Total}</text>
          <text x="${xL3}" y="${Math.max(14, l3Y-l3R-8).toFixed(1)}" text-anchor="middle" fill="#9fb3d1" font-size="10">${l3Name}</text>
      `;

      const nodesL2 = l2Nodes.map((n) => {
        const y = l2Y[n.name];
        const scale = n.count / Math.max(1, l3Total);
        const r = Math.max(12, 12 + scale * 18);
        const c = optionColor(n.name);
        return `
          <circle cx="${xL2}" cy="${y}" r="${r.toFixed(1)}" fill="${c}" fill-opacity="0.92" stroke="rgba(255,255,255,0.16)"></circle>
          <text x="${xL2}" y="${y+4}" text-anchor="middle" fill="#0b1020" font-size="${Math.max(9, Math.round(r*0.56))}" font-weight="700">${n.count}</text>
          <text x="${xL2}" y="${Math.max(14, y-r-8).toFixed(1)}" text-anchor="middle" fill="#9fb3d1" font-size="10">${n.name}</text>
        `;
      }).join('');

      const nodesFinal = finalNodes.map((n, idx) => {
        const y = finalY[`${n.l2}__${n.finalAction}__${idx}`];
        const scale = n.count / Math.max(1, l2Agg[n.l2] || 1);
        const r = Math.max(10, 10 + scale * 16);
        return `
          <circle cx="${xFinal}" cy="${y}" r="${r.toFixed(1)}" fill="rgba(122,197,255,0.18)" stroke="rgba(122,197,255,0.55)"></circle>
          <text x="${xFinal}" y="${y+4}" text-anchor="middle" fill="#dbeafe" font-size="${Math.max(8, Math.round(r*0.55))}" font-weight="700">${n.count}</text>
          <text x="${xFinal}" y="${Math.max(14, y-r-8).toFixed(1)}" text-anchor="middle" fill="#9fb3d1" font-size="10">${n.finalAction}</text>
        `;
      }).join('');

      const nodesAndLinks = `${linksL3toL2}${linksL2toFinal}${nodeL3}${nodesL2}${nodesFinal}`;
      return `<div class="panel" style="margin-bottom:0;min-width:420px;">
        <h5 style="margin:0 0 6px 0">${l3Name} Funnel</h5>
        <div class="sub" style="margin-bottom:6px">total transitions: ${l3Total}</div>
        <svg viewBox="0 0 760 ${svgHeight}" width="100%" height="${svgHeight}" style="background:rgba(15,18,27,0.45);border:1px solid var(--border);border-radius:10px;">
          ${nodesAndLinks}
        </svg>
      </div>`;
    }).join('');
  const tableRowsGrouped = (() => {
    const deepForTable = transitions.map((t) => ({
      c1: String(t.strat || "UNKNOWN"),
      c2: String(t.opt || "UNKNOWN"),
      c3: "ALL_ACTIONS",
      count: Number(t.count || 0),
    }));
    const grouped = deepForTable.reduce((acc, row) => {
      if (!acc[row.c1]) acc[row.c1] = {};
      if (!acc[row.c1][row.c2]) acc[row.c1][row.c2] = [];
      acc[row.c1][row.c2].push(row);
      return acc;
    }, {});
    return Object.keys(grouped)
      .sort((a, b) => a.localeCompare(b))
      .map((c1) => {
        const c2Groups = grouped[c1];
        const c2Html = Object.keys(c2Groups)
          .sort((a, b) => a.localeCompare(b))
          .map((c2) => {
            const c3Rows = c2Groups[c2]
              .sort((a, b) => {
                const c3cmp = a.c3.localeCompare(b.c3);
                if (c3cmp !== 0) return c3cmp;
                return b.count - a.count;
              })
              .map((r) => `<tr><td></td><td></td><td>${r.c3}</td><td>${r.count}</td></tr>`)
              .join('');
            return `<tr><td></td><td class="sub" style="font-weight:700;color:#8ec5ff;">${c2}</td><td></td><td></td></tr>${c3Rows}`;
          })
          .join('');
        return `<tr><td class="sub" style="font-weight:700;color:var(--accent);">${c1}</td><td></td><td></td><td></td></tr>${c2Html}`;
      })
      .join('');
  })();

  panelMap.innerHTML = `<h4 style="margin-top:0">Strategy → Option Map</h4>
    <div class="sub" style="margin-bottom:8px">Global funnel by L3 (L3 → L2, no near-VP filter)</div>
    <div style="margin-bottom:10px;display:grid;grid-template-columns:repeat(3,minmax(420px,1fr));gap:10px;align-items:start;overflow-x:auto;padding-bottom:4px;">${l3FunnelsHtml || '<div class="sub">No transition data</div>'}</div>
    <table><thead><tr><th>Strategy</th><th>Option</th><th>Final Action</th><th>Count</th></tr></thead><tbody>${
      tableRowsGrouped || '<tr><td colspan="4" class="sub">No data</td></tr>'
    }</tbody></table>`;
  root.appendChild(panelMap);
}

function renderRag(){
  const d = firstDetail();
  const root = document.getElementById('ragDetail');
  root.innerHTML = '';
  if (!d || !currentRows.length){
    root.innerHTML = '<div class="sub">No data</div>';
    return;
  }
  const n = Math.max(1, currentRows.length);
  const agg = currentRows.reduce((a,r)=>({
    loss_rate: a.loss_rate + Number(r.loss_rate||0),
    vp_entry_conversion_rate: a.vp_entry_conversion_rate + Number(r.vp_entry_conversion_rate||0),
    capture_conversion_after_contact: a.capture_conversion_after_contact + Number(r.capture_conversion_after_contact||0),
    finalizer_override: a.finalizer_override + Number(r.finalizer_override||0)
  }), {loss_rate:0, vp_entry_conversion_rate:0, capture_conversion_after_contact:0, finalizer_override:0});
  for (const k of Object.keys(agg)) agg[k] /= n;

  const m = d.mission || {};
  const topReasons = Object.entries(m.finalizer_override_reason_counts || {})
    .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
    .slice(0,3);
  const topReasonsText = topReasons.length
    ? topReasons.map(([k,v])=>`${k}:${v}`).join(', ')
    : 'none';

  const signals = [
    ['loss_rate', pct(agg.loss_rate), agg.loss_rate <= 0.60 ? 'OK' : 'WATCH'],
    ['vp_entry_conversion_rate', pct(agg.vp_entry_conversion_rate), agg.vp_entry_conversion_rate >= 0.30 ? 'OK' : 'WATCH'],
    ['capture_conversion_after_contact', pct(agg.capture_conversion_after_contact), agg.capture_conversion_after_contact >= 0.10 ? 'OK' : 'WATCH'],
    ['finalizer_override', pct(agg.finalizer_override), agg.finalizer_override <= 0.35 ? 'OK' : 'WATCH'],
  ];

  const signalRows = signals.map(([k,v,s])=>`<tr><td>${k}</td><td>${v}</td><td class="${s==='OK'?'ok':'warn'}">${s}</td></tr>`).join('');
  const prompt = [
    'Analiza este run de SB3 y sugiere una sola palanca para el siguiente ciclo.',
    `loss_rate=${agg.loss_rate.toFixed(4)}`,
    `vp_entry_conversion_rate=${agg.vp_entry_conversion_rate.toFixed(4)}`,
    `capture_conversion_after_contact=${agg.capture_conversion_after_contact.toFixed(4)}`,
    `finalizer_override=${agg.finalizer_override.toFixed(4)}`,
    `top_finalizer_override_reasons=${topReasonsText}`,
    'Responde con: hipotesis, cambio propuesto, riesgo principal, criterio de gate.'
  ].join('\\n');

  const panel = document.createElement('div');
  panel.className = 'panel';
  panel.innerHTML = `
    <div class="sub" style="margin-bottom:8px">
      RAG en eval es copiloto de analisis. No sustituye reglas de juego ni gates tacticos.
    </div>
    <table>
      <thead><tr><th>Signal</th><th>Value</th><th>Status</th></tr></thead>
      <tbody>${signalRows}</tbody>
    </table>
    <h4 style="margin:10px 0 6px">Prompt sugerido para RAG</h4>
    <textarea id="ragPromptBox" style="width:100%;min-height:140px;background:#10141d;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:8px">${prompt}</textarea>
    <div style="margin-top:8px;display:flex;justify-content:flex-end">
      <button id="ragCopyBtn">Copiar prompt</button>
    </div>
  `;
  root.appendChild(panel);

  const copyBtn = document.getElementById('ragCopyBtn');
  if (copyBtn){
    copyBtn.onclick = async () => {
      const box = document.getElementById('ragPromptBox');
      const txt = box ? box.value : '';
      try {
        await navigator.clipboard.writeText(txt);
        copyBtn.textContent = 'Copiado';
      } catch {
        copyBtn.textContent = 'No se pudo copiar';
      }
    };
  }
}

function renderHowTo(){
  const rootSummary = document.getElementById('howtoSummary');
  const rootChecks = document.getElementById('howtoChecks');
  rootSummary.innerHTML = '';
  rootChecks.innerHTML = '';

  if (!currentRows.length || !currentDetails.length){
    rootSummary.innerHTML = '<div class="sub">No data loaded.</div>';
    return;
  }

  const d = firstDetail() || {};
  const m = d.mission || {};
  const s = d.summary || {};
  const n = Math.max(1, currentRows.length);
  const agg = currentRows.reduce((a,r)=>({
    true_win_rate: a.true_win_rate + Number(r.true_win_rate||0),
    loss_rate: a.loss_rate + Number(r.loss_rate||0),
    vp_entry_conversion_rate: a.vp_entry_conversion_rate + Number(r.vp_entry_conversion_rate||0),
    capture_conversion_after_contact: a.capture_conversion_after_contact + Number(r.capture_conversion_after_contact||0),
    finalizer_override: a.finalizer_override + Number(r.finalizer_override||0),
    sb3_kept: a.sb3_kept + Number(r.sb3_kept||0),
    captured_final_avg: a.captured_final_avg + Number(r.captured_final_avg||0)
  }), {true_win_rate:0, loss_rate:0, vp_entry_conversion_rate:0, capture_conversion_after_contact:0, finalizer_override:0, sb3_kept:0, captured_final_avg:0});
  for (const k of Object.keys(agg)) agg[k] /= n;

  const checks = [
    {
      title: '1) Outcome Health',
      value: `true_win=${pct(agg.true_win_rate)} | loss=${pct(agg.loss_rate)}`,
      ok: agg.loss_rate <= 0.60,
      warn: agg.loss_rate <= 0.75,
      rule: 'Target: lower loss_rate and stable/improving true_win_rate'
    },
    {
      title: '2) VP Funnel',
      value: `entry_conv=${pct(agg.vp_entry_conversion_rate)} | after_contact=${pct(agg.capture_conversion_after_contact)} | final_vp=${asVpCount(agg.captured_final_avg)}`,
      ok: agg.vp_entry_conversion_rate >= 0.30 && agg.capture_conversion_after_contact >= 0.10,
      warn: agg.vp_entry_conversion_rate >= 0.20 && agg.capture_conversion_after_contact >= 0.05,
      rule: 'Target: VP entry and conversion both move up'
    },
    {
      title: '3) Override Pressure',
      value: `sb3_kept=${pct(agg.sb3_kept)} | finalizer_override=${pct(agg.finalizer_override)}`,
      ok: agg.finalizer_override <= 0.20,
      warn: agg.finalizer_override <= 0.35,
      rule: 'Target: low override pressure while keeping tactical quality'
    },
    {
      title: '4) Planning Alignment',
      value: `plan_progress_rate=${pct(Number(m.plan_progress_rate||0))} | capture_readiness=${String(m.capture_readiness ?? '-')}`,
      ok: Number(m.plan_progress_rate||0) >= 0.20,
      warn: Number(m.plan_progress_rate||0) >= 0.10,
      rule: 'Target: planning signals support VP progress'
    }
  ];

  let score = 0;
  for (const c of checks){
    if (c.ok) score += 2;
    else if (c.warn) score += 1;
  }
  let status = 'NO-GO';
  let statusCls = 'bad';
  if (score >= 7){ status = 'GO'; statusCls = 'ok'; }
  else if (score >= 4){ status = 'CONDITIONAL GO'; statusCls = 'warn'; }

  rootSummary.innerHTML = `
    <div class="k">Decision for this loaded report</div>
    <div class="v ${statusCls}" style="font-size:26px">${status}</div>
    <div class="sub">Use this as operational guidance, then confirm with multi-seed eval and tactical gates.</div>
  `;

  for (const c of checks){
    let rowCls = 'bad';
    let rowStatus = 'RED';
    if (c.ok){ rowCls = 'ok'; rowStatus = 'GREEN'; }
    else if (c.warn){ rowCls = 'warn'; rowStatus = 'YELLOW'; }
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.style.marginBottom = '8px';
    panel.innerHTML = `
      <div class="k">${c.title}</div>
      <div class="v ${rowCls}" style="font-size:18px">${rowStatus}</div>
      <div>${c.value}</div>
      <div class="sub">${c.rule}</div>
    `;
    rootChecks.appendChild(panel);
  }
}

function renderDetailTabs(){
  renderHowTo();
  renderTraining();
  renderMission();
  renderVPs();
  renderCombats();
  renderOverrides();
  renderActions();
  renderUnits();
  renderStrategies();
  renderRag();
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
    ['Reaction Fire', 'reaction_fire_count', true, 0.10, 'min'],
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
    const isCountMetric = key === 'reaction_fire_count' || key === 'vp_entries_taken' || key === 'captured_final_avg';
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
      <td>${asVpCount(Number(p.reaction_fire_count||0))}</td>
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
    'reaction_fire_count','vp_entries_taken','captured_final_avg','sb3_kept','finalizer_override'
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

async function postJson(url, payload){
  const r = await fetch(url, {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload || {})
  });
  const data = await r.json().catch(()=>({ok:false,error:'invalid json response'}));
  if (!r.ok || data.ok === false){
    throw new Error(data.error || `HTTP ${r.status}`);
  }
  return data;
}

function fmtDuration(seconds){
  const s = Number(seconds||0);
  const h = Math.floor(s/3600);
  const m = Math.floor((s%3600)/60);
  const ss = Math.floor(s%60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${ss}s`;
  return `${ss}s`;
}

function escHtml(v){
  return String(v ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function showControlLogs(data){
  const panel = document.getElementById('controlLogPanel');
  const title = document.getElementById('controlLogTitle');
  const meta = document.getElementById('controlLogMeta');
  const out = document.getElementById('controlLogStdout');
  const err = document.getElementById('controlLogStderr');
  if (!panel || !title || !meta || !out || !err) return;
  title.textContent = `${data.service_name || data.service_id || 'Service'} (${data.pm2_name || '-'})`;
  meta.textContent = `Últimas ${Number(data.lines || 300)} líneas por stream`;
  out.textContent = String(data.out_tail || '(empty)');
  err.textContent = String(data.err_tail || '(empty)');
  panel.style.display = 'block';
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function renderControl(){
  if (controlRenderInFlight) return;
  controlRenderInFlight = true;
  const tb = document.querySelector('#controlTable tbody');
  try {
    const data = await getJson('/api/control/services');
    const rows = data.services || [];
    const prevHtml = tb.innerHTML;
    const newRows = [];
    for (const s of rows){
      const statusCls = s.status === 'running' ? 'ok' : (s.status === 'reachable' ? 'warn' : 'bad');
      newRows.push(`
        <td>
          <div><strong>${s.name||s.id}</strong></div>
          <div class="sub">${s.description||''}</div>
        </td>
        <td class="${statusCls}">${String(s.status||'unknown').toUpperCase()}</td>
        <td>${s.pid ?? '-'}</td>
        <td>${fmtDuration(s.uptime_s||0)}</td>
        <td>${s.reachable ? 'yes' : 'no'}</td>
        <td>${s.health_url ? `<a href="${s.health_url}" target="_blank" rel="noopener">${s.health_url}</a>` : '-'}</td>
        <td>
          <button data-act="start" data-id="${s.id}">Start</button>
          <button data-act="stop" data-id="${s.id}">Stop</button>
          <button data-act="restart" data-id="${s.id}">Restart</button>
          <button data-act="logs" data-id="${s.id}">Logs</button>
        </td>
      `);
    }
    const newHtml = newRows.length
      ? newRows.map(r => `<tr>${r}</tr>`).join('')
      : '<tr><td colspan="7" class="sub">No services configured</td></tr>';
    if (newHtml !== prevHtml){
      tb.innerHTML = newHtml;
    }
    for (const b of tb.querySelectorAll('button[data-act]')){
      b.disabled = false;
      b.addEventListener('click', async ()=>{
        const id = b.getAttribute('data-id');
        const act = b.getAttribute('data-act');
        if (act === 'logs'){
          try{
            const data = await getJson(`/api/control/log?service_id=${encodeURIComponent(id)}&lines=300`);
            showControlLogs(data);
          }catch(e){
            alert(`No se pudo abrir logs: ${e.message||e}`);
          }
          return;
        }
        const prevText = b.textContent || '';
        b.textContent = '...';
        try{
          await postJson(`/api/control/${act}`, {service_id:id});
          await renderControl();
        }catch(e){
          alert(`Control action failed: ${e.message||e}`);
        }finally{
          b.disabled = false;
          b.textContent = prevText;
          for (const x of tb.querySelectorAll('button[data-act]')){
            x.disabled = false;
          }
        }
      });
    }
  } catch (e){
    if (!tb.innerHTML.trim()){
      tb.innerHTML = `<tr><td colspan="7" class="bad">Failed to load services: ${e.message||e}</td></tr>`;
    }
  } finally {
    controlRenderInFlight = false;
  }
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
  currentRows = rows;
  currentDetails = data.details || [];
  renderCards(rows);
  renderRows(rows);
  renderDetailTabs();
}

document.getElementById('reloadBtn').addEventListener('click', async ()=>{ await loadReports(); await loadSelected(); });
document.getElementById('reportSelect').addEventListener('change', loadSelected);
document.getElementById('historyReloadBtn').addEventListener('click', loadHistory);
document.getElementById('historyExportBtn').addEventListener('click', exportHistoryCsv);
document.getElementById('controlRefreshBtn').addEventListener('click', renderControl);
document.getElementById('controlLogCloseBtn').addEventListener('click', ()=>{
  const panel = document.getElementById('controlLogPanel');
  if (panel) panel.style.display = 'none';
});
setupTabs();

setInterval(renderControl, 10000);
(async ()=>{ await loadReports(); await loadSelected(); await loadHistory(); await renderControl(); })();
</script>
</body>
</html>
"""


def build_handler(reports_dir: Path, controller: ServiceController):
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

        def _text(self, body: str, status: int = 200):
            data = body.encode("utf-8", errors="replace")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._html(_page_html())
            if parsed.path == "/api/control/services":
                return self._json({"services": controller.list_status()})
            if parsed.path == "/api/control/log":
                qs = parse_qs(parsed.query)
                service_id = str((qs.get("service_id") or [""])[0]).strip()
                lines_raw = str((qs.get("lines") or ["300"])[0]).strip()
                if not service_id:
                    return self._json({"ok": False, "error": "missing service_id"}, status=400)
                try:
                    max_lines = max(50, min(3000, int(lines_raw)))
                except Exception:
                    max_lines = 300
                res = controller.read_service_logs(service_id, max_lines=max_lines)
                if not bool(res.get("ok")):
                    return self._json(res, status=400)
                res["lines"] = max_lines
                return self._json(res, status=200)
            if parsed.path == "/api/reports":
                files = sorted(
                    reports_dir.rglob("metrics_sb3_report_*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                return self._json(
                    {
                        "reports": [str(p.relative_to(reports_dir)).replace("\\", "/") for p in files],
                        "latest": (str(files[0].relative_to(reports_dir)).replace("\\", "/") if files else None),
                    }
                )
            if parsed.path == "/api/report":
                qs = parse_qs(parsed.query)
                name = (qs.get("name") or [""])[0]
                if not name:
                    return self._json({"error": "missing 'name'"}, status=400)
                rel = Path(name)
                path = (reports_dir / rel).resolve()
                try:
                    path.relative_to(reports_dir.resolve())
                except Exception:
                    return self._json({"error": "invalid report path"}, status=400)
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

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path not in {"/api/control/start", "/api/control/stop", "/api/control/restart"}:
                self.send_response(404)
                self.end_headers()
                return
            content_len = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                return self._json({"ok": False, "error": "invalid json payload"}, status=400)
            service_id = str(payload.get("service_id", "")).strip()
            if not service_id:
                return self._json({"ok": False, "error": "missing service_id"}, status=400)
            if parsed.path.endswith("/start"):
                res = controller.start(service_id)
            elif parsed.path.endswith("/stop"):
                res = controller.stop(service_id)
            else:
                res = controller.restart(service_id)
            return self._json(res, status=(200 if bool(res.get("ok")) else 400))

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
    controller = ServiceController(repo_root=repo_root)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(reports_dir, controller))
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

