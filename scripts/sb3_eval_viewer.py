from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
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


def _runs_root(repo_root: Path) -> Path:
    return (repo_root / "runs").resolve()


def _list_muzero_runs(repo_root: Path, limit: int = 50) -> list[dict]:
    root = _runs_root(repo_root)
    if not root.exists():
        return []
    run_dirs = [p for p in root.glob("muzero_*") if p.is_dir()]
    run_dirs = sorted(run_dirs, key=lambda p: p.stat().st_mtime, reverse=True)[: max(1, int(limit))]
    out: list[dict] = []
    for rd in run_dirs:
        run_manifest = rd / "run_manifest.json"
        metrics = rd / "metrics" / "summary.json"
        integrity = rd / "events" / "integrity.json"
        unitsides = rd / "metrics" / "units_sides.json"
        channels = rd / "metrics" / "observation_channels.json"
        out.append(
            {
                "run_id": rd.name,
                "run_dir": str(rd),
                "has_manifest": run_manifest.exists(),
                "has_metrics": metrics.exists(),
                "has_integrity": integrity.exists(),
                "has_unitsides": unitsides.exists(),
                "has_channels": channels.exists(),
            }
        )
    return out


def _read_muzero_run(repo_root: Path, run_id: str) -> dict:
    root = _runs_root(repo_root)
    rd = (root / run_id).resolve()
    try:
        rd.relative_to(root)
    except Exception:
        raise ValueError("invalid run_id")
    if not rd.exists() or not rd.is_dir():
        raise FileNotFoundError("run not found")
    manifest_path = rd / "run_manifest.json"
    metrics_path = rd / "metrics" / "summary.json"
    integrity_path = rd / "events" / "integrity.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    return {
        "run_id": run_id,
        "scenario_id": manifest.get("scenario_id"),
        "seed": manifest.get("seed"),
        "manifest_config": manifest.get("config", {}) or {},
        "metrics": (_read_json(metrics_path) if metrics_path.exists() else {}),
        "integrity": (_read_json(integrity_path) if integrity_path.exists() else {}),
    }


def _read_bench_latest(repo_root: Path) -> dict:
    path = (repo_root / "runs" / "bench_latest.json").resolve()
    if not path.exists():
        return {"scenario_id": "", "results": []}
    return _read_json(path)


def _read_muzero_channels(repo_root: Path, run_id: str) -> dict:
    root = _runs_root(repo_root)
    rd = (root / run_id).resolve()
    try:
        rd.relative_to(root)
    except Exception:
        raise ValueError("invalid run_id")
    path = rd / "metrics" / "observation_channels.json"
    if not path.exists():
        raise FileNotFoundError(
            f"channel preview not found for run '{run_id}'. "
            "Re-run training with CNN encoder to generate metrics/observation_channels.json."
        )
    return _read_json(path)


def _read_muzero_scenario_hexes(repo_root: Path, run_id: str) -> dict:
    run_payload = _read_muzero_run(repo_root, run_id)
    scenario_id = str(run_payload.get("scenario_id") or "").strip()
    seed = int(run_payload.get("seed") or 0)
    if not scenario_id:
        raise ValueError("run missing scenario_id")
    from assault_model.map.terrain_config import terrain_config
    from voec_sim.configs.config_loader import load_voec_config

    voec_cfg = load_voec_config((repo_root / "voec_sim" / "configs" / "voec_config.yaml").resolve())
    scenario_path = (voec_cfg.assets.scenarios_path / f"{scenario_id}.json").resolve()
    map_catalog_path = voec_cfg.assets.map_piece_catalog_path.resolve()
    if not scenario_path.exists():
        raise FileNotFoundError(f"scenario file not found: {scenario_path}")
    if not map_catalog_path.exists():
        raise FileNotFoundError(f"map piece catalog not found: {map_catalog_path}")

    raw_scenario = _read_json(scenario_path)
    raw_catalog = _read_json(map_catalog_path)
    catalog_pieces = (raw_catalog.get("pieces", {}) or {}) if isinstance(raw_catalog, dict) else {}
    hexes_by_key: dict[str, dict] = {}
    for piece in list((raw_scenario.get("map", {}) or {}).get("pieces", []) or []):
        piece_id = str(piece.get("id", "")).strip()
        origin = piece.get("origin", [0, 0]) if isinstance(piece, dict) else [0, 0]
        origin_q = int(origin[0]) if isinstance(origin, list) and len(origin) >= 2 else 0
        origin_r = int(origin[1]) if isinstance(origin, list) and len(origin) >= 2 else 0
        piece_def = catalog_pieces.get(piece_id, {}) if isinstance(catalog_pieces, dict) else {}
        for h in list((piece_def.get("hexes", []) if isinstance(piece_def, dict) else []) or []):
            q = origin_q + int(h.get("q", 0))
            r = origin_r + int(h.get("r", 0))
            terrain = str(h.get("terrain", "clear"))
            key = f"{q},{r}"
            hexes_by_key[key] = {"q": q, "r": r, "terrain": terrain}

    playable_hexes = sorted(
        [{"q": int(v["q"]), "r": int(v["r"])} for v in hexes_by_key.values()],
        key=lambda x: (int(x["r"]), int(x["q"])),
    )
    vp_hexes = [
        {"q": int(h.get("q")), "r": int(h.get("r"))}
        for h in list(((raw_scenario.get("vp", {}) or {}).get("hexes", []) or []))
        if isinstance(h.get("q"), int) and isinstance(h.get("r"), int)
    ]
    terrain_move_cost_by_hex: dict[str, float] = {}
    terrain_cover_by_hex: dict[str, float] = {}
    terrain_los_block_by_hex: dict[str, int] = {}
    for key, payload in hexes_by_key.items():
        terrain = str(payload.get("terrain", "clear"))
        move_cost = terrain_config.get_move_cost(terrain, "foot", default=1)
        if move_cost is None:
            terrain_move_cost_by_hex[key] = 0.0
        else:
            terrain_move_cost_by_hex[key] = float(max(0, int(move_cost))) / 4.0
        cover_dice = terrain_config.get_defense_dice(terrain, "INFANTRY")
        terrain_cover_by_hex[key] = float(len(cover_dice)) / 3.0
        los_type = str(terrain_config.get_los(terrain)).upper()
        terrain_los_block_by_hex[key] = 1 if los_type == "BLOCKED" else 0
    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "seed": seed,
        "hexes": playable_hexes,
        "vp_hexes": vp_hexes,
        "terrain_move_cost_by_hex": terrain_move_cost_by_hex,
        "terrain_cover_by_hex": terrain_cover_by_hex,
        "terrain_los_block_by_hex": terrain_los_block_by_hex,
    }


def _read_muzero_scenario_roles(repo_root: Path, run_id: str) -> dict:
    run_payload = _read_muzero_run(repo_root, run_id)
    scenario_id = str(run_payload.get("scenario_id") or "").strip()
    if not scenario_id:
        raise ValueError("run missing scenario_id")
    from voec_sim.configs.config_loader import load_voec_config

    voec_cfg = load_voec_config((repo_root / "voec_sim" / "configs" / "voec_config.yaml").resolve())
    scenario_path = (voec_cfg.assets.scenarios_path / f"{scenario_id}.json").resolve()
    if not scenario_path.exists():
        raise FileNotFoundError(f"scenario file not found: {scenario_path}")
    raw = _read_json(scenario_path)
    units = list(raw.get("units", []) or [])
    sides = sorted({str(u.get("side", "")).strip() for u in units if str(u.get("side", "")).strip()})
    victory_outcomes = raw.get("victory_outcomes", {}) or {}
    tracked_side = str(victory_outcomes.get("tracked_side", "")).strip()
    tracked_metric = str(victory_outcomes.get("metric", "")).strip()
    attacker_side = tracked_side if tracked_side in sides else ""
    if not attacker_side and len(sides) == 1:
        attacker_side = sides[0]
    defender_sides = [s for s in sides if s != attacker_side]
    vp_hexes = list((raw.get("vp", {}) or {}).get("hexes", []) or [])
    objective_total = len(vp_hexes)
    table = list(victory_outcomes.get("table", []) or [])
    for row in table:
        captured = row.get("captured", {}) if isinstance(row, dict) else {}
        if isinstance(captured, dict):
            objective_total = max(objective_total, int(captured.get("max", 0) or 0))
    return {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_path": str(scenario_path),
        "tracked_side": tracked_side,
        "tracked_metric": tracked_metric,
        "attacker_side": attacker_side,
        "defender_sides": defender_sides,
        "sides": sides,
        "objective_total": int(objective_total),
        "inference_source": "scenario_json",
    }


def _read_muzero_xai_decisions(repo_root: Path, run_id: str, limit: int = 2000) -> dict:
    root = _runs_root(repo_root)
    rd = (root / run_id).resolve()
    try:
        rd.relative_to(root)
    except Exception:
        raise ValueError("invalid run_id")
    path = rd / "xai" / "xai_decisions.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"xai decisions not found for run '{run_id}'. "
            "Re-run training with XAI decision logging enabled to generate xai/xai_decisions.jsonl."
        )
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except Exception:
                continue
    lim = max(1, min(20000, int(limit)))
    if len(rows) > lim:
        rows = rows[-lim:]
    return {"run_id": run_id, "count": len(rows), "rows": rows}


def _read_muzero_timeline(
    repo_root: Path,
    run_id: str,
    iteration: int | None = None,
    episode: int | None = None,
) -> dict:
    try:
        from agents.muzero.xai.timeline_exporter import export_muzero_episode_timeline
    except ModuleNotFoundError:
        repo_root_str = str(repo_root.resolve())
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
        from agents.muzero.xai.timeline_exporter import export_muzero_episode_timeline

    return export_muzero_episode_timeline(
        repo_root=repo_root,
        run_id=run_id,
        iteration=iteration,
        episode=episode,
    )


def _read_muzero_timeline_file(repo_root: Path, rel_path: str) -> dict:
    raw = str(rel_path or "").strip()
    if not raw:
        raise ValueError("missing path")
    path = (repo_root / raw).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except Exception:
        raise ValueError("invalid path")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"timeline file not found: {raw}")
    payload = _read_json(path)
    transitions = payload.get("transitions", []) if isinstance(payload, dict) else []
    if not isinstance(transitions, list):
        transitions = []
    return {
        "path": str(path),
        "schema_version": payload.get("schema_version", ""),
        "scenario_id": payload.get("scenario_id", ""),
        "seed": payload.get("seed", 0),
        "meta": payload.get("meta", {}) if isinstance(payload, dict) else {},
        "count": len(transitions),
        "transitions": transitions,
    }


def _export_muzero_timeline_file(
    repo_root: Path,
    run_id: str,
    iteration: int | None = None,
    episode: int | None = None,
    out_rel: str = "",
) -> dict:
    payload = _read_muzero_timeline(
        repo_root=repo_root,
        run_id=run_id,
        iteration=iteration,
        episode=episode,
    )
    out_path = (repo_root / str(out_rel).strip()).resolve() if str(out_rel).strip() else (
        repo_root / "runs" / run_id / "xai" / "muzero_timeline_latest.json"
    ).resolve()
    try:
        out_path.relative_to(repo_root.resolve())
    except Exception:
        raise ValueError("invalid out path")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rel = out_path.relative_to(repo_root.resolve()).as_posix()
    return {
        "ok": True,
        "run_id": run_id,
        "path": str(out_path),
        "path_rel": rel,
        "count": len(payload.get("transitions", []) or []),
        "timeline": payload,
    }


def _summarize_muzero_unitsides(repo_root: Path, run_id: str) -> dict:
    root = _runs_root(repo_root)
    rd = (root / run_id).resolve()
    try:
        rd.relative_to(root)
    except Exception:
        raise ValueError("invalid run_id")
    metrics_path = rd / "metrics" / "units_sides.json"
    if not metrics_path.exists():
        raise FileNotFoundError(
            f"units/sides metrics not found for run '{run_id}'. "
            "Re-run training with updated MuZero runner to generate metrics/units_sides.json."
        )
    payload = _read_json(metrics_path)
    required = {
        "transition_events",
        "side_turn_counts",
        "side_turn_rates",
        "top_action_units",
        "units_by_side",
        "global_actions",
        "vp_summary",
        "strategy_summary",
    }
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"units/sides metrics contract violation: missing fields {missing}")
    return payload


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
    #muzeroGlobalActionsSummary > .panel { margin-bottom:10px; }
    #muzeroGlobalActionsSummary .kv span {
      display:inline-block;
      margin-right:10px;
      margin-bottom:2px;
      white-space:nowrap;
    }
    #muzeroGlobalActionsSummary td,
    #muzeroGlobalActionsSummary th {
      white-space:nowrap;
      font-size:12px;
    }
    @media (max-width: 1400px) {
      #muzeroGlobalActionsSummary .kv {
        grid-template-columns: 1fr !important;
      }
      #muzeroGlobalActionsSummary .kv span {
        white-space:normal;
        word-break:break-word;
      }
      #muzeroGlobalActionsSummary td,
      #muzeroGlobalActionsSummary th {
        white-space:normal;
      }
    }
    @media (max-width: 1200px) {
      #muzeroXaiReplayLayout {
        grid-template-columns: 1fr !important;
      }
    }
    #muzeroXaiSummaryGrid {
      display:grid;
      grid-template-columns:repeat(4,minmax(180px,1fr));
      gap:8px 10px;
    }
    #muzeroXaiSummaryGrid .xai-card {
      background:#10141d;
      border:1px solid var(--border);
      border-radius:8px;
      padding:8px;
    }
    #muzeroXaiSummaryGrid .xai-card .k {
      color:var(--muted);
      font-size:12px;
      margin-bottom:4px;
    }
    #muzeroXaiSummaryGrid .xai-card .v {
      font-weight:700;
      font-size:16px;
    }
    #muzeroXaiSummaryGrid .xai-wide {
      grid-column:1 / -1;
    }
    #muzeroXaiSummaryGrid .xai-wide .v {
      font-size:13px;
      font-weight:600;
      line-height:1.35;
      white-space:normal;
      word-break:break-word;
    }
    @media (max-width: 1400px){
      #muzeroXaiSummaryGrid { grid-template-columns:repeat(2,minmax(180px,1fr)); }
    }
    @media (max-width: 900px){
      #muzeroXaiSummaryGrid { grid-template-columns:1fr; }
    }
    .hist-grid { display:grid; grid-template-columns:1fr; gap:10px; }
    .sparkline { width:100%; height:72px; background:#10141d; border:1px solid var(--border); border-radius:8px; padding:8px; box-sizing:border-box; }
    .units-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:10px; }
  </style>
</head>
<body>
  <h1>SB3 Eval Viewer</h1>
  <div class="top panel">
    <label>Mode:
      <select id="dashboardMode">
        <option value="sb3" selected>SB3</option>
        <option value="muzero">MuZero</option>
      </select>
    </label>
    <label id="muzeroRunLabel">Run:
      <select id="muzeroRunSelectTop"></select>
    </label>
    <button id="muzeroReloadBtnTop">Reload Runs</button>
    <label id="sb3ReportLabel">Report:
      <select id="reportSelect"></select>
    </label>
    <button id="reloadBtn">Reload</button>
    <span id="meta" class="sub"></span>
  </div>

  <div class="panel" id="sb3ServiceUrlsPanel" style="margin-bottom:12px">
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
    <button class="tab-btn active" data-tab="overview" data-domain="sb3">Overview</button>
    <button class="tab-btn" data-tab="howto" data-domain="sb3">How-To</button>
    <button class="tab-btn" data-tab="training" data-domain="sb3">Training</button>
    <button class="tab-btn" data-tab="mission" data-domain="sb3">Mission</button>
    <button class="tab-btn" data-tab="vps" data-domain="sb3">VPs</button>
    <button class="tab-btn" data-tab="combats" data-domain="sb3">Combats</button>
    <button class="tab-btn" data-tab="overrides" data-domain="sb3">Overrides</button>
    <button class="tab-btn" data-tab="actions" data-domain="sb3">Actions</button>
    <button class="tab-btn" data-tab="units" data-domain="sb3">Units/Side</button>
    <button class="tab-btn" data-tab="strategy" data-domain="sb3">Strategies</button>
    <button class="tab-btn" data-tab="rag" data-domain="sb3">RAG Copilot</button>
    <button class="tab-btn" data-tab="history" data-domain="sb3">History</button>
    <button class="tab-btn" data-tab="control" data-domain="both">Control</button>
    <button class="tab-btn" data-tab="muzero" data-domain="muzero">MuZero Ops</button>
    <button class="tab-btn" data-tab="muzero-runs" data-domain="muzero">MuZero Recent Runs</button>
    <button class="tab-btn" data-tab="muzero-units" data-domain="muzero">MuZero Units/Side</button>
    <button class="tab-btn" data-tab="muzero-actions" data-domain="muzero">MuZero Global Actions</button>
    <button class="tab-btn" data-tab="muzero-vps" data-domain="muzero">MuZero VPs</button>
    <button class="tab-btn" data-tab="muzero-strategies" data-domain="muzero">MuZero Strategies</button>
    <button class="tab-btn" data-tab="muzero-channels" data-domain="muzero">MuZero Channels</button>
    <button class="tab-btn" data-tab="muzero-xai" data-domain="muzero">MuZero XAI Decisions</button>
    <button class="tab-btn" data-tab="muzero-xai-map" data-domain="muzero">MuZero XAI Map Replay</button>
    <button class="tab-btn" data-tab="muzero-replay" data-domain="muzero">MuZero Match Replay</button>
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

  <div id="tab-muzero" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Ops</h3>
    <div class="top" id="muzeroRunBar" style="margin-bottom:8px; display:none">
      <label>Run:
        <select id="muzeroRunSelect"></select>
      </label>
      <button id="muzeroReloadBtn">Reload Runs</button>
    </div>
    <div id="muzeroCards" class="cards"></div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Run Detail</h4>
      <div id="muzeroRunDetail" class="kv"></div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Latest Benchmark</h4>
      <div id="muzeroBenchDetail" class="kv"></div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Benchmark Matrix</h4>
      <table id="muzeroBenchTable">
        <thead>
          <tr>
            <th>Agent</th><th>Episodes</th><th>Avg Return</th><th>Avg Steps</th><th>Finished Matches</th><th>Turn-Limit Finish</th><th>Win</th><th>Winner Sides</th><th>Tracked Capt Avg</th><th>Outcome Mix (Tracked)</th><th>VP Final Avg by Side</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
      <div class="sub" id="muzeroBenchReasons" style="margin-top:8px"></div>
    </div>
  </div>

  <div id="tab-muzero-units" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Units / Sides</h3>
    <div id="muzeroUnitsSidesDetail" class="kv"></div>
    <table id="muzeroUnitsTable" style="margin-top:8px">
      <thead>
        <tr><th>Side</th><th>Unit</th><th>Name</th><th>Category</th><th>Class</th><th>Dmg</th><th>Actions</th><th>BlockedTurns</th><th>Exp/Unit</th><th>Delta</th><th>Load</th><th>Atk</th><th>Kills</th><th>Dmg/Atk</th><th>Share Global</th><th>Share in Side</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div id="tab-muzero-runs" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Recent Runs</h3>
    <table id="muzeroRunsTable">
      <thead>
        <tr>
          <th>Run ID</th><th>Manifest</th><th>Metrics</th><th>Integrity</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div id="tab-muzero-actions" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Global Actions</h3>
    <div id="muzeroGlobalActionsSummary"></div>
    <div class="top" style="margin-top:8px">
      <label>Sort unified table:
        <select id="muzeroGlobalActionsSort">
          <option value="count" selected>Total Count</option>
          <option value="global_succ">Global Success</option>
          <option value="global_exp_dmg">Global Exp Dmg</option>
          <option value="global_exp_kills">Global Exp Kills</option>
          <option value="it_succ">IT Success</option>
          <option value="us_succ">US Success</option>
        </select>
      </label>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Unified Actions + Attack Effectiveness</h4>
      <table id="muzeroGlobalActionsBySideTable">
        <thead><tr><th>Action Kind</th><th>Total Count</th><th>Total Rate</th><th>IT Count</th><th>IT Rate</th><th>US Count</th><th>US Rate</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div id="tab-muzero-vps" class="tab-content panel">
    <h3 style="margin-top:0">MuZero VPs</h3>
    <div id="muzeroVpsSummary" class="kv"></div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Objective Decision Flow (Explainability Graph)</h4>
      <div id="muzeroVpsExplainGraph"></div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Objective Breakdown Graph (By Side)</h4>
      <div id="muzeroVpsHierBySideGraph"></div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Path Transition Matrix (Top)</h4>
      <table id="muzeroVpsPathTransitionsTable">
        <thead><tr><th>Scope</th><th>From Path</th><th>To Path</th><th>Count</th><th>Rate from From-Path</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Time-To-Convert by Reason (Top)</h4>
      <table id="muzeroVpsTimeToConvertReasonTable">
        <thead><tr><th>Scope</th><th>Reason</th><th>Count</th><th>Observed Conversion</th><th>TTC p50</th><th>TTC p90</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Top Harmful Paths</h4>
      <table id="muzeroVpsHarmfulPathsTable">
        <thead><tr><th>Path</th><th>Count</th><th>No-Conversion Rate</th><th>TTC p50</th><th>TTC p90</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">VP Actions by Side</h4>
      <table id="muzeroVpsBySideTable">
        <thead>
          <tr><th>Side</th><th>VP Init Avg</th><th>VP Final Avg</th><th>VP Gained Sum</th><th>VP Lost Sum</th><th>VP Net Sum</th><th>VP-related Actions</th><th>Capture Actions</th><th>VP Captures (state)</th><th>VP Capture Rate in Side</th><th>Capture Rate in Side</th><th>Units with VP Captures</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div id="tab-muzero-strategies" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Strategies</h3>
    <div id="muzeroStrategiesSummary" class="kv"></div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Strategy Mix by Side</h4>
      <table id="muzeroStrategiesBySideTable">
        <thead><tr><th>Strategy</th><th>Total Count</th><th>Total Rate</th><th>IT Count</th><th>IT Rate</th><th>US Count</th><th>US Rate</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div id="tab-muzero-channels" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Channels</h3>
    <div id="muzeroChannelsSummary" class="kv"></div>
    <div class="top" style="margin-top:8px">
      <label>Snapshot:
        <select id="muzeroChannelSnapshotSelect"></select>
      </label>
      <label>Channel:
        <select id="muzeroChannelSelect"></select>
      </label>
      <label>
        <input type="checkbox" id="muzeroShowConstantChannels" />
        Show constant channels
      </label>
      <button id="muzeroChannelRefreshBtn">Refresh</button>
    </div>
    <table id="muzeroChannelsTable" style="margin-top:8px">
      <thead>
        <tr><th>Idx</th><th>Name</th><th>Nonzero Cells</th><th>Nonzero Ratio</th><th>Mean</th><th>Max</th></tr>
      </thead>
      <tbody></tbody>
    </table>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Channel Heatmap</h4>
      <div id="muzeroChannelHeatmap" class="sub">No heatmap data.</div>
    </div>
  </div>

  <div id="tab-muzero-xai" class="tab-content panel">
    <h3 style="margin-top:0">MuZero XAI Decisions</h3>
    <div id="muzeroXaiSummary" class="kv"></div>
    <div class="top" style="margin-top:8px">
      <label>Side:
        <select id="muzeroXaiSideSelect">
          <option value="">(all)</option>
          <option value="IT">IT</option>
          <option value="US">US</option>
        </select>
      </label>
      <label>Action contains:
        <input id="muzeroXaiActionFilter" placeholder="FIRE_MOVE / CAPTURE / unit id"
          style="min-width:260px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:8px 10px;" />
      </label>
      <button id="muzeroXaiApplyBtn">Apply</button>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
      <div class="panel" style="margin-top:0">
        <h4 style="margin:0 0 8px 0">Table A: Latent Correlations (Top Dims)</h4>
        <table id="muzeroXaiDimTable">
          <thead>
            <tr><th>Dim</th><th>Support</th><th>Attack Rate</th><th>VP Capture Rate</th><th>Top Policy Prob Avg</th><th>Count</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="panel" style="margin-top:0">
        <h4 style="margin:0 0 8px 0">Table B: Decision Ownership by Side</h4>
        <table id="muzeroXaiOwnershipTable">
          <thead>
            <tr><th>Side</th><th>Rows</th><th>Policy Kept</th><th>Overwritten</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Table C: Step-Level Decisions (compact)</h4>
      <table id="muzeroXaiTable">
        <thead>
          <tr><th>It/Ep/Step</th><th>Turn</th><th>Side</th><th>Action</th><th>Top Policy</th><th>Top Prob</th><th>Value(root)</th><th>Latent Top Dims</th><th>Dyn Reward</th><th>MCTS (p/H/m)</th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <div id="tab-muzero-xai-map" class="tab-content panel">
    <h3 style="margin-top:0">MuZero XAI Map Replay</h3>
    <div id="muzeroXaiMapSummary" class="kv"></div>
    <div class="top" style="margin-top:8px">
      <label>Step:
        <input id="muzeroXaiMapStep" type="range" min="0" max="0" value="0" style="width:320px" />
      </label>
      <span id="muzeroXaiMapStepLabel" class="sub">step 0/0</span>
      <button id="muzeroXaiMapPlayBtn">Play</button>
      <button id="muzeroXaiMapPauseBtn">Pause</button>
      <label>Speed(ms):
        <input id="muzeroXaiMapSpeed" type="number" value="180" min="40" max="2000"
          style="width:88px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:6px 8px;" />
      </label>
      <label>Palette:
        <select id="muzeroXaiMapPalette">
          <option value="neon" selected>Neon</option>
          <option value="heat">Heat</option>
          <option value="mono">Mono</option>
        </select>
      </label>
      <label>Side colors:
        <select id="muzeroXaiMapSideMode">
          <option value="blend" selected>Blend</option>
          <option value="single">Single</option>
        </select>
      </label>
      <label>
        <input type="checkbox" id="muzeroXaiMapAccumulate" checked />
        Accumulate intensity
      </label>
    </div>
    <div style="display:grid;grid-template-columns:1.2fr 1fr;gap:10px;margin-top:8px;" id="muzeroXaiReplayLayout">
      <div class="panel" style="margin-top:0">
        <h4 style="margin:0 0 8px 0">Spatial Intensity (acting unit + target)</h4>
        <canvas id="muzeroXaiMapCanvas" width="720" height="560" style="width:100%;max-width:100%;height:560px;background:#0b0f18;border:1px solid var(--border);border-radius:8px;"></canvas>
      </div>
      <div style="display:grid;grid-template-rows:1fr 1fr;gap:10px;">
        <div class="panel" style="margin-top:0">
          <h4 style="margin:0 0 8px 0">Latent Activations Replay (dXX x step)</h4>
          <canvas id="muzeroXaiDimsCanvas" width="560" height="270" style="width:100%;max-width:100%;height:270px;background:#0b0f18;border:1px solid var(--border);border-radius:8px;"></canvas>
        </div>
        <div class="panel" style="margin-top:0">
          <h4 style="margin:0 0 8px 0">Latent Resonance Map (synthetic MRI style)</h4>
          <canvas id="muzeroXaiResCanvas" width="560" height="270" style="width:100%;max-width:100%;height:270px;background:#0b0f18;border:1px solid var(--border);border-radius:8px;"></canvas>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-muzero-replay" class="tab-content panel">
    <h3 style="margin-top:0">MuZero Match Replay (Timeline)</h3>
    <div id="muzeroReplaySummary" class="kv"></div>
    <div class="top" style="margin-top:8px">
      <button id="muzeroReplayLoadRunBtn">Load from selected run</button>
      <label>Iter:
        <input id="muzeroReplayIteration" type="number" value="-1" min="-1" max="9999"
          style="width:80px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:6px 8px;" />
      </label>
      <label>Ep:
        <input id="muzeroReplayEpisode" type="number" value="-1" min="-1" max="9999"
          style="width:80px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:6px 8px;" />
      </label>
      <label>Path:
        <input id="muzeroReplayPathInput" value="runs/ui_timeline_latest.json"
          style="min-width:300px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:8px 10px;" />
      </label>
      <button id="muzeroReplayExportBtn">Export now</button>
      <button id="muzeroReplayLoadPathBtn">Load JSON path</button>
      <label>Step:
        <input id="muzeroReplayStep" type="range" min="0" max="0" value="0" style="width:320px" />
      </label>
      <span id="muzeroReplayStepLabel" class="sub">step 0/0</span>
      <button id="muzeroReplayPlayBtn">Play</button>
      <button id="muzeroReplayPauseBtn">Pause</button>
      <label>Speed(ms):
        <input id="muzeroReplaySpeed" type="number" value="220" min="40" max="2000"
          style="width:88px;background:#1f2532;color:var(--txt);border:1px solid var(--border);border-radius:8px;padding:6px 8px;" />
      </label>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Step Details</h4>
      <div id="muzeroReplayStepDetail" class="kv"></div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Map Snapshot</h4>
      <canvas id="muzeroReplayMapCanvas" width="820" height="520"
        style="width:100%;max-width:100%;height:520px;background:#0b0f18;border:1px solid var(--border);border-radius:8px;"></canvas>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Units Snapshot</h4>
      <table id="muzeroReplayUnitsTable">
        <thead>
          <tr><th>Side</th><th>Unit ID</th><th>Unit</th><th>Hex</th><th>HP</th><th>Alive</th></tr>
        </thead>
        <tbody></tbody>
      </table>
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
let muzeroRuns = [];
let latestMuzeroRun = null;
let latestMuzeroBench = null;
let latestMuzeroUnitsSides = null;
let latestMuzeroChannels = null;
let latestMuzeroXai = null;
let latestMuzeroScenarioHexes = null;
let latestMuzeroScenarioRoles = null;
let muzeroXaiMapTimer = null;
let latestMuzeroReplay = null;
let muzeroReplayTimer = null;
let muzeroReplayHexOverlay = [];
let muzeroReplayHoverHex = null;
let controlRenderInFlight = false;
let dashboardMode = 'sb3';

function firstDetail(){
  return (currentDetails && currentDetails.length) ? currentDetails[0] : null;
}

async function loadReports(forceRefresh=false) {
  const sel = document.getElementById('reportSelect');
  const meta = document.getElementById('meta');
  try {
    const suffix = forceRefresh ? `?_ts=${Date.now()}` : '';
    const data = await getJson('/api/reports' + suffix);
    const prev = sel.value;
    sel.innerHTML = '';
    for (const name of data.reports){
      const o=document.createElement('option'); o.value=name; o.textContent=name; sel.appendChild(o);
    }
    if (prev && data.reports.includes(prev)) sel.value=prev;
    else if (data.latest) sel.value=data.latest;
    if (!data.reports || !data.reports.length){
      if (meta) meta.textContent = 'No SB3 reports found in reports dir.';
    }
  } catch (e) {
    if (meta) meta.textContent = `Error loading reports: ${e.message||e}`;
  }
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

  const criticalGuide = document.createElement('div');
  criticalGuide.className = 'panel';
  criticalGuide.style.marginBottom = '8px';
  criticalGuide.innerHTML = `
    <h4 style="margin:0 0 8px 0">Guia de metricas criticas (SB3)</h4>
    <table>
      <thead>
        <tr><th>Metrica</th><th>Senal critica</th><th>Interpretacion</th><th>Que ajustar</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>true_win_rate / loss_rate</td>
          <td>win bajo o loss alto sostenido</td>
          <td>la politica no convierte ventaja tactica en victoria</td>
          <td>subir presupuesto de entrenamiento, revisar reward de objetivo y mcts</td>
        </tr>
        <tr>
          <td>vp_entry_conversion_rate</td>
          <td>&lt; 20%</td>
          <td>el agente llega mal a zonas VP o no las prioriza</td>
          <td>reforzar reward de entrada VP, revisar canales de VP/distancia</td>
        </tr>
        <tr>
          <td>capture_conversion_after_contact</td>
          <td>&lt; 5-10%</td>
          <td>hay contacto pero no se cierra captura</td>
          <td>subir bonus de captura, penalizar espera con opcion de captura</td>
        </tr>
        <tr>
          <td>captured_final_avg</td>
          <td>plano o decreciente entre runs</td>
          <td>estancamiento en control de objetivos</td>
          <td>incrementar episodios por iteracion y/o mcts_simulations</td>
        </tr>
        <tr>
          <td>finalizer_override</td>
          <td>&gt; 35%</td>
          <td>la policy propuesta no pasa filtros tacticos</td>
          <td>mejorar calidad de acciones base (reward/policy), no solo reglas finales</td>
        </tr>
        <tr>
          <td>sb3_kept</td>
          <td>muy bajo junto a override alto</td>
          <td>desalineacion entre politica y criterio tactico</td>
          <td>ajustar exploracion y calibracion para reducir decisiones inviables</td>
        </tr>
        <tr>
          <td>plan_progress_rate</td>
          <td>&lt; 10-20%</td>
          <td>la secuencia de juego no progresa hacia objetivo</td>
          <td>subir peso de progreso/objetivo en shaping y extender horizonte util</td>
        </tr>
      </tbody>
    </table>
    <div class="sub" style="margin-top:8px">
      Regla rapida: primero estabilidad (win/loss), luego embudo VP (entry/capture), y al final eficiencia tactica (override/sb3_kept).
    </div>
  `;
  rootChecks.appendChild(criticalGuide);
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

function activateTab(tabName){
  const buttons = [...document.querySelectorAll('.tab-btn')];
  for (const x of buttons) x.classList.remove('active');
  const btn = buttons.find((b)=>b.dataset.tab === tabName);
  if (btn) btn.classList.add('active');
  for (const c of document.querySelectorAll('.tab-content')) c.classList.remove('active');
  const target = document.getElementById(`tab-${tabName}`);
  if (target) target.classList.add('active');
}

function applyDashboardMode(mode){
  dashboardMode = mode === 'muzero' ? 'muzero' : 'sb3';
  const tabButtons = [...document.querySelectorAll('.tab-btn')];
  for (const b of tabButtons){
    const domain = String(b.dataset.domain || 'sb3');
    const visible = domain === 'both' || domain === dashboardMode;
    b.style.display = visible ? '' : 'none';
  }
  // Keep SB3 header/cards always visible to avoid breaking report UX.
  const reportSelect = document.getElementById('reportSelect');
  const reportLabel = document.getElementById('sb3ReportLabel');
  const reloadBtn = document.getElementById('reloadBtn');
  const muzeroRunLabel = document.getElementById('muzeroRunLabel');
  const muzeroReloadBtnTop = document.getElementById('muzeroReloadBtnTop');
  const muzeroRunBar = document.getElementById('muzeroRunBar');
  const meta = document.getElementById('meta');
  const cards = document.getElementById('cards');
  const serviceUrlsPanel = document.getElementById('sb3ServiceUrlsPanel');
  const sb3Visible = dashboardMode === 'sb3';
  if (reportLabel) reportLabel.style.display = sb3Visible ? '' : 'none';
  if (reportSelect) reportSelect.style.display = sb3Visible ? '' : 'none';
  if (reloadBtn) reloadBtn.style.display = sb3Visible ? '' : 'none';
  if (meta) meta.style.display = sb3Visible ? '' : 'none';
  if (muzeroRunLabel) muzeroRunLabel.style.display = sb3Visible ? 'none' : '';
  if (muzeroReloadBtnTop) muzeroReloadBtnTop.style.display = sb3Visible ? 'none' : '';
  if (muzeroRunBar) muzeroRunBar.style.display = 'none';
  if (cards) cards.style.display = '';
  if (serviceUrlsPanel) serviceUrlsPanel.style.display = sb3Visible ? '' : 'none';
  if (dashboardMode === 'muzero'){
    const runMetrics = latestMuzeroRun ? (latestMuzeroRun.metrics || {}) : {};
    const runIntegrity = latestMuzeroRun ? (latestMuzeroRun.integrity || {}) : {};
    renderMuzeroTopCards(runMetrics, runIntegrity, latestMuzeroBench || {});
    activateTab('muzero');
  } else {
    loadSelected().catch(()=>{});
    activateTab('overview');
  }
}

async function loadSelected() {
  if (dashboardMode !== 'sb3') return;
  const name = document.getElementById('reportSelect').value;
  if (!name) return;
  const meta = document.getElementById('meta');
  try {
    const data = await getJson('/api/report?name='+encodeURIComponent(name));
    if (meta) meta.textContent = `timestamp=${data.meta?.timestamp||'-'} seed=${data.meta?.seed??'-'} episodes=${data.meta?.episodes??'-'}`;
    const rows = data.rows || [];
    currentRows = rows;
    currentDetails = data.details || [];
    renderCards(rows);
    renderRows(rows);
    renderDetailTabs();
  } catch (e) {
    if (meta) meta.textContent = `Error loading selected report: ${e.message||e}`;
  }
}

function renderMuzeroCards(metrics, integrity){
  const root = document.getElementById('muzeroCards');
  if (!root) return;
  const loss = Number((metrics || {}).loss || 0);
  const pl = Number((metrics || {}).policy_loss || 0);
  const vl = Number((metrics || {}).value_loss || 0);
  const rl = Number((metrics || {}).reward_loss || 0);
  const ol = Number((metrics || {}).objective_loss || 0);
  const transitionEvents = Number((integrity || {}).transition_events || 0);
  const trainEvents = Number((integrity || {}).train_step_events || 0);
  const valid = Boolean((integrity || {}).valid);
  const cards = [
    ["Loss", loss.toFixed(4), loss <= 0.20],
    ["Policy Loss", pl.toFixed(4), pl <= 0.10],
    ["Value Loss", vl.toFixed(4), vl <= 0.10],
    ["Reward Loss", rl.toFixed(4), rl <= 0.10],
    ["Objective Loss", ol.toFixed(4), ol <= 0.20],
    ["Transition Events", String(transitionEvents), transitionEvents > 0],
    ["TrainStep Events", String(trainEvents), trainEvents > 0],
    ["Integrity", valid ? "VALID" : "INVALID", valid],
  ];
  root.innerHTML = "";
  for (const [name, value, ok] of cards){
    const c = document.createElement('div');
    c.className = 'panel card';
    c.innerHTML = `<h3>${name}</h3><div class="v ${ok ? 'ok' : 'warn'}">${value}</div>`;
    root.appendChild(c);
  }
}

function renderMuzeroTopCards(metrics, integrity, bench){
  const root = document.getElementById('cards');
  if (!root) return;
  const loss = Number((metrics || {}).loss || 0);
  const pl = Number((metrics || {}).policy_loss || 0);
  const vl = Number((metrics || {}).value_loss || 0);
  const rl = Number((metrics || {}).reward_loss || 0);
  const ol = Number((metrics || {}).objective_loss || 0);
  const transitionEvents = Number((integrity || {}).transition_events || 0);
  const trainEvents = Number((integrity || {}).train_step_events || 0);
  const valid = Boolean((integrity || {}).valid);
  let winRate = 0;
  let timeoutRate = 0;
  if (bench && Array.isArray(bench.results)){
    const mz = bench.results.find((r)=>r.agent_name === 'muzero_stub') || bench.results[0];
    if (mz){
      winRate = Number(mz.win_rate || 0);
      timeoutRate = Number(mz.timeout_rate || 0);
    }
  }
  const cards = [
    ['Loss', loss.toFixed(4), loss <= 0.20],
    ['Policy Loss', pl.toFixed(4), pl <= 0.10],
    ['Value Loss', vl.toFixed(4), vl <= 0.10],
    ['Reward Loss', rl.toFixed(4), rl <= 0.10],
    ['Objective Loss', ol.toFixed(4), ol <= 0.20],
    ['Transition Events', String(transitionEvents), transitionEvents > 0],
    ['TrainStep Events', String(trainEvents), trainEvents > 0],
    ['Benchmark Win Rate', pct(winRate), winRate >= 0.50],
    ['Benchmark Turn-Limit Finish Rate', pct(timeoutRate), timeoutRate <= 0.50],
    ['Integrity', valid ? 'VALID' : 'INVALID', valid],
  ];
  root.innerHTML = '';
  for (const [name, display, good] of cards){
    const c = document.createElement('div');
    c.className = 'panel card';
    c.innerHTML = `<h3>${name}</h3><div class="v ${good ? 'ok' : 'warn'}">${display}</div>`;
    root.appendChild(c);
  }
}

function renderMuzeroRunDetail(run){
  const root = document.getElementById('muzeroRunDetail');
  if (!root) return;
  if (!run){
    root.innerHTML = '<div class="sub">No run selected.</div>';
    return;
  }
  const cfg = run.manifest_config || {};
  const rfRaw = String(cfg.reaction_fire_enabled || '').trim();
  const rfText = (rfRaw === '' || rfRaw === '1') ? 'ON' : (rfRaw === '0' ? 'OFF' : rfRaw);
  const model = cfg.model || {};
  const inputChannels = Number(model.observation_channels || model.input_channels || 0);
  const boardH = Number(model.observation_height || model.board_h || 0);
  const boardW = Number(model.observation_width || model.board_w || 0);
  const hiddenDim = Number(model.hidden_dim || 0);
  const actionDim = Number(model.action_dim || 0);
  const dynamicsBlocks = Number(model.dynamics_blocks || 0);
  const predictionBlocks = Number(model.prediction_blocks || 0);
  const repText = (inputChannels > 0 && boardH > 0 && boardW > 0 && hiddenDim > 0)
    ? `${inputChannels}x${boardH}x${boardW} -> hidden(${hiddenDim})`
    : '-';
  const dynInputText = (hiddenDim > 0 && actionDim > 0)
    ? `Linear(${hiddenDim}+${actionDim} -> ${hiddenDim}) + ReLU`
    : '-';
  const dynStateText = dynamicsBlocks > 0 ? `${dynamicsBlocks} residual MLP blocks` : '-';
  const predTrunkText = predictionBlocks > 0 ? `${predictionBlocks} residual MLP blocks` : '-';
  const policyHeadText = (hiddenDim > 0 && actionDim > 0) ? `Linear(${hiddenDim} -> ${actionDim})` : '-';
  const valueHeadText = hiddenDim > 0 ? `Linear(${hiddenDim} -> 1)` : '-';
  const rewardHeadText = hiddenDim > 0 ? `Linear(${hiddenDim} -> 1)` : '-';
  const objectiveHeadText = hiddenDim > 0 ? `Linear(${hiddenDim} -> 1)` : '-';
  const items = [
    ['Run ID', run.run_id || '-'],
    ['Scenario', run.scenario_id || '-'],
    ['Seed', String(run.seed ?? '-')],
    ['Reaction Fire', rfText],
    ['Iterations', String(cfg.iterations ?? '-')],
    ['Episodes / Iter', String(cfg.episodes_per_iter ?? '-')],
    ['Batch Size', String(cfg.batch_size ?? '-')],
    ['Resume CKPT', String(cfg.resume_checkpoint || '(none)')],
    ['Model - Representation (CNN)', repText],
    ['Model - Dynamics Input', dynInputText],
    ['Model - Dynamics State', dynStateText],
    ['Model - Prediction Trunk', predTrunkText],
    ['Model - Policy Head', policyHeadText],
    ['Model - Value Head', valueHeadText],
    ['Model - Reward Head', rewardHeadText],
    ['Model - Objective Head', objectiveHeadText],
    ['Train - Objective Loss Weight', String(cfg.objective_loss_weight ?? '-')],
    ['Train - Objective Target Mode', String(cfg.objective_target_mode ?? 'progress')],
    ['Train - Objective Pos Weight', String(cfg.objective_pos_weight ?? '-')],
    ['Metrics - Objective Loss', Number((run.metrics || {}).objective_loss ?? 0).toFixed(4)],
  ];
  renderKV('muzeroRunDetail', items);
}

function renderMuzeroRunsTable(runs){
  const tb = document.querySelector('#muzeroRunsTable tbody');
  if (!tb) return;
  tb.innerHTML = '';
  if (!runs || !runs.length){
    tb.innerHTML = '<tr><td colspan="4" class="sub">No MuZero runs found.</td></tr>';
    return;
  }
  for (const r of runs){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${r.run_id || '-'}</td>
      <td>${r.has_manifest ? '<span class="ok">yes</span>' : '<span class="bad">no</span>'}</td>
      <td>${r.has_metrics ? '<span class="ok">yes</span>' : '<span class="bad">no</span>'}</td>
      <td>${r.has_integrity ? '<span class="ok">yes</span>' : '<span class="bad">no</span>'}</td>
    `;
    tb.appendChild(tr);
  }
}

function renderMuzeroBenchDetail(bench){
  const root = document.getElementById('muzeroBenchDetail');
  if (!root) return;
  if (!bench || !Array.isArray(bench.results) || !bench.results.length){
    root.innerHTML = '<div class="sub">No benchmark data.</div>';
    return;
  }
  const mz = bench.results.find(r => r.agent_name === 'muzero_stub') || bench.results[0];
  const rnd = bench.results.find(r => r.agent_name === 'baseline_random');
  const reasons = mz.terminal_reasons || {};
  const reasonText = Object.entries(reasons).map(([k,v])=>`${k}: ${pct(Number(v||0))}`).join(' | ') || '-';
  const turnLimitFinishRate = Number(reasons.turn_unit_budget || reasons.max_steps || 0);
  const objectiveResolvedFinishRate = Number(reasons.objective_outcome_resolved || 0);
  const mzWinnerSides = Object.entries(mz.winner_side_counts || {})
    .map(([k,v])=>`${k}:${Number(v||0)} (${pct(Number((mz.winner_side_rates || {})[k] || 0))})`)
    .join(' | ') || '-';
  const rndWinnerSides = rnd ? (Object.entries(rnd.winner_side_counts || {})
    .map(([k,v])=>`${k}:${Number(v||0)} (${pct(Number((rnd.winner_side_rates || {})[k] || 0))})`)
    .join(' | ') || '-') : '-';
  const mzVpAvg = Object.entries(mz.vp_final_avg_by_side || {})
    .map(([k,v])=>`${k}:${Number(v||0).toFixed(2)}`)
    .join(' | ') || '-';
  const mzOutcomeMix = Object.entries(mz.scenario_outcome_rates || {})
    .map(([k,v])=>`${k}:${pct(Number(v||0))}`)
    .join(' | ') || '-';
  const rndOutcomeMix = rnd ? (Object.entries(rnd.scenario_outcome_rates || {})
    .map(([k,v])=>`${k}:${pct(Number(v||0))}`)
    .join(' | ') || '-') : '-';
  const mzVpDist = Object.entries(mz.vp_final_distribution_by_side || {})
    .map(([side, dist])=>{
      const txt = Object.entries(dist || {}).map(([k,v])=>`${k}:${pct(Number(v||0))}`).join(', ');
      return `${side}=>${txt || '-'}`;
    })
    .join(' | ') || '-';
  const roles = latestMuzeroScenarioRoles || {};
  const attackerSide = String(roles.attacker_side || mz.tracked_side || '').trim();
  const defenderSides = Array.isArray(roles.defender_sides) ? roles.defender_sides : [];
  const objectiveTotalRaw = Number(roles.objective_total || 0);
  const objectiveTotal = Number.isFinite(objectiveTotalRaw) && objectiveTotalRaw > 0 ? objectiveTotalRaw : null;
  const attackerWinRate = attackerSide ? Number((mz.winner_side_rates || {})[attackerSide] || 0) : null;
  const attackerCapturedAvg = Number(mz.tracked_captured_avg || 0);
  const defenderDeniedAvg = objectiveTotal !== null
    ? Math.max(0, objectiveTotal - attackerCapturedAvg)
    : null;
  const roleLine = attackerSide
    ? `Attacker=${attackerSide} | Defender=${defenderSides.length ? defenderSides.join(',') : '-'}`
    : '-';
  const roleMetric = String(roles.tracked_metric || mz.tracked_metric || '-');
  const items = [
    ['Scenario', String(bench.scenario_id || '-')],
    ['MuZero Avg Return', Number(mz.avg_return || 0).toFixed(3)],
    ['MuZero Win Rate', pct(Number(mz.win_rate || 0))],
    ['MuZero Turn-Limit Finish Rate', pct(Number(mz.timeout_rate || 0))],
    ['MuZero Finished Match Rate', pct(Number(mz.terminal_rate || 0))],
    ['Objective-Resolved Finish %', pct(objectiveResolvedFinishRate)],
    ['Turn-Limit Finish %', pct(turnLimitFinishRate)],
    ['Tracked Side / Metric', `${String(mz.tracked_side || '-')} / ${String(mz.tracked_metric || '-')}`],
    ['MuZero Tracked Capt Avg', Number(mz.tracked_captured_avg || 0).toFixed(2)],
    ['MuZero Tracked Outcome Mix', mzOutcomeMix],
    ['MuZero Winner Sides', mzWinnerSides],
    ['MuZero VP Final Avg by Side', mzVpAvg],
    ['MuZero VP Final Dist by Side', mzVpDist],
    ['Roles (from scenario.json)', roleLine],
    ['Role KPI Metric', roleMetric],
    ['Attacker Win Rate', attackerWinRate === null ? '-' : pct(attackerWinRate)],
    ['Attacker Objective Capt Avg', Number(attackerCapturedAvg || 0).toFixed(2)],
    ['Defender Objective Denied Avg', defenderDeniedAvg === null ? '-' : defenderDeniedAvg.toFixed(2)],
    ['Random Avg Return', rnd ? Number(rnd.avg_return || 0).toFixed(3) : '-'],
    ['Random Tracked Capt Avg', rnd ? Number(rnd.tracked_captured_avg || 0).toFixed(2) : '-'],
    ['Random Tracked Outcome Mix', rndOutcomeMix],
    ['Random Winner Sides', rndWinnerSides],
    ['Terminal Reasons (MuZero)', reasonText],
  ];
  renderKV('muzeroBenchDetail', items);

  const bt = document.querySelector('#muzeroBenchTable tbody');
  const reasonsEl = document.getElementById('muzeroBenchReasons');
  if (bt){
    bt.innerHTML = '';
    for (const r of (bench.results || [])){
      const winnerSidesText = Object.entries(r.winner_side_counts || {})
        .map(([k,v])=>`${k}:${Number(v||0)} (${pct(Number((r.winner_side_rates || {})[k] || 0))})`)
        .join(' | ') || '-';
      const outcomeMix = Object.entries(r.scenario_outcome_rates || {})
        .map(([k,v])=>`${k}:${pct(Number(v||0))}`)
        .join(' | ') || '-';
      const vpAvgText = Object.entries(r.vp_final_avg_by_side || {})
        .map(([k,v])=>`${k}:${Number(v||0).toFixed(2)}`)
        .join(' | ') || '-';
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${r.agent_name || '-'}</td>
        <td>${Number(r.episodes || 0)}</td>
        <td>${Number(r.avg_return || 0).toFixed(3)}</td>
        <td>${Number(r.avg_steps || 0).toFixed(2)}</td>
        <td>${pct(Number(r.terminal_rate || 0))}</td>
        <td>${pct(Number(r.timeout_rate || 0))}</td>
        <td>${pct(Number(r.win_rate || 0))}</td>
        <td>${winnerSidesText}</td>
        <td>${Number(r.tracked_captured_avg || 0).toFixed(2)}</td>
        <td>${outcomeMix}</td>
        <td>${vpAvgText}</td>
      `;
      bt.appendChild(tr);
    }
    if (!bench.results || !bench.results.length){
      bt.innerHTML = '<tr><td colspan="11" class="sub">No benchmark rows.</td></tr>';
    }
  }
  if (reasonsEl){
    const parts = [];
    for (const r of (bench.results || [])){
      const rs = r.terminal_reasons || {};
      const txt = Object.entries(rs).map(([k,v])=>`${k}:${pct(Number(v||0))}`).join(' | ') || '-';
      parts.push(`${r.agent_name || 'agent'} => ${txt}`);
    }
    reasonsEl.textContent = parts.length ? parts.join('   ||   ') : 'No terminal reasons available.';
  }
}

function renderMuzeroUnitsSides(data, errorMsg=''){
  const detail = document.getElementById('muzeroUnitsSidesDetail');
  const tb = document.querySelector('#muzeroUnitsTable tbody');
  if (!detail || !tb) return;
  if (!data || errorMsg){
    const msg = errorMsg ? `Error: ${errorMsg}` : 'No units/sides data.';
    renderKV('muzeroUnitsSidesDetail', [
      ['Status', msg],
      ['Hint', 'Select a MuZero run with TransitionEvent logs'],
    ]);
    tb.innerHTML = '<tr><td colspan="16" class="sub">No data.</td></tr>';
    return;
  }
  const sideCounts = data.side_turn_counts || {};
  const sideRates = data.side_turn_rates || {};
  const sidesText = Object.entries(sideCounts)
    .sort((a,b)=>Number(b[1]||0)-Number(a[1]||0))
    .map(([k,v]) => `${k}: ${v} (${pct(Number(sideRates[k] || 0))})`)
    .join(' | ') || '-';
  const sideUnitTotalText = Object.entries(data.units_by_side || {})
    .map(([k,v]) => {
      const p = v || {};
      const total = Number(p.total_actions || 0);
      const active = Number(p.active_units || 0);
      const expected = Number(p.expected_actions_per_active_unit || 0);
      return `${k}: ${total} (active=${active}, exp=${expected.toFixed(2)})`;
    })
    .join(' | ') || '-';
  const blockedTurnsText = Object.entries(data.units_by_side || {})
    .map(([k,v]) => {
      const units = ((v || {}).units || []);
      const blocked = units.reduce((acc, u)=>acc + Number(u.blocked_before_activation_turns || 0), 0);
      return `${k}: ${blocked}`;
    })
    .join(' | ') || '-';
  renderKV('muzeroUnitsSidesDetail', [
    ['Transition Events', String(Number(data.transition_events || 0))],
    ['Turn Share by Side', sidesText],
    ['Unit Action Volume by Side', sideUnitTotalText],
    ['Blocked Before Activation (turns)', blockedTurnsText],
  ]);
  tb.innerHTML = '';
  const unitsBySide = data.units_by_side || {};
  const rows = [];
  for (const [side, sidePayload] of Object.entries(unitsBySide)){
    for (const row of ((sidePayload || {}).units || [])){
      rows.push({
        side: String(side),
        unit_id: String(row.unit_id || '-'),
        unit_label: String(row.unit_label || '-'),
        category: String(row.category || '-'),
        class_name: String(row.class_name || row.unit_key || '-'),
        damage: Number(row.damage || 0),
        count: Number(row.count || 0),
        actions: Number(row.actions || row.count || 0),
        expected_actions_in_side: Number(
          row.expected_actions_in_side || (sidePayload || {}).expected_actions_per_active_unit || 0
        ),
        delta_vs_expected_in_side: Number(row.delta_vs_expected_in_side || 0),
        load_ratio_in_side: Number(row.load_ratio_in_side || 0),
        turns_eligible: Number(row.turns_eligible || 0),
        turns_activated: Number(row.turns_activated || row.actions || row.count || 0),
        activation_coverage: Number(row.activation_coverage || 0),
        blocked_before_activation_turns: Number(row.blocked_before_activation_turns || 0),
        attacks: Number(row.attacks || 0),
        kills: Number(row.kills || 0),
        damage_per_attack: Number(row.damage_per_attack || 0),
        rate_global: Number(row.rate_global || 0),
        rate_in_side: Number(row.rate_in_side || 0),
      });
    }
  }
  rows.sort((a,b)=>b.count-a.count);
  if (!rows.length){
    tb.innerHTML = '<tr><td colspan="16" class="sub">No unit action ids found in TransitionEvent logs for this run.</td></tr>';
    return;
  }
  for (const u of rows){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${u.side || '-'}</td>
      <td>${u.unit_id || '-'}</td>
      <td>${u.unit_label || '-'}</td>
      <td>${u.category || '-'}</td>
      <td>${u.class_name || '-'}</td>
      <td>${Number(u.damage || 0).toFixed(1)}</td>
      <td>${Number(u.actions || 0)}</td>
      <td>${Number(u.blocked_before_activation_turns || 0)}</td>
      <td>${Number(u.expected_actions_in_side || 0).toFixed(2)}</td>
      <td>${Number(u.delta_vs_expected_in_side || 0).toFixed(2)}</td>
      <td>${Number(u.load_ratio_in_side || 0).toFixed(2)}x</td>
      <td>${Number(u.attacks || 0)}</td>
      <td>${Number(u.kills || 0)}</td>
      <td>${Number(u.damage_per_attack || 0).toFixed(3)}</td>
      <td>${pct(Number(u.rate_global || 0))}</td>
      <td>${pct(Number(u.rate_in_side || 0))}</td>
    `;
    tb.appendChild(tr);
  }
}

function renderMuzeroGlobalActions(data, runMetrics){
  const summary = document.getElementById('muzeroGlobalActionsSummary');
  const bySideTable = document.getElementById('muzeroGlobalActionsBySideTable');
  const bySideTb = document.querySelector('#muzeroGlobalActionsBySideTable tbody');
  const sortSel = document.getElementById('muzeroGlobalActionsSort');
  if (!summary || !bySideTb || !bySideTable || !sortSel) return;
  const ga = (data || {}).global_actions || {};
  const rs = (data || {}).reward_summary || {};
  const os = (data || {}).option_space_summary || {};
  const ds = (data || {}).diagnostics_summary || {};
  const ae = ds.attack_effectiveness || {};
  const se = ds.search_efficiency_avg || {};
  const vc = ds.value_calibration || {};
  const vcp = ds.value_calibration_by_phase || {};
  const me = Array.isArray(ds.matchup_effectiveness) ? ds.matchup_effectiveness : [];
  const ce = Array.isArray(ds.context_effectiveness) ? ds.context_effectiveness : [];
  const dfr = ds.decision_flip_rate || {};
  const ooc = ds.objective_opportunity_conversion || {};
  const opf = ds.objective_progress_funnel || {};
  const tst = ds.tactical_survival_tradeoff || {};
  const xai = ds.xai_decision_signals || {};
  const dfrGlobal = pct(Number((((dfr || {}).global || {}).rate) || 0));
  const dfrIT = pct(Number((((((dfr || {}).by_side || {}).IT) || {}).rate) || 0));
  const dfrUS = pct(Number((((((dfr || {}).by_side || {}).US) || {}).rate) || 0));
  const oocGlobal = pct(Number((((ooc || {}).global || {}).rate) || 0));
  const oocIT = pct(Number((((((ooc || {}).by_side || {}).IT) || {}).rate) || 0));
  const oocUS = pct(Number((((((ooc || {}).by_side || {}).US) || {}).rate) || 0));
  const opfGlobal = (opf || {}).global || {};
  const opfBySide = (opf || {}).by_side || {};
  const opfConvGlobal = pct(Number(opfGlobal.conversion_rate || 0));
  const opfProgGlobal = pct(Number(opfGlobal.progress_rate || 0));
  const opfDeltaGlobal = Number(opfGlobal.avg_progress_delta || 0).toFixed(3);
  const opfOppGlobal = Number(opfGlobal.opportunities || 0);
  const opfStallsGlobal = Number(opfGlobal.stalls || 0);
  const ts = ds.train_stability || {};
  const objectiveLoss = Number((runMetrics || {}).objective_loss ?? 0);
  const xaiRep = xai.representation || {};
  const xaiPred = xai.prediction || {};
  const xaiDyn = xai.dynamics || {};
  const xaiTopPolicy = Array.isArray(xai.top_policy_actions) ? xai.top_policy_actions : [];
  const xaiTopDims = Array.isArray(xai.top_latent_dims) ? xai.top_latent_dims : [];
  const xaiTopPolicyPred = Array.isArray(xaiPred.top_policy_actions) ? xaiPred.top_policy_actions : xaiTopPolicy;
  const xaiTopDimsRep = Array.isArray(xaiRep.top_latent_dims) ? xaiRep.top_latent_dims : xaiTopDims;
  const compTotal = rs.components_total || {};
  const compAvg = rs.components_avg_per_transition || {};
  const osAvg = os.avg_per_transition || {};
  const aeByKind = Array.isArray(ae.by_action_kind) ? ae.by_action_kind : [];
  const aeBySideKind = ae.by_side_action_kind || {};
  const total = Number(ga.total_actions || 0);
  const kinds = ga.kinds || [];
  const kindsBySide = ga.kinds_by_side || {};
  const attackKinds = kinds
    .filter((x)=>!['MOVE','WAIT','TIMEOUT','UNKNOWN'].includes(String(x.action_kind || '').toUpperCase()))
    .reduce((acc, x)=>acc + Number(x.count || 0), 0);
  const fmtPair = (obj, digits) => Object.entries(obj || {})
    .map(([k,v])=>`<span><b>${k}</b>: ${Number(v || 0).toFixed(digits)}</span>`)
    .join('');
  const binsHtml = Array.isArray(vc.bins) && vc.bins.length
    ? vc.bins.map((b)=>`<span><b>${b.bin}</b>: ${Number(b.mae || 0).toFixed(3)}</span>`).join('')
    : '<span>-</span>';
  const phaseOrder = ['early', 'mid', 'late'];
  const phaseHtml = phaseOrder
    .map((p)=>{
      const row = vcp[p] || {};
      return `<span><b>${p}</b>: mae=${Number(row.mae || 0).toFixed(3)}, pred=${Number(row.avg_predicted || 0).toFixed(3)}, real=${Number(row.avg_realized_return || 0).toFixed(3)}, n=${Number(row.count || 0)}</span>`;
    })
    .join('');
  const aeGlobalRows = aeByKind.length
    ? aeByKind.slice(0, 6).map((r)=>`
        <tr>
          <td>${r.action_kind || '-'}</td>
          <td>${Number(r.count || 0)}</td>
          <td>${pct(Number(r.attack_success_estimate || 0))}</td>
          <td>${Number(r.expected_damage_estimate || 0).toFixed(3)}</td>
          <td>${Number(r.expected_kills_estimate || 0).toFixed(3)}</td>
        </tr>
      `).join('')
    : '<tr><td colspan="5" class="sub">No attack-effectiveness data.</td></tr>';
  const aeSideRows = Object.entries(aeBySideKind).length
    ? Object.entries(aeBySideKind).map(([side, rows])=>{
      const list = Array.isArray(rows) ? rows.slice(0, 3) : [];
      const text = list.map((r)=>`${r.action_kind}: succ ${pct(Number(r.attack_success_estimate || 0))}, dmg ${Number(r.expected_damage_estimate || 0).toFixed(2)}`).join(' | ');
      return `<tr><td>${side}</td><td>${text || '-'}</td></tr>`;
    }).join('')
    : '<tr><td colspan="2" class="sub">No side attack-effectiveness data.</td></tr>';
  const matchupRows = me.length
    ? me.slice(0, 8).map((r)=>`
        <tr>
          <td>${r.matchup || '-'}</td>
          <td>${Number(r.count || 0)}</td>
          <td>${pct(Number(r.attack_success_estimate || 0))}</td>
          <td>${Number(r.expected_damage_estimate || 0).toFixed(3)}</td>
          <td>${Number(r.expected_kills_estimate || 0).toFixed(3)}</td>
        </tr>
      `).join('')
    : '<tr><td colspan="5" class="sub">No matchup effectiveness data.</td></tr>';
  const parseContext = (ctxRaw) => {
    const raw = String(ctxRaw || '');
    const [distRaw, coverRaw, losRaw] = raw.split('|');
    const dist = String(distRaw || '').replace('dist_', '').replace('_', ' ').trim() || '-';
    const cover = String(coverRaw || '').replace('cover_', '').replace('_', ' ').trim() || '-';
    const los = String(losRaw || '').replace('los_', '').replace('_', ' ').trim() || '-';
    return { dist, cover, los };
  };
  const contextRows = ce.length
    ? ce
      .slice()
      .sort((a,b)=>Number(b.count || 0) - Number(a.count || 0))
      .slice(0, 10)
      .map((r)=>{
        const c = parseContext(r.context);
        return `
          <tr>
            <td>${c.dist}</td>
            <td>${c.cover}</td>
            <td>${c.los}</td>
            <td>${Number(r.count || 0)}</td>
            <td>${pct(Number(r.attack_success_estimate || 0))}</td>
            <td>${Number(r.expected_damage_estimate || 0).toFixed(3)}</td>
            <td>${Number(r.expected_kills_estimate || 0).toFixed(3)}</td>
          </tr>
        `;
      }).join('')
    : '<tr><td colspan="7" class="sub">No context effectiveness data.</td></tr>';
  const xaiPolicyText = xaiTopPolicyPred.length
    ? xaiTopPolicyPred.slice(0, 5).map((r)=>`${r.action_id}: ${Number(r.count || 0)} (${pct(Number(r.rate || 0))})`).join(' | ')
    : '-';
  const xaiDimsText = xaiTopDimsRep.length
    ? xaiTopDimsRep.slice(0, 5).map((r)=>`d${Number(r.dim || 0)}: ${Number(r.count || 0)} (${pct(Number(r.rate || 0))})`).join(' | ')
    : '-';
  const opfSideRows = Object.entries(opfBySide).length
    ? Object.entries(opfBySide).map(([side, row])=>`
      <tr>
        <td>${side}</td>
        <td>${Number((row || {}).opportunities || 0)}</td>
        <td>${pct(Number((row || {}).progress_rate || 0))}</td>
        <td>${pct(Number((row || {}).conversion_rate || 0))}</td>
        <td>${Number((row || {}).stalls || 0)}</td>
        <td>${Number((row || {}).avg_progress_delta || 0).toFixed(3)}</td>
      </tr>
    `).join('')
    : '<tr><td colspan="6" class="sub">No objective progress funnel data.</td></tr>';
  summary.innerHTML = `
    <div class="panel" style="margin-bottom:8px">
      <h4 style="margin:0 0 8px 0">Action Mix</h4>
      <div class="kv" style="grid-template-columns:repeat(3,minmax(160px,1fr));gap:6px 12px">
        <div><b>Total Actions</b><span>${total}</span></div>
        <div><b>Attack-like Actions</b><span>${attackKinds}</span></div>
        <div><b>Attack Share</b><span>${total > 0 ? pct(attackKinds / total) : '0.0%'}</span></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:8px">
      <h4 style="margin:0 0 8px 0">Search & Train Diagnostics</h4>
      <div class="kv" style="grid-template-columns:repeat(2,minmax(260px,1fr));gap:6px 12px">
        <div><b>Possible Actions Avg</b><span>legal=${Number(osAvg.legal_action_count || 0).toFixed(2)} | atk=${Number(osAvg.legal_attack_options || 0).toFixed(2)} | cap=${Number(osAvg.legal_capture_options || 0).toFixed(2)}</span></div>
        <div><b>MCTS Confidence Avg</b><span>p=${Number(osAvg.chosen_action_prob || 0).toFixed(3)} | margin=${Number(osAvg.mcts_margin || 0).toFixed(3)} | H=${Number(osAvg.mcts_entropy || 0).toFixed(3)}</span></div>
        <div><b>Search Efficiency Avg</b><span>visits=${Number(se.mcts_total_visits || 0).toFixed(2)} | active=${Number(se.mcts_active_actions || 0).toFixed(2)} | ratio=${Number(se.mcts_active_ratio || 0).toFixed(3)}</span></div>
        <div><b>Train Stability</b><span>grad_norm=${Number(ts.final_grad_norm || 0).toFixed(4)} | replay_age_mean=${Number(ts.replay_age_mean || 0).toFixed(1)} | replay_age_max=${Number(ts.replay_age_max || 0).toFixed(0)}</span></div>
        <div><b>Objective Head Loss</b><span>${objectiveLoss.toFixed(4)}</span></div>
        <div><b>Value Calibration MAE</b><span>${Number(vc.mae || 0).toFixed(4)}</span></div>
        <div><b>Value Calibration Bins</b><span>${binsHtml}</span></div>
        <div><b>Decision Flip Rate</b><span>global=${dfrGlobal} | IT=${dfrIT} | US=${dfrUS}</span></div>
        <div><b>Objective Opportunity Conv.</b><span>global=${oocGlobal} | IT=${oocIT} | US=${oocUS}</span></div>
        <div><b>Objective Progress Funnel (Global)</b><span>opp=${opfOppGlobal} | prog=${opfProgGlobal} | conv=${opfConvGlobal} | stalls=${opfStallsGlobal} | avgDelta=${opfDeltaGlobal}</span></div>
        <div><b>Tactical Survival Tradeoff</b><span>net_avg=${Number((((tst||{}).global||{}).net_tradeoff_avg || 0)).toFixed(3)} | out=${Number((((tst||{}).global||{}).damage_out_avg || 0)).toFixed(3)} | in+2=${Number((((tst||{}).global||{}).damage_in_next2_avg || 0)).toFixed(3)}</span></div>
        <div style="grid-column:1 / -1;"><b>Value Calibration by Phase</b><span>${phaseHtml || '-'}</span></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:8px">
      <h4 style="margin:0 0 8px 0">Objective Progress Funnel (By Side)</h4>
      <table>
        <thead><tr><th>Side</th><th>Opportunities</th><th>Progress Rate</th><th>Conversion Rate</th><th>Stalls</th><th>Avg Progress Delta</th></tr></thead>
        <tbody>${opfSideRows}</tbody>
      </table>
    </div>
    <div class="panel" style="margin-bottom:8px">
      <h4 style="margin:0 0 8px 0">Reward Components</h4>
      <div class="kv" style="grid-template-columns:1fr;gap:6px">
        <div><b>Total</b><span>${fmtPair(compTotal, 3) || '-'}</span></div>
        <div><b>Avg / Transition</b><span>${fmtPair(compAvg, 4) || '-'}</span></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:8px">
      <h4 style="margin:0 0 8px 0">XAI Decision Signals (Root)</h4>
      <div class="kv" style="grid-template-columns:repeat(2,minmax(260px,1fr));gap:6px 12px">
        <div><b>Representation L2 Avg</b><span>${Number((xaiRep.latent_l2_norm_avg ?? xai.latent_l2_norm_avg ?? 0)).toFixed(3)}</span></div>
        <div><b>Prediction Top-1 Avg</b><span>${pct(Number((xaiPred.policy_top1_confidence_avg ?? xai.policy_top1_confidence_avg ?? 0)))}</span></div>
        <div><b>Prediction Value(root) Avg</b><span>${Number((xaiPred.predicted_value_root_avg ?? xai.predicted_value_root_avg ?? 0)).toFixed(4)}</span></div>
        <div><b>Dynamics Pred Reward Avg</b><span>${Number((xaiDyn.pred_reward_avg ?? xai.dynamics_pred_reward_avg ?? 0)).toFixed(4)}</span></div>
        <div><b>Dynamics Next L2 Avg</b><span>${Number((xaiDyn.next_latent_l2_avg ?? xai.dynamics_next_latent_l2_avg ?? 0)).toFixed(3)}</span></div>
        <div><b>Dynamics Delta L2 Avg</b><span>${Number((xaiDyn.delta_l2_avg ?? xai.dynamics_delta_l2_avg ?? 0)).toFixed(3)}</span></div>
        <div style="grid-column:1 / -1;"><b>Top Policy Actions</b><span>${xaiPolicyText}</span></div>
        <div style="grid-column:1 / -1;"><b>Top Latent Dimensions</b><span>${xaiDimsText}</span></div>
      </div>
    </div>
    <div class="panel" style="margin-bottom:8px">
      <h4 style="margin:0 0 8px 0">Attack Effectiveness</h4>
      <div class="sub">Merged into unified action table below (global + by side).</div>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Matchup Effectiveness (Attacker → Target)</h4>
      <table>
        <thead><tr><th>Matchup</th><th>Count</th><th>Success</th><th>Exp Dmg</th><th>Exp Kills</th></tr></thead>
        <tbody>${matchupRows}</tbody>
      </table>
    </div>
    <div class="panel" style="margin-top:8px">
      <h4 style="margin:0 0 8px 0">Attack Context Effectiveness (Dist/Cover/LOS)</h4>
      <table>
        <thead><tr><th>Dist</th><th>Cover</th><th>LOS</th><th>Count</th><th>Success</th><th>Exp Dmg</th><th>Exp Kills</th></tr></thead>
        <tbody>${contextRows}</tbody>
      </table>
    </div>
  `;

  bySideTb.innerHTML = '';
  const sideNames = Object.keys(kindsBySide).sort();
  const byKind = {};
  for (const side of sideNames){
    for (const row of (kindsBySide[side] || [])){
      const kind = String(row.action_kind || 'UNKNOWN');
      if (!byKind[kind]) byKind[kind] = {};
      byKind[kind][side] = {
        count: Number(row.count || 0),
        rate: Number(row.rate_in_side || 0),
      };
    }
  }
  if (!sideNames.length || !Object.keys(byKind).length){
    bySideTable.querySelector('thead').innerHTML = '<tr><th>Action Kind</th><th>Total Count</th><th>Total Rate</th><th>Global Succ</th><th>Global Exp Dmg</th><th>Global Exp Kills</th><th>Count</th><th>Rate</th><th>Succ</th><th>Exp Dmg</th></tr>';
    bySideTb.innerHTML = '<tr><td colspan="10" class="sub">No side action breakdown.</td></tr>';
    return;
  }
  const aeGlobalMap = {};
  for (const row of aeByKind){
    const k = String(row.action_kind || 'UNKNOWN');
    aeGlobalMap[k] = {
      success: Number(row.attack_success_estimate || 0),
      expDmg: Number(row.expected_damage_estimate || 0),
      expKills: Number(row.expected_kills_estimate || 0),
    };
  }
  const aeSideMap = {};
  for (const [side, rows] of Object.entries(aeBySideKind || {})){
    aeSideMap[String(side)] = {};
    for (const row of (Array.isArray(rows) ? rows : [])){
      const k = String(row.action_kind || 'UNKNOWN');
      aeSideMap[String(side)][k] = {
        success: Number(row.attack_success_estimate || 0),
        expDmg: Number(row.expected_damage_estimate || 0),
      };
    }
  }
  const headerCells = [
    '<th>Action Kind</th>',
    '<th>Total Count</th>',
    '<th>Total Rate</th>',
    '<th>Global Succ</th>',
    '<th>Global Exp Dmg</th>',
    '<th>Global Exp Kills</th>',
  ];
  for (const side of sideNames){
    headerCells.push(`<th>${side} Count</th>`);
    headerCells.push(`<th>${side} Rate</th>`);
    headerCells.push(`<th>${side} Succ</th>`);
    headerCells.push(`<th>${side} Exp Dmg</th>`);
  }
  bySideTable.querySelector('thead').innerHTML = `<tr>${headerCells.join('')}</tr>`;
  const sortMode = String(sortSel.value || 'count');
  const kindsSorted = Object.keys(byKind).sort((a,b)=>{
    const sumCount = (kind) => {
      let v = 0;
      for (const side of sideNames){
        v += Number((byKind[kind][side] || {}).count || 0);
      }
      return v;
    };
    const globalSucc = (kind) => Number((aeGlobalMap[kind] || {}).success || 0);
    const globalDmg = (kind) => Number((aeGlobalMap[kind] || {}).expDmg || 0);
    const globalKills = (kind) => Number((aeGlobalMap[kind] || {}).expKills || 0);
    const sideSucc = (kind, side) => Number((((aeSideMap[side] || {})[kind] || {}).success) || 0);
    let va = 0;
    let vb = 0;
    if (sortMode === 'global_succ'){
      va = globalSucc(a); vb = globalSucc(b);
    } else if (sortMode === 'global_exp_dmg'){
      va = globalDmg(a); vb = globalDmg(b);
    } else if (sortMode === 'global_exp_kills'){
      va = globalKills(a); vb = globalKills(b);
    } else if (sortMode === 'it_succ'){
      va = sideSucc(a, 'IT'); vb = sideSucc(b, 'IT');
    } else if (sortMode === 'us_succ'){
      va = sideSucc(a, 'US'); vb = sideSucc(b, 'US');
    } else {
      va = sumCount(a); vb = sumCount(b);
    }
    if (vb !== va) return vb - va;
    return sumCount(b) - sumCount(a);
  });
  for (const kind of kindsSorted){
    const tr = document.createElement('tr');
    let totalCountForKind = 0;
    for (const side of sideNames){
      totalCountForKind += Number((byKind[kind][side] || {}).count || 0);
    }
    const cells = [
      `<td>${kind}</td>`,
      `<td>${totalCountForKind}</td>`,
      `<td>${total > 0 ? pct(totalCountForKind / total) : '0.0%'}</td>`,
      `<td>${pct(Number((aeGlobalMap[kind] || {}).success || 0))}</td>`,
      `<td>${Number((aeGlobalMap[kind] || {}).expDmg || 0).toFixed(3)}</td>`,
      `<td>${Number((aeGlobalMap[kind] || {}).expKills || 0).toFixed(3)}</td>`,
    ];
    for (const side of sideNames){
      const payload = byKind[kind][side] || { count: 0, rate: 0 };
      const eff = ((aeSideMap[side] || {})[kind] || {});
      cells.push(`<td>${Number(payload.count || 0)}</td>`);
      cells.push(`<td>${pct(Number(payload.rate || 0))}</td>`);
      cells.push(`<td>${pct(Number(eff.success || 0))}</td>`);
      cells.push(`<td>${Number(eff.expDmg || 0).toFixed(3)}</td>`);
    }
    tr.innerHTML = cells.join('');
    bySideTb.appendChild(tr);
  }
}

function renderMuzeroVps(data){
  const summary = document.getElementById('muzeroVpsSummary');
  const bySideTb = document.querySelector('#muzeroVpsBySideTable tbody');
  const hierGraph = document.getElementById('muzeroVpsHierBySideGraph');
  const pathTransTb = document.querySelector('#muzeroVpsPathTransitionsTable tbody');
  const ttcReasonTb = document.querySelector('#muzeroVpsTimeToConvertReasonTable tbody');
  const harmfulTb = document.querySelector('#muzeroVpsHarmfulPathsTable tbody');
  const explainGraph = document.getElementById('muzeroVpsExplainGraph');
  if (!summary || !bySideTb || !hierGraph || !explainGraph || !pathTransTb || !ttcReasonTb || !harmfulTb) return;
  const vp = (data || {}).vp_summary || {};
  const ds = (data || {}).diagnostics_summary || {};
  const ooc = ds.objective_opportunity_conversion || {};
  const opf = ds.objective_progress_funnel || {};
  const opx = ds.objective_progress_explain || {};
  const opa = ds.objective_path_analysis || {};
  const opfGlobal = (opf || {}).global || {};
  const opfBySide = (opf || {}).by_side || {};
  const opxBySide = (opx || {}).by_side || {};
  const pathMatrix = (opa.path_transition_matrix || {});
  const pathMatrixGlobal = Array.isArray(pathMatrix.global) ? pathMatrix.global : [];
  const pathMatrixBySide = (pathMatrix.by_side || {});
  const ttcByReason = (((opa.time_to_convert || {}).by_reason) || {});
  const ttcByReasonGlobal = Array.isArray(ttcByReason.global) ? ttcByReason.global : [];
  const ttcByReasonSide = (ttcByReason.by_side || {});
  const ttcByPath = (((opa.time_to_convert || {}).by_path) || {});
  const ttcByPathGlobal = Array.isArray(ttcByPath.global) ? ttcByPath.global : [];
  const ttcByPathSide = (ttcByPath.by_side || {});
  const harmfulPaths = Array.isArray(opa.harmful_paths_top) ? opa.harmful_paths_top : [];
  renderKV('muzeroVpsSummary', [
    ['VP-related Actions (total)', String(Number(vp.vp_related_actions_total || 0))],
    ['Capture Actions (total)', String(Number(vp.capture_actions_total || 0))],
    ['VP Captures (state total)', String(Number(vp.vp_captures_total || 0))],
    ['VP Captures / 1000 transitions', Number(vp.vp_captures_per_1000_transitions || 0).toFixed(2)],
    ['VP Capture Rate (global)', pct(Number(vp.vp_capture_rate_global || 0))],
    ['Units with VP Captures (total)', String(Number(vp.unique_units_with_vp_captures_total || 0))],
    ['VP Initial Avg by Side', Object.entries(vp.vp_initial_avg_by_side || {}).map(([k,v])=>`${k}:${Number(v||0).toFixed(2)}`).join(' | ') || '-'],
    ['VP Final Avg by Side', Object.entries(vp.vp_final_avg_by_side || {}).map(([k,v])=>`${k}:${Number(v||0).toFixed(2)}`).join(' | ') || '-'],
    ['VP Gained Sum by Side', Object.entries(vp.vp_gain_sum_by_side || {}).map(([k,v])=>`${k}:${Number(v||0)}`).join(' | ') || '-'],
    ['VP Lost Sum by Side', Object.entries(vp.vp_loss_sum_by_side || {}).map(([k,v])=>`${k}:${Number(v||0)}`).join(' | ') || '-'],
    ['VP Net Sum by Side', Object.entries(vp.vp_net_sum_by_side || {}).map(([k,v])=>`${k}:${Number(v||0)}`).join(' | ') || '-'],
    ['VP Net Avg / Episode by Side', Object.entries(vp.vp_net_avg_per_episode_by_side || {}).map(([k,v])=>`${k}:${Number(v||0).toFixed(3)}`).join(' | ') || '-'],
    ['Objective Opp. Conv. (global/by-side)', `global=${pct(Number((((ooc || {}).global || {}).rate) || 0))} | IT=${pct(Number((((((ooc || {}).by_side || {}).IT) || {}).rate) || 0))} | US=${pct(Number((((((ooc || {}).by_side || {}).US) || {}).rate) || 0))}`],
    ['Objective Progress Funnel (global)', `opp=${Number(opfGlobal.opportunities || 0)} | progress=${Number(opfGlobal.progress_actions || 0)} | conv=${Number(opfGlobal.conversions || 0)} | stalls=${Number(opfGlobal.stalls || 0)} | progRate=${pct(Number(opfGlobal.progress_rate || 0))} | convRate=${pct(Number(opfGlobal.conversion_rate || 0))} | avgDelta=${Number(opfGlobal.avg_progress_delta || 0).toFixed(3)}`],
    ['Note', 'Gain/Loss are gross flow sums across all transitions; Net is gain-loss.'],
    ['VP-related Rate (global)', pct(Number(vp.vp_related_action_rate_global || 0))],
    ['Capture Rate (global)', pct(Number(vp.capture_action_rate_global || 0))],
  ]);
  const flowRows = Object.entries(opfBySide || {});
  const flowPayloads = [{ side: 'GLOBAL', row: opfGlobal }];
  for (const [side, row] of flowRows){
    flowPayloads.push({ side: String(side), row: row || {} });
  }
  const mkFlowSvg = (title, row, explain) => {
    const opp = Math.max(0, Number((row || {}).opportunities || 0));
    const progress = Math.max(0, Number((row || {}).progress_actions || 0));
    const conversions = Math.max(0, Number((row || {}).conversions || 0));
    const stalls = Math.max(0, Number((row || {}).stalls || (opp - progress)));
    const noProgress = Math.max(0, opp - progress);
    const progressedNotConverted = Math.max(0, progress - conversions);
    const stalledNotConverted = Math.max(0, noProgress - Math.max(0, Math.min(conversions, noProgress)));
    const convFromProgress = Math.max(0, Math.min(conversions, progress));
    const convFromNoProgress = Math.max(0, conversions - convFromProgress);
    const explainRow = explain || {};
    const noProgCounts = explainRow.no_progress_reason_counts || {};
    const convPathCounts = explainRow.conversion_path_counts || {};
    const topNoProg = Object.entries(noProgCounts)
      .sort((a,b)=>Number(b[1] || 0) - Number(a[1] || 0))
      .slice(0, 2);
    const topConvPath = Object.entries(convPathCounts)
      .sort((a,b)=>Number(b[1] || 0) - Number(a[1] || 0))
      .slice(0, 2);
    const W = 430;
    const H = 290;
    const nodeW = 140;
    const nodeH = 36;
    const x0 = 10;
    const x1 = 150;
    const x2 = 280;
    const yCenter = 110;
    const yTop = 55;
    const yBot = 155;
    const rScale = opp > 0 ? Math.max(4.0, Math.min(22.0, 90.0 / Math.sqrt(opp))) : 5.0;
    const bubbleR = (v) => Math.max(10, Math.min(48, Math.sqrt(Math.max(0, v)) * rScale));
    const linkScale = opp > 0 ? Math.max(1.0, Math.min(4.0, 32.0 / opp)) : 1.0;
    const stroke = (v) => Math.max(1.0, Math.min(14.0, v * linkScale));
    const reasonR = (v) => Math.max(8, Math.min(18, Math.sqrt(Math.max(0, Number(v || 0))) * 3.2));
    const shortLabel = (txt) => {
      const s = String(txt || '').replaceAll('_', ' ');
      return s.length > 16 ? (s.slice(0, 15) + '…') : s;
    };
    const reasonBubble = (x, y, key, val, fill, strokeColor) => `
      <g>
        <title>${String(key)}: ${Number(val || 0)}</title>
        <circle cx="${x}" cy="${y}" r="${reasonR(val)}" fill="${fill}" stroke="${strokeColor}" opacity="0.95"></circle>
        <text x="${x}" y="${y + 3}" text-anchor="middle" fill="#eaf2f8" font-size="10">${Number(val || 0)}</text>
        <text x="${x}" y="${y + 20}" text-anchor="middle" fill="#9fb1c9" font-size="10">${shortLabel(key)}</text>
      </g>
    `;
    const reasonLink = (xA, yA, xB, yB, val, color) => `
      <path d="M ${xA} ${yA} C ${xA + 24} ${yA - 16}, ${xB - 18} ${yB + 10}, ${xB} ${yB}"
            fill="none" stroke="${color}" stroke-width="${Math.max(1.0, Math.min(6.0, Number(val || 0) * 0.35)).toFixed(2)}"
            stroke-linecap="round" opacity="0.75"></path>
    `;
    const isNotConvertedPath = (k) => String(k || '').toLowerCase().includes('not_converted') || String(k || '').toLowerCase().includes('stalled');
    const noProg1 = topNoProg[0] || null;
    const noProg2 = topNoProg[1] || null;
    const conv1 = topConvPath[0] || null;
    const conv2 = topConvPath[1] || null;
    const link = (xA, yA, xB, yB, val, color) => `
      <path d="M ${xA} ${yA} C ${xA + 80} ${yA}, ${xB - 80} ${yB}, ${xB} ${yB}"
            fill="none" stroke="${color}" stroke-width="${stroke(val).toFixed(2)}" stroke-linecap="round" opacity="0.65"></path>
    `;
    return `
      <div style="background:rgba(15,18,27,0.45);border:1px solid var(--border);border-radius:10px;padding:8px;">
      <div class="sub" style="margin:0 0 6px 0;"><b>${title}</b> · opp=${opp} · prog=${progress} · conv=${conversions} · stalls=${stalls}</div>
      <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;">
        <circle cx="${x0 + 58}" cy="${yCenter}" r="${bubbleR(opp)}" fill="rgba(93,173,226,0.24)" stroke="#5dade2"></circle>
        <circle cx="${x1 + 58}" cy="${yTop + nodeH / 2}" r="${bubbleR(progress)}" fill="rgba(46,204,113,0.20)" stroke="#2ecc71"></circle>
        <circle cx="${x1 + 58}" cy="${yBot + nodeH / 2}" r="${bubbleR(noProgress)}" fill="rgba(93,173,226,0.16)" stroke="#5dade2"></circle>
        <circle cx="${x2 + 58}" cy="${yTop + nodeH / 2}" r="${bubbleR(conversions)}" fill="rgba(245,176,65,0.20)" stroke="#f5b041"></circle>
        <circle cx="${x2 + 58}" cy="${yBot + nodeH / 2}" r="${bubbleR(Math.max(0, opp - conversions))}" fill="rgba(149,165,166,0.16)" stroke="#95a5a6"></circle>
        ${link(x0 + nodeW, yCenter, x1, yTop + nodeH / 2, progress, '#2ecc71')}
        ${link(x0 + nodeW, yCenter, x1, yBot + nodeH / 2, noProgress, '#5dade2')}
        ${link(x1 + nodeW, yTop + nodeH / 2, x2, yTop + nodeH / 2, convFromProgress, '#f5b041')}
        ${link(x1 + nodeW, yTop + nodeH / 2, x2, yBot + nodeH / 2, progressedNotConverted, '#58d68d')}
        ${link(x1 + nodeW, yBot + nodeH / 2, x2, yTop + nodeH / 2, convFromNoProgress, '#af7ac5')}
        ${link(x1 + nodeW, yBot + nodeH / 2, x2, yBot + nodeH / 2, stalledNotConverted, '#7f8c8d')}
        <rect x="${x0}" y="${yCenter - nodeH / 2}" width="${nodeW}" height="${nodeH}" rx="8" ry="8" fill="#1b2538" stroke="#4aa3ff"></rect>
        <text x="${x0 + 10}" y="${yCenter - 4}" fill="#d8e2f1" font-size="12">OPPORTUNITY</text>
        <text x="${x0 + 10}" y="${yCenter + 14}" fill="#9fb1c9" font-size="12">${opp}</text>
        <rect x="${x1}" y="${yTop}" width="${nodeW}" height="${nodeH}" rx="8" ry="8" fill="#1f3a2b" stroke="#2ecc71"></rect>
        <text x="${x1 + 10}" y="${yTop + 14}" fill="#dff6e9" font-size="12">PROGRESS</text>
        <text x="${x1 + 10}" y="${yTop + 30}" fill="#9de3be" font-size="12">${progress}</text>
        <rect x="${x1}" y="${yBot}" width="${nodeW}" height="${nodeH}" rx="8" ry="8" fill="#1b2e47" stroke="#5dade2"></rect>
        <text x="${x1 + 10}" y="${yBot + 14}" fill="#dcecff" font-size="12">NO PROGRESS</text>
        <text x="${x1 + 10}" y="${yBot + 30}" fill="#9cc6f4" font-size="12">${noProgress}</text>
        <rect x="${x2}" y="${yTop}" width="${nodeW}" height="${nodeH}" rx="8" ry="8" fill="#4a3118" stroke="#f5b041"></rect>
        <text x="${x2 + 10}" y="${yTop + 14}" fill="#fff1db" font-size="12">CONVERTED</text>
        <text x="${x2 + 10}" y="${yTop + 30}" fill="#f8cb8c" font-size="12">${conversions}</text>
        <rect x="${x2}" y="${yBot}" width="${nodeW}" height="${nodeH}" rx="8" ry="8" fill="#313b47" stroke="#95a5a6"></rect>
        <text x="${x2 + 10}" y="${yBot + 14}" fill="#e5eaef" font-size="12">NOT CONVERTED</text>
        <text x="${x2 + 10}" y="${yBot + 30}" fill="#bcc7d1" font-size="12">${Math.max(0, opp - conversions)}</text>
        <text x="${x1 + 58}" y="246" text-anchor="middle" fill="#7fb3d5" font-size="11">No-progress reasons</text>
        ${(topNoProg[0] ? reasonBubble(x1 + 22, 262, topNoProg[0][0], topNoProg[0][1], 'rgba(93,173,226,0.28)', '#5dade2') : '')}
        ${(topNoProg[1] ? reasonBubble(x1 + 94, 262, topNoProg[1][0], topNoProg[1][1], 'rgba(93,173,226,0.20)', '#5dade2') : '')}
        <text x="${x2 + 58}" y="246" text-anchor="middle" fill="#f5b041" font-size="11">Conversion paths</text>
        ${(noProg1 ? reasonLink(x1 + 22, 248, x1 + 58, yBot + nodeH / 2 + 4, noProg1[1], '#5dade2') : '')}
        ${(noProg2 ? reasonLink(x1 + 94, 248, x1 + 58, yBot + nodeH / 2 + 4, noProg2[1], '#5dade2') : '')}
        ${(conv1 ? reasonLink(x2 + 22, 248, x2 + 58, (isNotConvertedPath(conv1[0]) ? (yBot + nodeH / 2 + 4) : (yTop + nodeH / 2 + 4)), conv1[1], (isNotConvertedPath(conv1[0]) ? '#95a5a6' : '#f5b041')) : '')}
        ${(conv2 ? reasonLink(x2 + 94, 248, x2 + 58, (isNotConvertedPath(conv2[0]) ? (yBot + nodeH / 2 + 4) : (yTop + nodeH / 2 + 4)), conv2[1], (isNotConvertedPath(conv2[0]) ? '#95a5a6' : '#af7ac5')) : '')}
        ${(topConvPath[0] ? reasonBubble(x2 + 22, 262, topConvPath[0][0], topConvPath[0][1], 'rgba(245,176,65,0.28)', '#f5b041') : '')}
        ${(topConvPath[1] ? reasonBubble(x2 + 94, 262, topConvPath[1][0], topConvPath[1][1], 'rgba(175,122,197,0.24)', '#af7ac5') : '')}
      </svg>
      </div>
    `;
  };
  if (!flowPayloads.length){
    explainGraph.innerHTML = '<div class="sub">No objective funnel data to build explainability graph.</div>';
  } else {
    const cardsHtml = flowPayloads
      .filter((p)=>Number((p.row || {}).opportunities || 0) > 0)
      .map((p)=>mkFlowSvg(p.side, p.row || {}, ((opxBySide || {})[String(p.side)] || ((p.side === 'GLOBAL') ? ((opx || {}).global || {}) : {}))))
      .join('');
    explainGraph.innerHTML = cardsHtml
      ? `<div style="display:grid;grid-template-columns:repeat(3,minmax(280px,1fr));gap:10px;align-items:start;">${cardsHtml}</div>`
      : '<div class="sub">No opportunities in this run (graph not informative).</div>';
  }
  hierGraph.innerHTML = '';
  pathTransTb.innerHTML = '';
  ttcReasonTb.innerHTML = '';
  harmfulTb.innerHTML = '';
  const sideRowsForExplain = Object.entries(opfBySide || {}).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
  if (!sideRowsForExplain.length){
    hierGraph.innerHTML = '<div class="sub">No side opportunities to explain.</div>';
  } else {
    const mkBreakdownSvg = (side, funnelRow, convEntries, reasonEntries, ttcReasonMap, ttcPathMap) => {
      const opp = Math.max(0, Number((funnelRow || {}).opportunities || 0));
      const progress = Math.max(0, Number((funnelRow || {}).progress_actions || 0));
      const conversions = Math.max(0, Number((funnelRow || {}).conversions || 0));
      const stalls = Math.max(0, Number((funnelRow || {}).stalls || 0));
      const noProgress = Math.max(0, opp - progress);
      const W = 450;
      const H = 320;
      const baseX = 45;
      const lane1X = 170;
      const lane2X = 300;
      const lane3X = 400;
      const yMid = 130;
      const rr = (v) => Math.max(9, Math.min(28, Math.sqrt(Math.max(0, Number(v || 0))) * 2.5));
      const fmtTtc = (v) => (Number(v) >= 0 ? Number(v).toFixed(1) : '-');
      const urgencyColor = (meta, baseGood, baseWarn) => {
        const rate = Number((meta || {}).conversion_observed_rate ?? -1);
        const p90 = Number((meta || {}).ttc_p90_turns ?? -1);
        // High urgency: low conversion + long p90.
        if (rate >= 0 && p90 >= 0 && (rate < 0.25 || p90 >= 8.0)) return '#e74c3c';
        if (rate >= 0 && p90 >= 0 && (rate < 0.45 || p90 >= 5.0)) return '#f1c40f';
        return baseGood || baseWarn;
      };
      const path = (x1, y1, x2, y2, w, color) => `
        <path d="M ${x1} ${y1} C ${x1 + 42} ${y1}, ${x2 - 42} ${y2}, ${x2} ${y2}"
              fill="none" stroke="${color}" stroke-width="${Math.max(1.0, Math.min(5.0, Number(w || 1))).toFixed(2)}" opacity="0.7" />`;
      const bubble = (x, y, label, v, fill, stroke, metaText='') => `
        <g>
          <title>${label}: ${Number(v || 0)}</title>
          <circle cx="${x}" cy="${y}" r="${rr(v)}" fill="${fill}" stroke="${stroke}" />
          <text x="${x}" y="${y + 3}" text-anchor="middle" fill="#dfe8f4" font-size="10">${Number(v || 0)}</text>
          <text x="${x}" y="${y + 18}" text-anchor="middle" fill="#97aac1" font-size="10">${label}</text>
          ${metaText ? `<text x="${x}" y="${y + 32}" text-anchor="middle" fill="#8aa0b8" font-size="9">${metaText}</text>` : ''}
        </g>`;
      const convTop = (Array.isArray(convEntries) ? convEntries : []).slice(0, 3);
      const reasonTop = (Array.isArray(reasonEntries) ? reasonEntries : []).slice(0, 3);
      const convY = [80, 150, 220];
      const reasonY = [70, 150, 230];
      const convNodes = convTop.map((e, i)=>{
        const key = String(e[0]);
        return { key, count: Number(e[1] || 0), y: convY[i] || 190, meta: (ttcPathMap || {})[key] || null };
      });
      const reasonNodes = reasonTop.map((e, i)=>{
        const key = String(e[0]);
        return { key, count: Number(e[1] || 0), y: reasonY[i] || 230, meta: (ttcReasonMap || {})[key] || null };
      });
      const short = (s)=> {
        const t = String(s || '').replaceAll('_', ' ');
        return t.length > 16 ? (t.slice(0, 15) + '…') : t;
      };
      return `
        <div style="background:rgba(15,18,27,0.45);border:1px solid var(--border);border-radius:10px;padding:8px;">
          <div class="sub" style="margin:0 0 6px 0;"><b>${side}</b> · opp=${opp} · progress=${progress} · conv=${conversions} · stalls=${stalls}</div>
          <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" style="display:block;">
            <text x="${lane1X}" y="20" text-anchor="middle" fill="#7fb3d5" font-size="11">Funnel</text>
            <text x="${lane2X}" y="20" text-anchor="middle" fill="#f5b041" font-size="11">Conversion Paths (r/p50/p90)</text>
            <text x="${lane3X}" y="20" text-anchor="middle" fill="#af7ac5" font-size="11">No-Progress Reasons (r/p50/p90)</text>
            ${path(baseX, yMid, lane1X, 70, progress, '#2ecc71')}
            ${path(baseX, yMid, lane1X, 130, conversions, '#f5b041')}
            ${path(baseX, yMid, lane1X, 190, stalls, '#5dade2')}
            ${bubble(baseX, yMid, 'opp', opp, 'rgba(93,173,226,0.25)', '#5dade2')}
            ${bubble(lane1X, 70, 'progress', progress, 'rgba(46,204,113,0.22)', '#2ecc71')}
            ${bubble(lane1X, 130, 'converted', conversions, 'rgba(245,176,65,0.22)', '#f5b041')}
            ${bubble(lane1X, 190, 'stalls', stalls, 'rgba(93,173,226,0.18)', '#5dade2')}
            ${convNodes.map((n)=>{
              const meta = n.meta || {};
              const hasMeta = meta && Number(meta.count || 0) > 0;
              const metaTxt = hasMeta
                ? `r=${pct(Number(meta.conversion_observed_rate || 0))} TTC p50=${fmtTtc(meta.ttc_p50_turns)} p90=${fmtTtc(meta.ttc_p90_turns)}`
                : 'TTC: N/A';
              const c = urgencyColor(meta, '#f5b041', '#af7ac5');
              return (
                `${path(lane1X, 130, lane2X, n.y, n.count, '#f5b041')}
                 ${bubble(lane2X, n.y, short(n.key), n.count, 'rgba(245,176,65,0.18)', c, metaTxt)}`
              );
            }).join('')}
            ${reasonNodes.map((n)=>{
              const meta = n.meta || {};
              const hasMeta = meta && Number(meta.count || 0) > 0;
              const metaTxt = hasMeta
                ? `r=${pct(Number(meta.conversion_observed_rate || 0))} TTC p50=${fmtTtc(meta.ttc_p50_turns)} p90=${fmtTtc(meta.ttc_p90_turns)}`
                : 'TTC: N/A';
              const c = urgencyColor(meta, '#af7ac5', '#5dade2');
              return (
                `${path(lane1X, 190, lane3X, n.y, n.count, '#af7ac5')}
                 ${bubble(lane3X, n.y, short(n.key), n.count, 'rgba(175,122,197,0.18)', c, metaTxt)}`
              );
            }).join('')}
            <text x="${lane2X}" y="302" text-anchor="middle" fill="#7f8c8d" font-size="10">${convNodes.length ? '' : 'no conversion path rows'}</text>
            <text x="${lane3X}" y="302" text-anchor="middle" fill="#7f8c8d" font-size="10">${reasonNodes.length ? '' : 'no reason rows'}</text>
          </svg>
        </div>
      `;
    };
    const graphCards = [];
    for (const [side, funnelRow] of sideRowsForExplain){
      const opp = Math.max(1, Number((funnelRow || {}).opportunities || 0));
      const explainSide = (opxBySide || {})[side] || {};
      const noProgCounts = explainSide.no_progress_reason_counts || {};
      const convPathCounts = explainSide.conversion_path_counts || {};
      const noProgEntries = Object.entries(noProgCounts).sort((a,b)=>Number(b[1] || 0) - Number(a[1] || 0));
      const convEntries = Object.entries(convPathCounts).sort((a,b)=>Number(b[1] || 0) - Number(a[1] || 0));
      const reasonRows = Array.isArray((ttcByReasonSide || {})[side]) ? (ttcByReasonSide || {})[side] : [];
      const pathRows = Array.isArray((ttcByPathSide || {})[side]) ? (ttcByPathSide || {})[side] : [];
      const reasonMap = {};
      const pathMap = {};
      for (const r of reasonRows) {
        const k = String((r || {}).key || '');
        if (k) reasonMap[k] = r;
      }
      for (const r of pathRows) {
        const k = String((r || {}).key || '');
        if (k) pathMap[k] = r;
      }
      graphCards.push(mkBreakdownSvg(side, funnelRow, convEntries, noProgEntries, reasonMap, pathMap));
    }
    hierGraph.innerHTML = graphCards.length
      ? `<div style="display:grid;grid-template-columns:repeat(3,minmax(300px,1fr));gap:10px;align-items:start;">${graphCards.join('')}</div>`
      : '<div class="sub">No side opportunities to explain.</div>';
  }
  const transitionRows = [];
  for (const r of pathMatrixGlobal.slice(0, 12)){
    transitionRows.push({ scope: 'GLOBAL', row: r });
  }
  for (const [side, rows] of Object.entries(pathMatrixBySide || {})){
    for (const r of (Array.isArray(rows) ? rows.slice(0, 6) : [])){
      transitionRows.push({ scope: String(side), row: r });
    }
  }
  if (!transitionRows.length){
    pathTransTb.innerHTML = '<tr><td colspan="5" class="sub">No path transition matrix data.</td></tr>';
  } else {
    for (const item of transitionRows){
      const r = item.row || {};
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${item.scope}</td>
        <td>${String(r.from_path || '-')}</td>
        <td>${String(r.to_path || '-')}</td>
        <td>${Number(r.count || 0)}</td>
        <td>${pct(Number(r.rate_from || 0))}</td>
      `;
      pathTransTb.appendChild(tr);
    }
  }
  const ttcRows = [];
  for (const r of ttcByReasonGlobal.slice(0, 8)){
    ttcRows.push({ scope: 'GLOBAL', row: r });
  }
  for (const [side, rows] of Object.entries(ttcByReasonSide || {})){
    for (const r of (Array.isArray(rows) ? rows.slice(0, 4) : [])){
      ttcRows.push({ scope: String(side), row: r });
    }
  }
  if (!ttcRows.length){
    ttcReasonTb.innerHTML = '<tr><td colspan="6" class="sub">No time-to-convert reason data.</td></tr>';
  } else {
    for (const item of ttcRows){
      const r = item.row || {};
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${item.scope}</td>
        <td>${String(r.key || '-')}</td>
        <td>${Number(r.count || 0)}</td>
        <td>${pct(Number(r.conversion_observed_rate || 0))}</td>
        <td>${Number(r.ttc_p50_turns || -1).toFixed(2)}</td>
        <td>${Number(r.ttc_p90_turns || -1).toFixed(2)}</td>
      `;
      ttcReasonTb.appendChild(tr);
    }
  }
  if (!harmfulPaths.length){
    harmfulTb.innerHTML = '<tr><td colspan="5" class="sub">No harmful path ranking data.</td></tr>';
  } else {
    for (const r of harmfulPaths){
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${String(r.path || '-')}</td>
        <td>${Number(r.count || 0)}</td>
        <td>${pct(Number(r.no_conversion_rate || 0))}</td>
        <td>${Number(r.ttc_p50_turns || -1).toFixed(2)}</td>
        <td>${Number(r.ttc_p90_turns || -1).toFixed(2)}</td>
      `;
      harmfulTb.appendChild(tr);
    }
  }
  bySideTb.innerHTML = '';
  const rows = Object.entries(vp.by_side || {});
  if (!rows.length){
    bySideTb.innerHTML = '<tr><td colspan="12" class="sub">No VP-by-side data.</td></tr>';
    return;
  }
  for (const [side, payload] of rows){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${side}</td>
      <td>${Number(payload.vp_initial || 0).toFixed(2)}</td>
      <td>${Number(payload.vp_final || 0).toFixed(2)}</td>
      <td>${Number(payload.vp_gained_sum || 0)}</td>
      <td>${Number(payload.vp_lost_sum || 0)}</td>
      <td>${Number(payload.vp_net_sum || 0)}</td>
      <td>${Number(payload.vp_related_actions || 0)}</td>
      <td>${Number(payload.capture_actions || 0)}</td>
      <td>${Number(payload.vp_captures || 0)}</td>
      <td>${pct(Number(payload.vp_capture_rate_in_side || 0))}</td>
      <td>${pct(Number(payload.capture_rate_in_side || 0))}</td>
      <td>${Number(payload.unique_units_with_vp_captures || payload.unique_units_with_vp_actions || 0)}</td>
    `;
    bySideTb.appendChild(tr);
  }
}

function renderMuzeroStrategies(data){
  const summary = document.getElementById('muzeroStrategiesSummary');
  const sideTable = document.getElementById('muzeroStrategiesBySideTable');
  const sideTb = document.querySelector('#muzeroStrategiesBySideTable tbody');
  if (!summary || !sideTb || !sideTable) return;
  const ss = (data || {}).strategy_summary || {};
  const rows = ss.strategies || [];
  const bySide = ss.strategies_by_side || {};

  const getRate = (name) =>
    Number((rows.find((r) => String(r.strategy) === name) || {}).rate_global || 0);
  renderKV('muzeroStrategiesSummary', [
    ['Total Actions', String(Number(ss.total_actions || 0))],
    ['Advance Share', pct(getRate('ADVANCE'))],
    ['Attack Share', pct(getRate('ATTACK'))],
    ['Capture Share', pct(getRate('CAPTURE'))],
    ['Assault Share', pct(getRate('ASSAULT'))],
    ['Hold Share', pct(getRate('HOLD'))],
  ]);

  sideTb.innerHTML = '';
  const sideNames = Object.keys(bySide).sort();
  const byStrategy = {};
  for (const side of sideNames){
    for (const r of (bySide[side] || [])){
      const strategy = String(r.strategy || 'OTHER');
      if (!byStrategy[strategy]) byStrategy[strategy] = {};
      byStrategy[strategy][side] = {
        count: Number(r.count || 0),
        rate: Number(r.rate_in_side || 0),
      };
    }
  }
  if (!sideNames.length || !Object.keys(byStrategy).length){
    sideTable.querySelector('thead').innerHTML = '<tr><th>Strategy</th><th>Total Count</th><th>Total Rate</th><th>Count</th><th>Rate</th></tr>';
    sideTb.innerHTML = '<tr><td colspan="5" class="sub">No side strategy breakdown.</td></tr>';
    return;
  }
  const headerCells = ['<th>Strategy</th>', '<th>Total Count</th>', '<th>Total Rate</th>'];
  for (const side of sideNames){
    headerCells.push(`<th>${side} Count</th>`);
    headerCells.push(`<th>${side} Rate</th>`);
  }
  sideTable.querySelector('thead').innerHTML = `<tr>${headerCells.join('')}</tr>`;
  const strategyRows = rows.length ? rows : Object.keys(byStrategy).map((s)=>({strategy:s,count:0,rate_global:0}));
  const sortedStrategies = strategyRows
    .slice()
    .sort((a,b)=>Number(b.count||0)-Number(a.count||0))
    .map((r)=>String(r.strategy || 'OTHER'));
  for (const strategy of sortedStrategies){
    let totalCount = 0;
    for (const side of sideNames){
      totalCount += Number((byStrategy[strategy] && byStrategy[strategy][side] ? byStrategy[strategy][side].count : 0) || 0);
    }
    const globalRow = rows.find((r)=>String(r.strategy||'OTHER')===strategy) || {};
    const totalRate = Number(globalRow.rate_global || 0);
    const cells = [
      `<td>${strategy}</td>`,
      `<td>${totalCount}</td>`,
      `<td>${pct(totalRate)}</td>`,
    ];
    for (const side of sideNames){
      const payload = (byStrategy[strategy] || {})[side] || { count: 0, rate: 0 };
      cells.push(`<td>${Number(payload.count || 0)}</td>`);
      cells.push(`<td>${pct(Number(payload.rate || 0))}</td>`);
    }
    const tr = document.createElement('tr');
    tr.innerHTML = cells.join('');
    sideTb.appendChild(tr);
  }
}

function _updateMuzeroChannelHeatmap(){
  const data = latestMuzeroChannels;
  const heatRoot = document.getElementById('muzeroChannelHeatmap');
  const snapshotSel = document.getElementById('muzeroChannelSnapshotSelect');
  const channelSel = document.getElementById('muzeroChannelSelect');
  if (!heatRoot || !snapshotSel || !channelSel || !data) return;
  const snapshots = data.snapshots || [];
  if (!snapshots.length){
    heatRoot.innerHTML = '<div class="sub">No snapshot planes available.</div>';
    return;
  }
  const snap = snapshots.find((s)=>String(s.label) === String(snapshotSel.value)) || snapshots[0];
  const channel = (snap.channels || []).find((c)=>String(c.index) === String(channelSel.value)) || (snap.channels || [])[0];
  if (!channel || !Array.isArray(channel.values)){
    heatRoot.innerHTML = '<div class="sub">No channel values available.</div>';
    return;
  }
  const values = channel.values;
  let minV = Infinity;
  let maxV = -Infinity;
  for (const row of values){
    for (const v of row){
      const fv = Number(v || 0);
      if (fv < minV) minV = fv;
      if (fv > maxV) maxV = fv;
    }
  }
  const den = (maxV - minV) || 1e-9;
  const isUniform = Math.abs(maxV - minV) < 1e-12;
  const rowsHtml = values.map((row)=>`<tr>${
    row.map((v)=>{
      const fv = Number(v || 0);
      let color = 'rgba(40,52,80,0.25)';
      if (isUniform){
        if (Math.abs(fv) < 1e-12){
          color = 'rgba(90,100,120,0.35)';
        } else if (fv > 0){
          // Strong visible fill for uniform nonzero channels.
          color = 'rgba(0,220,140,0.90)';
        } else {
          color = 'rgba(255,80,80,0.90)';
        }
      } else {
        const t = (fv - minV) / den;
        const alpha = Math.max(0.15, Math.min(1.0, t));
        color = fv >= 0
          ? `rgba(70,170,255,${alpha.toFixed(3)})`
          : `rgba(255,100,100,${alpha.toFixed(3)})`;
      }
      return `<td title="${fv.toFixed(4)}" style="width:16px;height:16px;background:${color};border:1px solid #1e2534;"></td>`;
    }).join('')
  }</tr>`).join('');
  const uniformTag = isUniform ? ' [uniform channel]' : '';
  const uniformHint = isUniform
    ? `<div class="sub" style="margin:0 0 6px 0;">uniform value = ${minV.toFixed(4)} (rendered with high-contrast fill)</div>`
    : '';
  heatRoot.innerHTML = `
    <div class="sub" style="margin-bottom:6px;">snapshot=${snap.label} channel=${channel.name} min=${minV.toFixed(4)} max=${maxV.toFixed(4)}${uniformTag}</div>
    ${uniformHint}
    <table style="border-collapse:collapse;"><tbody>${rowsHtml}</tbody></table>
  `;
}

function renderMuzeroChannels(data, errorMsg=''){
  const summary = document.getElementById('muzeroChannelsSummary');
  const tb = document.querySelector('#muzeroChannelsTable tbody');
  const snapshotSel = document.getElementById('muzeroChannelSnapshotSelect');
  const channelSel = document.getElementById('muzeroChannelSelect');
  const showConst = document.getElementById('muzeroShowConstantChannels');
  if (!summary || !tb || !snapshotSel || !channelSel || !showConst) return;
  if (!data || errorMsg){
    latestMuzeroChannels = null;
    renderKV('muzeroChannelsSummary', [
      ['Status', errorMsg ? `Error: ${errorMsg}` : 'No channel data'],
      ['Hint', 'Run training with CNN encoder and reload run'],
    ]);
    snapshotSel.innerHTML = '';
    channelSel.innerHTML = '';
    tb.innerHTML = '<tr><td colspan="6" class="sub">No channel data.</td></tr>';
    const heatRoot = document.getElementById('muzeroChannelHeatmap');
    if (heatRoot) heatRoot.innerHTML = '<div class="sub">No heatmap data.</div>';
    return;
  }
  latestMuzeroChannels = data;
  const shape = data.shape || {};
  renderKV('muzeroChannelsSummary', [
    ['Encoder', String(data.encoder_type || '-')],
    ['Channels', String(Number(shape.channels || 0))],
    ['Height', String(Number(shape.height || 0))],
    ['Width', String(Number(shape.width || 0))],
  ]);
  const snapshots = data.snapshots || [];
  const firstSnapshot = snapshots[0] || {};
  const allRows = firstSnapshot.channels || data.channels || [];
  const rows = showConst.checked
    ? allRows
    : allRows.filter((r)=>!['turn_norm','done_flag'].includes(String(r.name || '')));
  snapshotSel.innerHTML = '';
  for (const s of snapshots){
    const o = document.createElement('option');
    o.value = String(s.label || '');
    o.textContent = String(s.label || '');
    snapshotSel.appendChild(o);
  }
  channelSel.innerHTML = '';
  for (const row of rows){
    const o = document.createElement('option');
    o.value = String(row.index);
    o.textContent = `${row.index} - ${row.name || '-'}`;
    channelSel.appendChild(o);
  }
  tb.innerHTML = '';
  if (!rows.length){
    tb.innerHTML = '<tr><td colspan="6" class="sub">No channels listed.</td></tr>';
    const heatRoot = document.getElementById('muzeroChannelHeatmap');
    if (heatRoot) heatRoot.innerHTML = '<div class="sub">No heatmap data.</div>';
    return;
  }
  for (const row of rows){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${Number(row.index || 0)}</td>
      <td>${row.name || '-'}</td>
      <td>${Number(row.nonzero_cells || 0)}</td>
      <td>${pct(Number(row.nonzero_ratio || 0))}</td>
      <td>${Number(row.mean_value || 0).toFixed(4)}</td>
      <td>${Number(row.max_value || 0).toFixed(4)}</td>
    `;
    tb.appendChild(tr);
  }
  _updateMuzeroChannelHeatmap();
}

function renderMuzeroXaiDecisions(data, errorMsg=''){
  const summary = document.getElementById('muzeroXaiSummary');
  const tb = document.querySelector('#muzeroXaiTable tbody');
  const dimTb = document.querySelector('#muzeroXaiDimTable tbody');
  const ownTb = document.querySelector('#muzeroXaiOwnershipTable tbody');
  const sideSel = document.getElementById('muzeroXaiSideSelect');
  const actionFilter = document.getElementById('muzeroXaiActionFilter');
  if (!summary || !tb || !dimTb || !ownTb || !sideSel || !actionFilter) return;
  if (!data || errorMsg){
    latestMuzeroXai = null;
    renderKV('muzeroXaiSummary', [['Status', errorMsg ? `Error: ${errorMsg}` : 'No XAI decision data']]);
    dimTb.innerHTML = '<tr><td colspan="6" class="sub">No latent correlation rows.</td></tr>';
    ownTb.innerHTML = '<tr><td colspan="4" class="sub">No ownership rows.</td></tr>';
    tb.innerHTML = '<tr><td colspan="10" class="sub">No XAI decision rows.</td></tr>';
    return;
  }
  latestMuzeroXai = data;
  const rows = Array.isArray(data.rows) ? data.rows : [];
  const side = String(sideSel.value || '').trim().toUpperCase();
  const term = String(actionFilter.value || '').trim().toUpperCase();
  const filtered = rows.filter((r)=>{
    if (side && String(r.to_play || '').toUpperCase() !== side) return false;
    if (term){
      const hay = `${r.action_id || ''} ${r.action_kind || ''}`.toUpperCase();
      if (!hay.includes(term)) return false;
    }
    return true;
  });
  const topProbAvg = filtered.length
    ? (filtered.reduce((acc, r)=>acc + Number(((r.policy_top_probs || [])[0] || 0)), 0) / filtered.length)
    : 0;
  const l2Avg = filtered.length
    ? (filtered.reduce((acc, r)=>acc + Number(r.latent_l2_norm || 0), 0) / filtered.length)
    : 0;
  const valueRootAvg = filtered.length
    ? (filtered.reduce((acc, r)=>acc + Number(r.predicted_value_root || 0), 0) / filtered.length)
    : 0;
  const dynRewardAvg = filtered.length
    ? (filtered.reduce((acc, r)=>acc + Number(r.dynamics_pred_reward || 0), 0) / filtered.length)
    : 0;
  const dynNextL2Avg = filtered.length
    ? (filtered.reduce((acc, r)=>acc + Number(r.dynamics_next_latent_l2 || 0), 0) / filtered.length)
    : 0;
  const dynDeltaL2Avg = filtered.length
    ? (filtered.reduce((acc, r)=>acc + Number(r.dynamics_delta_l2 || 0), 0) / filtered.length)
    : 0;
  const dimStats = new Map();
  for (const r of filtered){
    const dims = Array.isArray(r.latent_top_indices) ? r.latent_top_indices : [];
    const isAttack = !['', 'MOVE', 'WAIT', 'TIMEOUT'].includes(String(r.action_kind || '').toUpperCase());
    const vpCapture = Number(r.vp_captures || 0) > 0 ? 1 : 0;
    const topProb = Number(((r.policy_top_probs || [])[0] || 0));
    for (const dRaw of dims){
      const d = Number(dRaw);
      if (!Number.isFinite(d)) continue;
      if (!dimStats.has(d)){
        dimStats.set(d, {count: 0, attackCount: 0, vpCount: 0, topProbSum: 0});
      }
      const s = dimStats.get(d);
      s.count += 1;
      if (isAttack) s.attackCount += 1;
      if (vpCapture) s.vpCount += 1;
      s.topProbSum += topProb;
    }
  }
  const dimRows = Array.from(dimStats.entries()).map(([dim, s])=>({
    dim: Number(dim),
    count: Number(s.count || 0),
    support: filtered.length > 0 ? Number(s.count || 0) / filtered.length : 0,
    attackRate: Number(s.count || 0) > 0 ? Number(s.attackCount || 0) / Number(s.count || 1) : 0,
    vpCaptureRate: Number(s.count || 0) > 0 ? Number(s.vpCount || 0) / Number(s.count || 1) : 0,
    topProbAvg: Number(s.count || 0) > 0 ? Number(s.topProbSum || 0) / Number(s.count || 1) : 0,
  }));
  dimRows.sort((a,b)=>b.count-a.count);
  const dimExplainText = dimRows.length
    ? dimRows.slice(0, 5).map((r)=>`d${r.dim}: supp ${pct(r.support)}, atk ${pct(r.attackRate)}, vpCap ${pct(r.vpCaptureRate)}, pTop ${pct(r.topProbAvg)}`).join(' | ')
    : '-';
  const ownership = {
    total: 0,
    aligned: 0,
    overwritten: 0,
    bySide: {},
  };
  for (const r of filtered){
    const side = String(r.to_play || 'unknown').toUpperCase();
    const action = String(r.action_id || '');
    const topPolicy = String(((r.policy_top_actions || [])[0]) || '');
    const aligned = action && topPolicy && action === topPolicy;
    ownership.total += 1;
    if (aligned) ownership.aligned += 1;
    else ownership.overwritten += 1;
    if (!ownership.bySide[side]){
      ownership.bySide[side] = { total: 0, aligned: 0, overwritten: 0 };
    }
    ownership.bySide[side].total += 1;
    if (aligned) ownership.bySide[side].aligned += 1;
    else ownership.bySide[side].overwritten += 1;
  }
  summary.innerHTML = `
    <div id="muzeroXaiSummaryGrid">
      <div class="xai-card"><div class="k">Rows (loaded)</div><div class="v">${String(Number(data.count || rows.length || 0))}</div></div>
      <div class="xai-card"><div class="k">Rows (filtered)</div><div class="v">${String(filtered.length)}</div></div>
      <div class="xai-card"><div class="k">Representation L2 avg</div><div class="v">${Number(l2Avg || 0).toFixed(3)}</div></div>
      <div class="xai-card"><div class="k">Prediction Top-1 prob avg</div><div class="v">${pct(Number(topProbAvg || 0))}</div></div>
      <div class="xai-card"><div class="k">Prediction Value(root) avg</div><div class="v">${Number(valueRootAvg || 0).toFixed(4)}</div></div>
      <div class="xai-card"><div class="k">Dynamics Reward avg</div><div class="v">${Number(dynRewardAvg || 0).toFixed(4)}</div></div>
      <div class="xai-card"><div class="k">Dynamics Next L2 avg</div><div class="v">${Number(dynNextL2Avg || 0).toFixed(3)}</div></div>
      <div class="xai-card"><div class="k">Dynamics Delta L2 avg</div><div class="v">${Number(dynDeltaL2Avg || 0).toFixed(3)}</div></div>
    </div>
  `;
  dimTb.innerHTML = '';
  ownTb.innerHTML = '';
  tb.innerHTML = '';
  if (!filtered.length){
    dimTb.innerHTML = '<tr><td colspan="6" class="sub">No rows after filter.</td></tr>';
    ownTb.innerHTML = '<tr><td colspan="4" class="sub">No rows after filter.</td></tr>';
    tb.innerHTML = '<tr><td colspan="10" class="sub">No rows after filter.</td></tr>';
    return;
  }
  for (const r of dimRows.slice(0, 12)){
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>d${Number(r.dim || 0)}</td>
      <td>${pct(Number(r.support || 0))}</td>
      <td>${pct(Number(r.attackRate || 0))}</td>
      <td>${pct(Number(r.vpCaptureRate || 0))}</td>
      <td>${pct(Number(r.topProbAvg || 0))}</td>
      <td>${Number(r.count || 0)}</td>
    `;
    dimTb.appendChild(tr);
  }
  if (!dimTb.children.length){
    dimTb.innerHTML = '<tr><td colspan="6" class="sub">No latent dimension rows.</td></tr>';
  }
  const bySideRows = Object.entries(ownership.bySide).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
  for (const [sideName, s] of bySideRows){
    const t = Math.max(1, Number(s.total || 0));
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${sideName || '-'}</td>
      <td>${Number(s.total || 0)}</td>
      <td>${Number(s.aligned || 0)} (${pct(Number(s.aligned || 0) / t)})</td>
      <td>${Number(s.overwritten || 0)} (${pct(Number(s.overwritten || 0) / t)})</td>
    `;
    ownTb.appendChild(tr);
  }
  if (bySideRows.length){
    const totalAll = Number(ownership.total || 0);
    const alignedAll = Number(ownership.aligned || 0);
    const overwrittenAll = Number(ownership.overwritten || 0);
    const denomAll = Math.max(1, totalAll);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><b>TOTAL</b></td>
      <td><b>${totalAll}</b></td>
      <td><b>${alignedAll} (${pct(alignedAll / denomAll)})</b></td>
      <td><b>${overwrittenAll} (${pct(overwrittenAll / denomAll)})</b></td>
    `;
    ownTb.appendChild(tr);
  }
  if (!ownTb.children.length){
    ownTb.innerHTML = '<tr><td colspan="4" class="sub">No ownership rows.</td></tr>';
  }
  const maxRows = 300;
  for (const r of filtered.slice(-maxRows).reverse()){
    const tr = document.createElement('tr');
    const topA = String(((r.policy_top_actions || [])[0]) || '-');
    const topP = Number(((r.policy_top_probs || [])[0]) || 0);
    const dims = (Array.isArray(r.latent_top_indices) ? r.latent_top_indices : [])
      .slice(0, 5)
      .map((d)=>`d${Number(d)}`)
      .join(', ');
    tr.innerHTML = `
      <td>${Number(r.iteration || 0)}/${Number(r.episode || 0)}/${Number(r.step || 0)}</td>
      <td>${Number(r.game_turn || 0)}</td>
      <td>${r.to_play || '-'}</td>
      <td>${r.action_id || '-'}</td>
      <td>${topA}</td>
      <td>${pct(topP)}</td>
      <td>${Number(r.predicted_value_root || 0).toFixed(4)}</td>
      <td>${dims || '-'}</td>
      <td>${Number(r.dynamics_pred_reward || 0).toFixed(4)}</td>
      <td>p=${Number(r.chosen_action_prob || 0).toFixed(3)} | H=${Number(r.mcts_entropy || 0).toFixed(3)} | m=${Number(r.mcts_margin || 0).toFixed(3)}</td>
    `;
    tb.appendChild(tr);
  }
}

function _renderMuzeroXaiMapFrame(){
  const canvas = document.getElementById('muzeroXaiMapCanvas');
  const dimsCanvas = document.getElementById('muzeroXaiDimsCanvas');
  const resCanvas = document.getElementById('muzeroXaiResCanvas');
  const slider = document.getElementById('muzeroXaiMapStep');
  const label = document.getElementById('muzeroXaiMapStepLabel');
  const accum = document.getElementById('muzeroXaiMapAccumulate');
  const paletteSel = document.getElementById('muzeroXaiMapPalette');
  const sideModeSel = document.getElementById('muzeroXaiMapSideMode');
  if (!canvas || !slider || !label || !accum) return;
  const rows = Array.isArray((latestMuzeroXai || {}).rows) ? latestMuzeroXai.rows : [];
  const ctx = canvas.getContext('2d');
  if (!ctx){
    return;
  }
  const total = rows.length;
  const idx = Math.max(0, Math.min(total - 1, Number(slider.value || 0)));
  const palette = String((paletteSel && paletteSel.value) || 'neon');
  const sideMode = String((sideModeSel && sideModeSel.value) || 'blend');
  label.textContent = total ? `step ${idx + 1}/${total}` : 'step 0/0';
  ctx.fillStyle = '#0b0f18';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!total){
    return;
  }
  const runCfg = ((latestMuzeroRun || {}).manifest_config || {}).model || {};
  const w = Number(runCfg.observation_width || 32);
  const h = Number(runCfg.observation_height || 32);
  const start = accum.checked ? 0 : idx;
  const end = idx;
  const counts = new Map();
  const scenarioHexes = Array.isArray((latestMuzeroScenarioHexes || {}).hexes)
    ? latestMuzeroScenarioHexes.hexes
    : [];
  const getPlayableCellsFromChannels = ()=>{
    const snaps = Array.isArray((latestMuzeroChannels || {}).snapshots) ? latestMuzeroChannels.snapshots : [];
    const snap = snaps[0] || {};
    const channels = Array.isArray(snap.channels) ? snap.channels : [];
    const playable = channels.find((c)=>String(c.name || '') === 'map_playable' || Number(c.index) === 12);
    const vals = (playable && Array.isArray(playable.values)) ? playable.values : null;
    if (!vals || !vals.length) return [];
    const halfW = Math.floor(w / 2);
    const halfH = Math.floor(h / 2);
    const out = [];
    for (let y = 0; y < vals.length; y += 1){
      const row = Array.isArray(vals[y]) ? vals[y] : [];
      for (let x = 0; x < row.length; x += 1){
        if (Number(row[x] || 0) <= 0) continue;
        out.push({ q: x - halfW, r: y - halfH });
      }
    }
    return out;
  };
  const playableCellsFromChannels = getPlayableCellsFromChannels();
  const geometryCells = scenarioHexes.length
    ? scenarioHexes.map((h)=>({ q: Number(h.q), r: Number(h.r) }))
    : playableCellsFromChannels;
  const hexSet = new Set(geometryCells.map((h)=>`${Number(h.q)},${Number(h.r)}`));
  const addCell = (q, r, weight, sideTag)=>{
    const qn = Number(q);
    const rn = Number(r);
    if (!Number.isFinite(qn) || !Number.isFinite(rn)) return;
    if (hexSet.size > 0 && !hexSet.has(`${qn},${rn}`)) return;
    if (hexSet.size === 0 && (qn < 0 || rn < 0 || qn >= w || rn >= h)) return;
    const key = `${qn},${rn}`;
    const prev = counts.get(key) || { total: 0, it: 0, us: 0 };
    const next = {
      total: Number(prev.total || 0) + Number(weight || 0),
      it: Number(prev.it || 0),
      us: Number(prev.us || 0),
    };
    const s = String(sideTag || '').toUpperCase();
    if (s === 'IT') next.it += Number(weight || 0);
    if (s === 'US') next.us += Number(weight || 0);
    counts.set(key, next);
  };
  for (let i = start; i <= end; i += 1){
    const row = rows[i] || {};
    const sideTag = String(row.unit_side || row.to_play || '').toUpperCase();
    const aq = Number(row.acting_q || 0);
    const ar = Number(row.acting_r || 0);
    if ((aq !== 0 || ar !== 0)) addCell(aq, ar, 1.0, sideTag);
    const actionKind = String(row.action_kind || '').toUpperCase();
    const isAttack = !['', 'MOVE', 'WAIT', 'TIMEOUT'].includes(actionKind);
    if (isAttack){
      const hasTargetUnit = String(row.attack_target_unit_id || '').trim().length > 0;
      const tq = Number(row.target_q);
      const tr = Number(row.target_r);
      if (hasTargetUnit && Number.isFinite(tq) && Number.isFinite(tr)){
        addCell(tq, tr, 0.6, sideTag);
      }
    }
  }
  let maxV = 0;
  for (const v of counts.values()) maxV = Math.max(maxV, Number((v || {}).total || 0));
  const safeMax = Math.max(1e-9, maxV);
  const baseCells = geometryCells.length
    ? geometryCells
    : Array.from({ length: h }, (_, rr)=>
      Array.from({ length: w }, (_, qq)=>({ q: qq, r: rr }))
    ).flat();
  // Match assault_ai_ui projection: odd-r offset hex layout.
  const axialRaw = (q, r)=>({
    x: Math.sqrt(3) * (q + 0.5 * (r % 2)),
    y: 1.5 * r,
  });
  const raws = baseCells.map((c)=>axialRaw(Number(c.q), Number(c.r)));
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const p of raws){
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  const pad = 14;
  const spanX = Math.max(1e-9, maxX - minX);
  const spanY = Math.max(1e-9, maxY - minY);
  const scale = Math.min((canvas.width - 2 * pad) / spanX, (canvas.height - 2 * pad) / spanY);
  const offsetX = (canvas.width - spanX * scale) / 2;
  const offsetY = (canvas.height - spanY * scale) / 2;
  // Match assault_ai_ui geometry: center spacing uses HEX_SIZE as circumradius.
  // With odd-r offset projection, touching neighbors require radius ~= scale.
  const hexRadius = Math.max(2.5, scale);
  const hexPath = (cx, cy, rad) => {
    ctx.beginPath();
    for (let k = 0; k < 6; k += 1){
      const ang = (Math.PI / 180) * (60 * k - 30);
      const px = cx + rad * Math.cos(ang);
      const py = cy + rad * Math.sin(ang);
      if (k === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
  };
  const axialToPixel = (q, r) => {
    const raw = axialRaw(q, r);
    const px = offsetX + (raw.x - minX) * scale;
    const py = offsetY + (raw.y - minY) * scale;
    return { px, py };
  };
  for (const [key, payload] of counts.entries()){
    const [q, r] = key.split(',').map((n)=>Number(n));
    const totalVal = Number((payload || {}).total || 0);
    const itVal = Number((payload || {}).it || 0);
    const usVal = Number((payload || {}).us || 0);
    const t = totalVal / safeMax;
    const a = Math.max(0.12, Math.min(1.0, t));
    const { px, py } = axialToPixel(q, r);
    if (sideMode === 'single'){
      if (palette === 'heat') ctx.fillStyle = `rgba(255,${Math.round(120 + 80 * (1 - t))},40,${a.toFixed(3)})`;
      else if (palette === 'mono') ctx.fillStyle = `rgba(210,225,255,${a.toFixed(3)})`;
      else ctx.fillStyle = `rgba(255,80,80,${a.toFixed(3)})`;
    } else {
      const itFrac = totalVal > 0 ? itVal / totalVal : 0;
      const usFrac = totalVal > 0 ? usVal / totalVal : 0;
      const rCol = Math.round(235 * itFrac + 40 * usFrac);
      const gCol = Math.round(85 * itFrac + 180 * usFrac);
      const bCol = Math.round(70 * itFrac + 255 * usFrac);
      ctx.fillStyle = `rgba(${rCol},${gCol},${bCol},${a.toFixed(3)})`;
    }
    hexPath(px, py, hexRadius);
    ctx.fill();
  }
  ctx.strokeStyle = 'rgba(90,110,150,0.35)';
  ctx.lineWidth = 1;
  for (const c of baseCells){
    const { px, py } = axialToPixel(Number(c.q), Number(c.r));
    hexPath(px, py, hexRadius);
    ctx.stroke();
  }
  // Side legend
  ctx.fillStyle = 'rgba(220,230,255,0.92)';
  ctx.font = '12px Segoe UI, sans-serif';
  ctx.fillText('IT', 10, 18);
  ctx.fillStyle = 'rgba(235,85,70,0.95)';
  ctx.fillRect(30, 8, 16, 10);
  ctx.fillStyle = 'rgba(220,230,255,0.92)';
  ctx.fillText('US', 58, 18);
  ctx.fillStyle = 'rgba(40,180,255,0.95)';
  ctx.fillRect(82, 8, 16, 10);

  if (!dimsCanvas) return;
  const dctx = dimsCanvas.getContext('2d');
  if (!dctx) return;
  const dims = 96;
  const cols = Math.min(240, rows.length);
  const colStart = Math.max(0, idx - cols + 1);
  dctx.fillStyle = '#0b0f18';
  dctx.fillRect(0, 0, dimsCanvas.width, dimsCanvas.height);
  const cellW = dimsCanvas.width / Math.max(1, cols);
  const cellH = dimsCanvas.height / Math.max(1, dims);
  const heat = Array.from({ length: dims }, () => Array(cols).fill(0));
  let maxHeat = 0;
  for (let c = 0; c < cols; c += 1){
    const row = rows[colStart + c] || {};
    const idxs = Array.isArray(row.latent_top_indices) ? row.latent_top_indices : [];
    const vals = Array.isArray(row.latent_top_values) ? row.latent_top_values : [];
    for (let k = 0; k < idxs.length; k += 1){
      const d = Number(idxs[k]);
      const v = Math.abs(Number(vals[k] || 0));
      if (!Number.isFinite(d) || d < 0 || d >= dims) continue;
      heat[d][c] = v;
      if (v > maxHeat) maxHeat = v;
    }
  }
  const safeHeat = Math.max(1e-9, maxHeat);
  for (let d = 0; d < dims; d += 1){
    for (let c = 0; c < cols; c += 1){
      const t = heat[d][c] / safeHeat;
      if (t <= 0) continue;
      const a = Math.max(0.08, Math.min(0.95, t));
      if (palette === 'heat') dctx.fillStyle = `rgba(255,${Math.round(160 + 80 * (1 - t))},60,${a.toFixed(3)})`;
      else if (palette === 'mono') dctx.fillStyle = `rgba(210,225,255,${a.toFixed(3)})`;
      else dctx.fillStyle = `rgba(80,220,255,${a.toFixed(3)})`;
      dctx.fillRect(c * cellW, (dims - 1 - d) * cellH, cellW, cellH);
    }
  }
  const cursorCol = cols - 1;
  dctx.strokeStyle = 'rgba(255,200,80,0.9)';
  dctx.lineWidth = 2;
  dctx.beginPath();
  dctx.moveTo((cursorCol + 0.5) * cellW, 0);
  dctx.lineTo((cursorCol + 0.5) * cellW, dimsCanvas.height);
  dctx.stroke();

  if (!resCanvas) return;
  const rctx = resCanvas.getContext('2d');
  if (!rctx) return;
  rctx.fillStyle = '#0b0f18';
  rctx.fillRect(0, 0, resCanvas.width, resCanvas.height);
  if (!total) return;
  const rowNow = rows[idx] || {};
  const idxs = Array.isArray(rowNow.latent_top_indices) ? rowNow.latent_top_indices : [];
  const vals = Array.isArray(rowNow.latent_top_values) ? rowNow.latent_top_values : [];
  const cx = resCanvas.width / 2;
  const cy = resCanvas.height / 2;
  const maxR = Math.min(resCanvas.width, resCanvas.height) * 0.36;
  for (let k = 0; k < idxs.length; k += 1){
    const d = Number(idxs[k]);
    const v = Math.abs(Number(vals[k] || 0));
    if (!Number.isFinite(d) || !Number.isFinite(v)) continue;
    const ang = ((d % 96) / 96) * Math.PI * 2;
    const rad = maxR * (0.35 + (k / Math.max(1, idxs.length)) * 0.6);
    const x = cx + Math.cos(ang) * rad;
    const y = cy + Math.sin(ang) * rad;
    const rr = 16 + v * 240;
    const g = rctx.createRadialGradient(x, y, 0, x, y, rr);
    const alpha = Math.max(0.06, Math.min(0.65, 0.1 + v * 5.0));
    if (palette === 'heat'){
      g.addColorStop(0, `rgba(255,160,60,${alpha.toFixed(3)})`);
      g.addColorStop(1, 'rgba(255,160,60,0)');
    } else if (palette === 'mono'){
      g.addColorStop(0, `rgba(210,225,255,${alpha.toFixed(3)})`);
      g.addColorStop(1, 'rgba(210,225,255,0)');
    } else {
      g.addColorStop(0, `rgba(90,220,255,${alpha.toFixed(3)})`);
      g.addColorStop(1, 'rgba(90,220,255,0)');
    }
    rctx.fillStyle = g;
    rctx.beginPath();
    rctx.arc(x, y, rr, 0, Math.PI * 2);
    rctx.fill();
  }
  rctx.strokeStyle = 'rgba(120,150,220,0.22)';
  rctx.lineWidth = 1;
  rctx.beginPath();
  rctx.arc(cx, cy, maxR * 0.45, 0, Math.PI * 2);
  rctx.stroke();
  rctx.beginPath();
  rctx.arc(cx, cy, maxR * 0.75, 0, Math.PI * 2);
  rctx.stroke();
  rctx.fillStyle = 'rgba(190,210,255,0.9)';
  rctx.font = '12px Segoe UI, sans-serif';
  rctx.fillText(`step ${idx + 1}/${total}`, 12, 18);
}

function renderMuzeroXaiMap(data, errorMsg=''){
  const summary = document.getElementById('muzeroXaiMapSummary');
  const slider = document.getElementById('muzeroXaiMapStep');
  if (!summary || !slider) return;
  if (!data || errorMsg){
    renderKV('muzeroXaiMapSummary', [['Status', errorMsg ? `Error: ${errorMsg}` : 'No XAI map data']]);
    slider.min = '0';
    slider.max = '0';
    slider.value = '0';
    _renderMuzeroXaiMapFrame();
    return;
  }
  const rows = Array.isArray(data.rows) ? data.rows : [];
  const runCfg = ((latestMuzeroRun || {}).manifest_config || {}).model || {};
  const snaps = Array.isArray((latestMuzeroChannels || {}).snapshots) ? latestMuzeroChannels.snapshots : [];
  const snap = snaps[0] || {};
  const channels = Array.isArray(snap.channels) ? snap.channels : [];
  const playable = channels.find((c)=>String(c.name || '') === 'map_playable' || Number(c.index) === 12);
  const vals = (playable && Array.isArray(playable.values)) ? playable.values : null;
  let playableCount = 0;
  if (vals && vals.length){
    for (const row of vals){
      if (!Array.isArray(row)) continue;
      for (const v of row){
        if (Number(v || 0) > 0) playableCount += 1;
      }
    }
  }
  renderKV('muzeroXaiMapSummary', [
    ['Rows', String(rows.length)],
    ['Board tensor', `${Number(runCfg.observation_width || 32)}x${Number(runCfg.observation_height || 32)}`],
    ['Playable hexes', String(playableCount || Number(((latestMuzeroScenarioHexes || {}).hexes || []).length || 0))],
    ['Signal', 'acting unit = full weight, target = 0.6 weight'],
  ]);
  slider.min = '0';
  slider.max = String(Math.max(0, rows.length - 1));
  slider.value = String(Math.max(0, rows.length - 1));
  _renderMuzeroXaiMapFrame();
}

function _renderMuzeroReplayFrame(){
  const slider = document.getElementById('muzeroReplayStep');
  const label = document.getElementById('muzeroReplayStepLabel');
  const detailRoot = document.getElementById('muzeroReplayStepDetail');
  const tbody = document.querySelector('#muzeroReplayUnitsTable tbody');
  if (!slider || !label || !detailRoot || !tbody) return;
  const rows = Array.isArray((latestMuzeroReplay || {}).transitions) ? latestMuzeroReplay.transitions : [];
  const total = rows.length;
  const idx = Math.max(0, Math.min(Math.max(0, total - 1), Number(slider.value || 0)));
  label.textContent = `step ${total ? idx + 1 : 0}/${total}`;
  tbody.innerHTML = '';
  if (!total){
    renderKV('muzeroReplayStepDetail', [['Status', 'No replay loaded']]);
    return;
  }
  const row = rows[idx] || {};
  renderKV('muzeroReplayStepDetail', [
    ['Turn', String(row.turn || 0)],
    ['Side', String(row.to_play || '-')],
    ['Action', String(row.action_id || '-')],
    ['Reward', Number(row.reward || 0).toFixed(3)],
    ['Done', (row.done ? 'Yes' : 'No')],
  ]);
  const units = Array.isArray(row.units) ? row.units.slice() : [];
  units.sort((a,b)=>{
    const sa = String((a || {}).side || '');
    const sb = String((b || {}).side || '');
    if (sa !== sb) return sa.localeCompare(sb);
    return String((a || {}).unit_id || '').localeCompare(String((b || {}).unit_id || ''));
  });
  for (const u of units){
    const tr = document.createElement('tr');
    const side = String((u || {}).side || '');
    const unitId = String((u || {}).unit_id || '-');
    const unitLabel = String((u || {}).unit_label || (u || {}).unit_id || '');
    const hex = `${Number((u || {}).q || 0)},${Number((u || {}).r || 0)}`;
    const hp = Number((u || {}).hp || 0);
    const alive = Boolean((u || {}).alive);
    tr.innerHTML = `<td>${side}</td><td>${unitId}</td><td>${unitLabel}</td><td>${hex}</td><td>${hp}</td><td>${alive ? 'yes' : 'no'}</td>`;
    tbody.appendChild(tr);
  }
  _renderMuzeroReplayMap(row, units);
}

function _renderMuzeroReplayMap(stepRow, units){
  const canvas = document.getElementById('muzeroReplayMapCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = '#0b0f18';
  ctx.fillRect(0, 0, w, h);
  const hexes = Array.isArray((latestMuzeroScenarioHexes || {}).hexes) ? latestMuzeroScenarioHexes.hexes : [];
  const points = [];
  muzeroReplayHexOverlay = [];
  for (const h0 of hexes){
    const q = Number((h0 || {}).q);
    const r = Number((h0 || {}).r);
    if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
    points.push({ q, r });
  }
  for (const u of units){
    const q = Number((u || {}).q);
    const r = Number((u || {}).r);
    if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
    points.push({ q, r });
  }
  if (!points.length){
    ctx.fillStyle = 'rgba(190,210,255,0.85)';
    ctx.font = '14px Segoe UI, sans-serif';
    ctx.fillText('No map coordinates available', 14, 22);
    return;
  }
  let minQ = 0, maxQ = 0, minR = 0, maxR = 0;
  for (const p of points){
    minQ = Math.min(minQ, p.q);
    maxQ = Math.max(maxQ, p.q);
    minR = Math.min(minR, p.r);
    maxR = Math.max(maxR, p.r);
  }
  const spanQ = Math.max(1, maxQ - minQ + 1);
  const spanR = Math.max(1, maxR - minR + 1);
  const margin = 30;
  const sizeByW = (w - margin * 2) / (Math.sqrt(3) * (spanQ + spanR * 0.5) + 2);
  const sizeByH = (h - margin * 2) / (1.5 * spanR + 2);
  const size = Math.max(8, Math.min(28, sizeByW, sizeByH));
  const ox = margin + size * 1.8;
  const oy = margin + size * 1.8;
  const toXY = (q, r) => {
    const qq = q - minQ;
    const rr = r - minR;
    const x = ox + size * Math.sqrt(3) * (qq + rr / 2);
    const y = oy + size * 1.5 * rr;
    return [x, y];
  };
    const moveByHex = (latestMuzeroScenarioHexes || {}).terrain_move_cost_by_hex || {};
    const coverByHex = (latestMuzeroScenarioHexes || {}).terrain_cover_by_hex || {};
    const losByHex = (latestMuzeroScenarioHexes || {}).terrain_los_block_by_hex || {};
    const vpSet = new Set(
      Array.isArray((latestMuzeroScenarioHexes || {}).vp_hexes)
        ? latestMuzeroScenarioHexes.vp_hexes.map((v)=>`${Number(v.q)},${Number(v.r)}`)
        : []
    );
    const drawHex = (x, y, radius, stroke, fill) => {
    ctx.beginPath();
    for (let i = 0; i < 6; i += 1){
      const a = (Math.PI / 180) * (60 * i - 30);
      const px = x + radius * Math.cos(a);
      const py = y + radius * Math.sin(a);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1;
    ctx.stroke();
  };
  if (hexes.length){
    for (const hx of hexes){
      const q = Number((hx || {}).q);
      const r = Number((hx || {}).r);
      if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
      const [x, y] = toXY(q, r);
        const key = `${q},${r}`;
        const move = Number(moveByHex[key] || 1.0);
        const cover = Number(coverByHex[key] || 0.0);
        const los = Number(losByHex[key] || 0);
        const vp = vpSet.has(key);
        const moveTint = Math.max(0, Math.min(1, (move - 1.0) / 2.0));
        const baseR = Math.round(45 + 95 * moveTint);
        const baseG = Math.round(64 + 70 * (1 - moveTint));
        const baseB = Math.round(88 + 45 * (1 - moveTint));
        const coverAlpha = Math.max(0.08, Math.min(0.55, cover * 0.9));
        const fill = `rgba(${baseR},${baseG},${baseB},${Math.max(0.25, 0.25 + coverAlpha).toFixed(3)})`;
        const stroke = los > 0 ? 'rgba(255,180,90,0.95)' : (vp ? 'rgba(220,240,120,0.95)' : 'rgba(110,130,170,0.65)');
        drawHex(x, y, size * 0.92, stroke, fill);
        muzeroReplayHexOverlay.push({
          q, r, x, y, radius: size * 0.92, move, cover, los, vp,
        });
        if (vp){
          ctx.fillStyle = 'rgba(220,240,120,0.9)';
          ctx.beginPath();
          ctx.arc(x, y, Math.max(2, size * 0.14), 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = 'rgba(240,250,150,0.98)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(x, y, Math.max(5, size * 0.42), 0, Math.PI * 2);
          ctx.stroke();
          ctx.fillStyle = 'rgba(245,250,170,0.96)';
          ctx.font = `${Math.max(8, Math.round(size * 0.32))}px Segoe UI, sans-serif`;
          ctx.fillText('VP', x - size * 0.22, y - size * 0.52);
        }
        if (los > 0){
          ctx.fillStyle = 'rgba(255,195,120,0.92)';
          ctx.font = `${Math.max(8, Math.round(size * 0.38))}px Segoe UI, sans-serif`;
          ctx.fillText('L', x - size * 0.16, y + size * 0.12);
        }
    }
  }
  for (const u of units){
    const q = Number((u || {}).q);
    const r = Number((u || {}).r);
    if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
    const side = String((u || {}).side || '').toUpperCase();
    const alive = Boolean((u || {}).alive);
    const [x, y] = toXY(q, r);
    const base = side === 'US' ? '80,180,255' : '255,120,120';
    const alpha = alive ? 0.95 : 0.35;
    drawHex(x, y, size * 0.78, `rgba(${base},1.0)`, `rgba(${base},${alpha})`);
    ctx.fillStyle = 'rgba(8,12,20,0.95)';
    ctx.beginPath();
    ctx.arc(x, y, Math.max(3, size * 0.22), 0, Math.PI * 2);
    ctx.fill();
  }
  const action = String((stepRow || {}).action_id || '');
  ctx.fillStyle = 'rgba(190,210,255,0.9)';
  ctx.font = '13px Segoe UI, sans-serif';
  ctx.fillText(`Action: ${action || '-'}`, 12, h - 16);
  ctx.fillStyle = 'rgba(180,200,240,0.82)';
  ctx.font = '12px Segoe UI, sans-serif';
  ctx.fillText('Terrain: brighter=harder move | stronger fill=more cover | L=LOS block | dot=VP', 12, h - 34);
  ctx.fillStyle = 'rgba(170,190,230,0.78)';
  ctx.fillText('Grid origin: q=0,r=0 at top-left', 12, h - 50);
  if (muzeroReplayHoverHex){
    const hh = muzeroReplayHoverHex;
    const lines = [
      `hex ${hh.q},${hh.r}`,
      `move ${Number(hh.move || 0).toFixed(2)} | cover ${Number(hh.cover || 0).toFixed(2)} | los ${Number(hh.los || 0)}`,
      hh.vp ? 'VP hex' : 'non-VP',
    ];
    const bx = Math.max(8, Math.min(w - 260, Number(hh.x || 10) + 14));
    const by = Math.max(8, Math.min(h - 72, Number(hh.y || 10) - 14));
    ctx.fillStyle = 'rgba(12,18,30,0.92)';
    ctx.fillRect(bx, by, 252, 56);
    ctx.strokeStyle = 'rgba(120,150,220,0.75)';
    ctx.lineWidth = 1;
    ctx.strokeRect(bx, by, 252, 56);
    ctx.fillStyle = 'rgba(215,228,255,0.95)';
    ctx.font = '12px Segoe UI, sans-serif';
    ctx.fillText(lines[0], bx + 8, by + 16);
    ctx.fillText(lines[1], bx + 8, by + 32);
    ctx.fillText(lines[2], bx + 8, by + 48);
  }
}

function renderMuzeroReplay(data, errorMsg=''){
  const slider = document.getElementById('muzeroReplayStep');
  if (!slider) return;
  if (!data || errorMsg){
    latestMuzeroReplay = null;
    renderKV('muzeroReplaySummary', [['Status', errorMsg ? `Error: ${errorMsg}` : 'No replay data']]);
    slider.min = '0';
    slider.max = '0';
    slider.value = '0';
    _renderMuzeroReplayFrame();
    return;
  }
  latestMuzeroReplay = data;
  const rows = Array.isArray(data.transitions) ? data.transitions : [];
  const meta = (data.meta && typeof data.meta === 'object') ? data.meta : {};
  renderKV('muzeroReplaySummary', [
    ['Scenario', String(data.scenario_id || '-')],
    ['Seed', String(data.seed || 0)],
    ['Transitions', String(rows.length)],
    ['Run', String(meta.run_id || '-')],
    ['Iteration/Episode', `${String(meta.iteration ?? '-')}/${String(meta.episode ?? '-')}`],
    ['Action mismatches', String(meta.action_mismatch_count ?? 0)],
  ]);
  slider.min = '0';
  slider.max = String(Math.max(0, rows.length - 1));
  slider.value = String(Math.max(0, rows.length - 1));
  _renderMuzeroReplayFrame();
}

async function loadMuzeroReplayFromSelectedRun(){
  const sel = document.getElementById('muzeroRunSelect');
  const iterInput = document.getElementById('muzeroReplayIteration');
  const epInput = document.getElementById('muzeroReplayEpisode');
  if (!sel || !sel.value){
    renderMuzeroReplay(null, 'No run selected');
    return;
  }
  try {
    const iter = Number((iterInput && iterInput.value) || -1);
    const ep = Number((epInput && epInput.value) || -1);
    const qs = new URLSearchParams();
    qs.set('run_id', String(sel.value));
    if (Number.isFinite(iter) && iter >= 0) qs.set('iteration', String(Math.floor(iter)));
    if (Number.isFinite(ep) && ep >= 0) qs.set('episode', String(Math.floor(ep)));
    const data = await getJson('/api/muzero/timeline?' + qs.toString());
    renderMuzeroReplay(data);
  } catch (e) {
    renderMuzeroReplay(null, e.message || String(e));
  }
}

async function exportMuzeroReplayFromSelectedRun(){
  const sel = document.getElementById('muzeroRunSelect');
  const iterInput = document.getElementById('muzeroReplayIteration');
  const epInput = document.getElementById('muzeroReplayEpisode');
  const pathInput = document.getElementById('muzeroReplayPathInput');
  if (!sel || !sel.value){
    renderMuzeroReplay(null, 'No run selected');
    return;
  }
  try {
    const iter = Number((iterInput && iterInput.value) || -1);
    const ep = Number((epInput && epInput.value) || -1);
    const outPath = String((pathInput && pathInput.value) || '').trim();
    const payload = { run_id: String(sel.value) };
    if (Number.isFinite(iter) && iter >= 0) payload.iteration = Math.floor(iter);
    if (Number.isFinite(ep) && ep >= 0) payload.episode = Math.floor(ep);
    if (outPath) payload.out_path = outPath;
    const data = await postJson('/api/muzero/timeline_export', payload);
    if (pathInput && data.path_rel) pathInput.value = String(data.path_rel);
    renderMuzeroReplay(data.timeline || null, '');
  } catch (e) {
    renderMuzeroReplay(null, e.message || String(e));
  }
}

async function loadMuzeroReplayFromPath(){
  const input = document.getElementById('muzeroReplayPathInput');
  const path = String((input && input.value) || '').trim();
  if (!path){
    renderMuzeroReplay(null, 'Path is empty');
    return;
  }
  try {
    const data = await getJson('/api/muzero/timeline_file?path=' + encodeURIComponent(path));
    renderMuzeroReplay(data);
  } catch (e) {
    renderMuzeroReplay(null, e.message || String(e));
  }
}

async function loadMuzeroRuns(){
  const data = await getJson('/api/muzero/runs');
  muzeroRuns = data.runs || [];
  renderMuzeroRunsTable(muzeroRuns);
  const sel = document.getElementById('muzeroRunSelect');
  const topSel = document.getElementById('muzeroRunSelectTop');
  const prev = sel ? sel.value : '';
  const buildOptions = (target)=>{
    if (!target) return;
    target.innerHTML = '';
    for (const r of muzeroRuns){
      const o = document.createElement('option');
      o.value = r.run_id;
      o.textContent = r.run_id;
      target.appendChild(o);
    }
  };
  buildOptions(sel);
  buildOptions(topSel);
  const nextValue = (prev && muzeroRuns.some(r => r.run_id === prev))
    ? prev
    : String(data.latest_run_id || '');
  if (sel && nextValue) sel.value = nextValue;
  if (topSel && nextValue) topSel.value = nextValue;
}

async function loadMuzeroSelected(){
  const sel = document.getElementById('muzeroRunSelect');
  const topSel = document.getElementById('muzeroRunSelectTop');
  if (sel && topSel && topSel.value !== sel.value){
    topSel.value = sel.value;
  }
  if (!sel || !sel.value){
    renderMuzeroCards({}, {});
    renderMuzeroRunDetail(null);
    renderMuzeroUnitsSides(null, 'No run selected');
    renderMuzeroXaiDecisions(null, 'No run selected');
    renderMuzeroXaiMap(null, 'No run selected');
    renderMuzeroReplay(null, 'No run selected');
    latestMuzeroScenarioHexes = null;
    latestMuzeroScenarioRoles = null;
    return;
  }
  const run = await getJson('/api/muzero/run?run_id=' + encodeURIComponent(sel.value));
  latestMuzeroRun = run;
  renderMuzeroCards(run.metrics || {}, run.integrity || {});
  renderMuzeroRunDetail(run);
  try {
    const unitsides = await getJson('/api/muzero/unitsides?run_id=' + encodeURIComponent(sel.value));
    latestMuzeroUnitsSides = unitsides;
    renderMuzeroUnitsSides(unitsides);
    renderMuzeroGlobalActions(unitsides, run.metrics || {});
    renderMuzeroVps(unitsides);
    renderMuzeroStrategies(unitsides);
  } catch (e) {
    latestMuzeroUnitsSides = null;
    renderMuzeroUnitsSides(null, e.message || String(e));
    renderMuzeroGlobalActions(null, run.metrics || {});
    renderMuzeroVps(null);
    renderMuzeroStrategies(null);
  }
  try {
    const channels = await getJson('/api/muzero/channels?run_id=' + encodeURIComponent(sel.value));
    renderMuzeroChannels(channels);
  } catch (e) {
    renderMuzeroChannels(null, e.message || String(e));
  }
  try {
    const xai = await getJson('/api/muzero/xai_decisions?run_id=' + encodeURIComponent(sel.value) + '&limit=4000');
    renderMuzeroXaiDecisions(xai);
    renderMuzeroXaiMap(xai);
  } catch (e) {
    renderMuzeroXaiDecisions(null, e.message || String(e));
    renderMuzeroXaiMap(null, e.message || String(e));
  }
  try {
    latestMuzeroScenarioHexes = await getJson('/api/muzero/scenario_hexes?run_id=' + encodeURIComponent(sel.value));
    _renderMuzeroXaiMapFrame();
  } catch (e) {
    latestMuzeroScenarioHexes = null;
  }
  try {
    latestMuzeroScenarioRoles = await getJson('/api/muzero/scenario_roles?run_id=' + encodeURIComponent(sel.value));
  } catch (e) {
    latestMuzeroScenarioRoles = null;
  }
  await loadMuzeroReplayFromSelectedRun();
  if (latestMuzeroBench){
    renderMuzeroBenchDetail(latestMuzeroBench);
  }
  if (dashboardMode === 'muzero'){
    renderMuzeroTopCards(run.metrics || {}, run.integrity || {}, latestMuzeroBench || {});
  }
}

async function loadMuzeroBench(){
  const bench = await getJson('/api/muzero/bench_latest');
  latestMuzeroBench = bench;
  renderMuzeroBenchDetail(bench);
  if (dashboardMode === 'muzero'){
    const runMetrics = latestMuzeroRun ? (latestMuzeroRun.metrics || {}) : {};
    const runIntegrity = latestMuzeroRun ? (latestMuzeroRun.integrity || {}) : {};
    renderMuzeroTopCards(runMetrics, runIntegrity, bench || {});
  }
}

document.getElementById('reloadBtn').addEventListener('click', async ()=>{ await loadReports(true); await loadSelected(); });
document.getElementById('reportSelect').addEventListener('change', loadSelected);
document.getElementById('historyReloadBtn').addEventListener('click', loadHistory);
document.getElementById('historyExportBtn').addEventListener('click', exportHistoryCsv);
document.getElementById('controlRefreshBtn').addEventListener('click', renderControl);
document.getElementById('muzeroReloadBtn').addEventListener('click', async ()=>{ await loadMuzeroRuns(); await loadMuzeroSelected(); await loadMuzeroBench(); });
document.getElementById('muzeroRunSelect').addEventListener('change', loadMuzeroSelected);
document.getElementById('muzeroReloadBtnTop').addEventListener('click', async ()=>{
  await loadMuzeroRuns();
  await loadMuzeroSelected();
  await loadMuzeroBench();
});
document.getElementById('muzeroRunSelectTop').addEventListener('change', async (e)=>{
  const runId = String((e && e.target && e.target.value) || '');
  const sel = document.getElementById('muzeroRunSelect');
  if (sel && runId) sel.value = runId;
  await loadMuzeroSelected();
});
document.getElementById('muzeroChannelSnapshotSelect').addEventListener('change', _updateMuzeroChannelHeatmap);
document.getElementById('muzeroChannelSelect').addEventListener('change', _updateMuzeroChannelHeatmap);
document.getElementById('muzeroChannelRefreshBtn').addEventListener('click', _updateMuzeroChannelHeatmap);
document.getElementById('muzeroShowConstantChannels').addEventListener('change', ()=>{
  renderMuzeroChannels(latestMuzeroChannels);
});
document.getElementById('muzeroXaiApplyBtn').addEventListener('click', ()=>{
  renderMuzeroXaiDecisions(latestMuzeroXai);
});
document.getElementById('muzeroXaiSideSelect').addEventListener('change', ()=>{
  renderMuzeroXaiDecisions(latestMuzeroXai);
});
document.getElementById('muzeroXaiActionFilter').addEventListener('input', ()=>{
  renderMuzeroXaiDecisions(latestMuzeroXai);
});
document.getElementById('muzeroXaiMapStep').addEventListener('input', _renderMuzeroXaiMapFrame);
document.getElementById('muzeroXaiMapAccumulate').addEventListener('change', _renderMuzeroXaiMapFrame);
document.getElementById('muzeroXaiMapPalette').addEventListener('change', _renderMuzeroXaiMapFrame);
document.getElementById('muzeroXaiMapSideMode').addEventListener('change', _renderMuzeroXaiMapFrame);
document.getElementById('muzeroXaiMapSpeed').addEventListener('change', ()=>{
  const v = Number(document.getElementById('muzeroXaiMapSpeed').value || 180);
  if (!Number.isFinite(v)) document.getElementById('muzeroXaiMapSpeed').value = '180';
});
document.getElementById('muzeroXaiMapPlayBtn').addEventListener('click', ()=>{
  const slider = document.getElementById('muzeroXaiMapStep');
  const speedInput = document.getElementById('muzeroXaiMapSpeed');
  if (!slider) return;
  const intervalMs = Math.max(40, Math.min(2000, Number((speedInput && speedInput.value) || 180)));
  if (muzeroXaiMapTimer) clearInterval(muzeroXaiMapTimer);
  muzeroXaiMapTimer = setInterval(()=>{
    const maxV = Number(slider.max || 0);
    const curr = Number(slider.value || 0);
    slider.value = String(curr >= maxV ? 0 : curr + 1);
    _renderMuzeroXaiMapFrame();
  }, intervalMs);
});
document.getElementById('muzeroXaiMapPauseBtn').addEventListener('click', ()=>{
  if (muzeroXaiMapTimer){
    clearInterval(muzeroXaiMapTimer);
    muzeroXaiMapTimer = null;
  }
});
document.getElementById('muzeroReplayLoadRunBtn').addEventListener('click', loadMuzeroReplayFromSelectedRun);
document.getElementById('muzeroReplayExportBtn').addEventListener('click', exportMuzeroReplayFromSelectedRun);
document.getElementById('muzeroReplayLoadPathBtn').addEventListener('click', loadMuzeroReplayFromPath);
document.getElementById('muzeroReplayStep').addEventListener('input', _renderMuzeroReplayFrame);
document.getElementById('muzeroReplaySpeed').addEventListener('change', ()=>{
  const v = Number(document.getElementById('muzeroReplaySpeed').value || 220);
  if (!Number.isFinite(v)) document.getElementById('muzeroReplaySpeed').value = '220';
});
document.getElementById('muzeroReplayPlayBtn').addEventListener('click', ()=>{
  const slider = document.getElementById('muzeroReplayStep');
  const speedInput = document.getElementById('muzeroReplaySpeed');
  if (!slider) return;
  const intervalMs = Math.max(40, Math.min(2000, Number((speedInput && speedInput.value) || 220)));
  if (muzeroReplayTimer) clearInterval(muzeroReplayTimer);
  muzeroReplayTimer = setInterval(()=>{
    const maxV = Number(slider.max || 0);
    const curr = Number(slider.value || 0);
    slider.value = String(curr >= maxV ? 0 : curr + 1);
    _renderMuzeroReplayFrame();
  }, intervalMs);
});
document.getElementById('muzeroReplayPauseBtn').addEventListener('click', ()=>{
  if (muzeroReplayTimer){
    clearInterval(muzeroReplayTimer);
    muzeroReplayTimer = null;
  }
});
document.getElementById('muzeroReplayMapCanvas').addEventListener('mousemove', (e)=>{
  const canvas = document.getElementById('muzeroReplayMapCanvas');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const sx = canvas.width / Math.max(1, rect.width);
  const sy = canvas.height / Math.max(1, rect.height);
  const mx = (e.clientX - rect.left) * sx;
  const my = (e.clientY - rect.top) * sy;
  let best = null;
  let bestD = Number.POSITIVE_INFINITY;
  for (const h of muzeroReplayHexOverlay){
    const dx = mx - Number(h.x || 0);
    const dy = my - Number(h.y || 0);
    const d = Math.sqrt(dx * dx + dy * dy);
    if (d <= Number(h.radius || 0) && d < bestD){
      best = h;
      bestD = d;
    }
  }
  muzeroReplayHoverHex = best;
  _renderMuzeroReplayFrame();
});
document.getElementById('muzeroReplayMapCanvas').addEventListener('mouseleave', ()=>{
  muzeroReplayHoverHex = null;
  _renderMuzeroReplayFrame();
});
document.getElementById('muzeroGlobalActionsSort').addEventListener('change', ()=>{
  renderMuzeroGlobalActions(latestMuzeroUnitsSides, (latestMuzeroRun || {}).metrics || {});
});
document.getElementById('dashboardMode').addEventListener('change', async (e)=>{
  const mode = (e && e.target && e.target.value) || 'sb3';
  applyDashboardMode(mode);
  if (mode === 'sb3'){
    const sel = document.getElementById('reportSelect');
    if (sel) sel.innerHTML = '';
    await loadReports(true);
    await loadSelected();
  } else {
    await loadMuzeroRuns();
    await loadMuzeroSelected();
    await loadMuzeroBench();
  }
});
document.getElementById('controlLogCloseBtn').addEventListener('click', ()=>{
  const panel = document.getElementById('controlLogPanel');
  if (panel) panel.style.display = 'none';
});
setupTabs();
applyDashboardMode('sb3');

setInterval(renderControl, 10000);
(async ()=>{
  try { await loadReports(); } catch {}
  try { await loadSelected(); } catch {}
  try { await loadHistory(); } catch {}
  try { await renderControl(); } catch {}
  try { await loadMuzeroRuns(); } catch {}
  try { await loadMuzeroSelected(); } catch {}
  try { await loadMuzeroBench(); } catch {}
})();
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
            if parsed.path == "/api/muzero/runs":
                qs = parse_qs(parsed.query)
                limit_raw = (qs.get("limit") or ["50"])[0]
                try:
                    limit = max(1, min(200, int(limit_raw)))
                except Exception:
                    limit = 50
                runs = _list_muzero_runs(controller.repo_root, limit=limit)
                latest = ""
                for r in runs:
                    if bool(r.get("has_manifest")) and bool(r.get("has_metrics")) and bool(r.get("has_integrity")):
                        latest = str(r.get("run_id", ""))
                        break
                if not latest:
                    latest = runs[0]["run_id"] if runs else ""
                return self._json({"runs": runs, "latest_run_id": latest})
            if parsed.path == "/api/muzero/run":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    payload = _read_muzero_run(controller.repo_root, run_id)
                except ValueError:
                    return self._json({"error": "invalid run_id"}, status=400)
                except FileNotFoundError:
                    return self._json({"error": "run not found"}, status=404)
                return self._json(payload)
            if parsed.path == "/api/muzero/bench_latest":
                return self._json(_read_bench_latest(controller.repo_root))
            if parsed.path == "/api/muzero/unitsides":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    payload = _summarize_muzero_unitsides(controller.repo_root, run_id)
                except ValueError:
                    return self._json({"error": "invalid run_id"}, status=400)
                return self._json(payload)
            if parsed.path == "/api/muzero/channels":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    payload = _read_muzero_channels(controller.repo_root, run_id)
                except ValueError:
                    return self._json({"error": "invalid run_id"}, status=400)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, status=404)
                return self._json(payload)
            if parsed.path == "/api/muzero/xai_decisions":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                limit_raw = str((qs.get("limit") or ["2000"])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    limit = max(1, min(20000, int(limit_raw)))
                except Exception:
                    limit = 2000
                try:
                    payload = _read_muzero_xai_decisions(controller.repo_root, run_id, limit=limit)
                except ValueError:
                    return self._json({"error": "invalid run_id"}, status=400)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, status=404)
                return self._json(payload)
            if parsed.path == "/api/muzero/scenario_hexes":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    payload = _read_muzero_scenario_hexes(controller.repo_root, run_id)
                except ValueError:
                    return self._json({"error": "invalid run_id"}, status=400)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, status=404)
                except Exception as e:
                    return self._json({"error": f"failed loading scenario hexes: {e}"}, status=500)
                return self._json(payload)
            if parsed.path == "/api/muzero/scenario_roles":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    payload = _read_muzero_scenario_roles(controller.repo_root, run_id)
                except ValueError:
                    return self._json({"error": "invalid run_id"}, status=400)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, status=404)
                except Exception as e:
                    return self._json({"error": f"failed loading scenario roles: {e}"}, status=500)
                return self._json(payload)
            if parsed.path == "/api/muzero/timeline":
                qs = parse_qs(parsed.query)
                run_id = str((qs.get("run_id") or [""])[0]).strip()
                iteration_raw = str((qs.get("iteration") or [""])[0]).strip()
                episode_raw = str((qs.get("episode") or [""])[0]).strip()
                if not run_id:
                    return self._json({"error": "missing run_id"}, status=400)
                try:
                    iteration = int(iteration_raw) if iteration_raw else None
                    episode = int(episode_raw) if episode_raw else None
                    payload = _read_muzero_timeline(
                        controller.repo_root,
                        run_id,
                        iteration=iteration,
                        episode=episode,
                    )
                except ValueError as e:
                    return self._json({"error": str(e)}, status=400)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, status=404)
                except Exception as e:
                    return self._json({"error": f"failed loading timeline: {e}"}, status=500)
                return self._json(payload)
            if parsed.path == "/api/muzero/timeline_file":
                qs = parse_qs(parsed.query)
                rel_path = str((qs.get("path") or [""])[0]).strip()
                if not rel_path:
                    return self._json({"error": "missing path"}, status=400)
                try:
                    payload = _read_muzero_timeline_file(controller.repo_root, rel_path)
                except ValueError as e:
                    return self._json({"error": str(e)}, status=400)
                except FileNotFoundError as e:
                    return self._json({"error": str(e)}, status=404)
                except Exception as e:
                    return self._json({"error": f"failed loading timeline file: {e}"}, status=500)
                return self._json(payload)
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path not in {
                "/api/control/start",
                "/api/control/stop",
                "/api/control/restart",
                "/api/muzero/timeline_export",
            }:
                self.send_response(404)
                self.end_headers()
                return
            content_len = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                return self._json({"ok": False, "error": "invalid json payload"}, status=400)
            if parsed.path == "/api/muzero/timeline_export":
                run_id = str(payload.get("run_id", "")).strip()
                if not run_id:
                    return self._json({"ok": False, "error": "missing run_id"}, status=400)
                iteration_raw = payload.get("iteration", None)
                episode_raw = payload.get("episode", None)
                out_path = str(payload.get("out_path", "")).strip()
                try:
                    iteration = int(iteration_raw) if iteration_raw is not None else None
                    episode = int(episode_raw) if episode_raw is not None else None
                    res = _export_muzero_timeline_file(
                        repo_root=controller.repo_root,
                        run_id=run_id,
                        iteration=iteration,
                        episode=episode,
                        out_rel=out_path,
                    )
                except ValueError as e:
                    return self._json({"ok": False, "error": str(e)}, status=400)
                except FileNotFoundError as e:
                    return self._json({"ok": False, "error": str(e)}, status=404)
                except Exception as e:
                    return self._json({"ok": False, "error": f"timeline export failed: {e}"}, status=500)
                return self._json(res, status=200)
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

