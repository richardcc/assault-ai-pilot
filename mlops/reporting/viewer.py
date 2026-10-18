from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from mlops.reporting.catalog_api import (
    build_publish_status_payload as _build_publish_status_payload,
    build_v2_catalog_payload as _build_v2_catalog_payload,
    build_v2_model_evals_payload as _build_v2_model_evals_payload,
    build_v2_model_payload as _build_v2_model_payload,
    build_v2_model_trains_payload as _build_v2_model_trains_payload,
)
from mlops.reporting.catalog_duckdb import load_catalog_summary_from_duckdb
from mlops.reporting.model_api import (
    build_train_summary_payload as _build_train_summary_payload,
)
from mlops.reporting.model_deletion import (
    delete_model_experiment as _delete_model_experiment,
)
from mlops.reporting.replay_api import (
    build_muzero_replay_payload as _build_muzero_replay_payload,
    build_replay_log_payload as _build_replay_log_payload,
    build_v2_replay_meta_payload as _build_v2_replay_meta_payload,
    build_v2_replay_steps_payload as _build_v2_replay_steps_payload,
)
from mlops.reporting.viewer_data_access import (
    load_elo_rows_from_duckdb as _load_elo_rows_from_duckdb,
    load_eval_history_page_from_parquet as _load_eval_history_page_from_parquet,
    load_model_detail_index_first as _load_model_detail_index_first,
    load_scenario_detail as _load_scenario_detail,
    load_scenario_overlay as _load_scenario_overlay,
    load_train_history_page_from_duckdb as _load_train_history_page_from_duckdb,
)
from mlops.reporting.viewer_elo_page import (
    elo_page_html as _elo_page_html,
)
from mlops.reporting.viewer_io import (
    json_bytes as _json_bytes,
    load_catalog_payload as _load_catalog_payload,
    read_catalog as _read_catalog,
)


def _model_html() -> str:
    path = Path(__file__).resolve().parent / "viewer_web" / "model.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

_TRACE_RUN_ID_RE = re.compile(r"run_id=(efficientzero_v2_[0-9a-f]+|muzero_[0-9a-f]+)")
_TRACE_RESUMED_FROM_RE = re.compile(r"resumed_from=(.+)")
_TRACE_CYCLE_RE = re.compile(r"^\d{8}_\d{6}_(.+)_(phase\d+_.+)$")


def _load_curriculum_traceability_payload(repo_root: Path, limit: int = 120) -> dict[str, Any]:
    trace_path = (repo_root / "runs_curriculum" / "experiments" / "reporting" / "curriculum_phase_traceability.jsonl").resolve()
    if not trace_path.exists():
        return {
            "schema_version": "curriculum_traceability.v1",
            "status": "missing",
            "rows": [],
            "path": str(trace_path),
        }
    rows: list[dict[str, Any]] = []
    try:
        lines = trace_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
        for line in lines[-max(1, int(limit)) :]:
            raw = str(line or "").strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except Exception as exc:
        return {
            "schema_version": "curriculum_traceability.v1",
            "status": "error",
            "error": str(exc),
            "rows": [],
            "path": str(trace_path),
        }

    cycles_root = (repo_root / "runs_curriculum" / "experiments" / "curriculum_cycles").resolve()
    if cycles_root.exists():
        for cycle_dir in sorted(cycles_root.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not cycle_dir.is_dir():
                continue
            status_path = cycle_dir / "meta" / "status.json"
            if status_path.exists():
                continue
            lock_path = cycle_dir / "meta" / "manifest.lock.json"
            if not lock_path.exists():
                continue
            lock = _read_catalog(lock_path)
            cycle_id = str((lock or {}).get("cycle_id", "") or cycle_dir.name)
            m = _TRACE_CYCLE_RE.match(cycle_id)
            if not m:
                continue
            curriculum_name = str(m.group(1) or "")
            phase_name = str(m.group(2) or "")
            train_log = cycle_dir / "logs" / "01_train.log"
            train_run_id = ""
            checkpoint_path = ""
            if train_log.exists():
                raw = train_log.read_text(encoding="utf-8", errors="ignore")
                run_ids = _TRACE_RUN_ID_RE.findall(raw)
                if run_ids:
                    train_run_id = str(run_ids[-1])
                resumed = _TRACE_RESUMED_FROM_RE.findall(raw)
                if resumed:
                    checkpoint_path = str(resumed[-1]).strip()
            if not train_run_id:
                continue
            already = any(str((r or {}).get("train_run_id", "")) == train_run_id for r in rows)
            if already:
                continue
            rows.append(
                {
                    "schema_version": "curriculum_traceability.v1",
                    "recorded_at_utc": str((lock or {}).get("created_at_utc", "") or ""),
                    "curriculum_name": curriculum_name,
                    "curriculum_version": "",
                    "phase_name": phase_name,
                    "phase_index": None,
                    "phase_started_at": str((lock or {}).get("created_at_utc", "") or ""),
                    "phase_finished_at": "",
                    "train_run_id": train_run_id,
                    "eval_run_id": "",
                    "checkpoint_path": checkpoint_path,
                    "scenario_mix_ids": [],
                    "scenario_mix_weights": [],
                    "matchup_profiles_enabled": [],
                    "seeds_hash": "",
                    "gate_spec_snapshot": {},
                    "gate_result_status": "IN_PROGRESS",
                    "gate_fail_reasons": [],
                    "promotion_decision": "pending",
                    "promotion_reason": "phase_running",
                    "baseline_reference": "",
                    "hard_gate_badge": "HARD GATE: IN_PROGRESS",
                    "diagnostic_status": "RUNNING",
                    "diagnostic_badge": "DIAGNOSTIC: RUNNING",
                    "diagnostic_warnings": [],
                    "diagnostic_metrics": {
                        "timeout_rate": None,
                        "non_timeout_resolution_rate": None,
                        "resolved_non_timeout_win_rate": None,
                    },
                    "gate_metrics": {},
                    "bench_payload_path": "",
                    "curriculum_yaml": "",
                    "event": "phase_in_progress",
                    "cycle_id": cycle_id,
                }
            )

    rows = sorted(rows, key=lambda r: str((r or {}).get("recorded_at_utc", "")), reverse=True)
    return {
        "schema_version": "curriculum_traceability.v1",
        "status": "ok",
        "rows": rows,
        "path": str(trace_path),
        "total": int(len(rows)),
    }


def _load_curriculum_compare_latest_payload(repo_root: Path, limit: int = 120) -> dict[str, Any]:
    report_dir = (repo_root / "runs_curriculum" / "experiments" / "reporting").resolve()
    if not report_dir.exists():
        return {"schema_version": "curriculum_compare_summary.v1", "status": "missing", "rows": []}
    files = sorted(report_dir.glob("curriculum_compare_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"schema_version": "curriculum_compare_summary.v1", "status": "missing", "rows": []}
    latest = files[0]
    rows: list[dict[str, str]] = []
    try:
        raw_bytes = latest.read_bytes()
        if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
            text = raw_bytes.decode("utf-16", errors="ignore")
        else:
            text = raw_bytes.decode("utf-8-sig", errors="ignore")
        for line in text.splitlines():
            raw = str(line or "").replace("\x00", "").strip()
            if not raw or raw.startswith("phase\tprofile\tagent\tmetric\tbaseline\tcandidate\tdelta") or raw.startswith("baseline="):
                continue
            parts = [p.replace("\x00", "").strip() for p in raw.split("\t")]
            if len(parts) != 7:
                continue
            rows.append(
                {
                    "phase": parts[0],
                    "profile": parts[1],
                    "agent": parts[2],
                    "metric": parts[3],
                    "baseline": parts[4],
                    "candidate": parts[5],
                    "delta": parts[6],
                }
            )
            if len(rows) >= max(1, int(limit)):
                break
    except Exception as exc:
        return {
            "schema_version": "curriculum_compare_summary.v1",
            "status": "error",
            "error": str(exc),
            "rows": [],
            "latest_path": str(latest),
        }
    return {
        "schema_version": "curriculum_compare_summary.v1",
        "status": "ok",
        "rows": rows,
        "latest_path": str(latest),
        "total_rows": int(len(rows)),
    }


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


def _read_channel_attribution_report(repo_root: Path, run_id: str) -> dict[str, Any]:
    cands = [
        (repo_root / "runs" / run_id / "metrics" / "channel_effectiveness_report.json").resolve(),
        (repo_root / "runs_curriculum" / run_id / "metrics" / "channel_effectiveness_report.json").resolve(),
    ]
    for c in cands:
        if c.exists():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["exists"] = True
                    return data
            except Exception:
                pass
    for m in repo_root.glob(f"runs*/**/{run_id}/metrics/channel_effectiveness_report.json"):
        if m.exists():
            try:
                data = json.loads(m.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["exists"] = True
                    return data
            except Exception:
                pass
    return {"exists": False}


def _run_channel_attribution_job(repo_root: Path, run_id: str) -> dict[str, Any]:
    import sys
    import importlib
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    import scripts.analyze_channel_attribution as aca
    importlib.reload(aca)
    _load_model = aca._load_model
    _collect_observations = aca._collect_observations
    analyze_channels = aca.analyze_channels

    found_rd = None
    cands = [
        (repo_root / "runs" / run_id).resolve(),
        (repo_root / "runs_curriculum" / run_id).resolve(),
    ]
    for c in cands:
        if c.exists() and c.is_dir():
            found_rd = c
            break
    if not found_rd:
        for m in repo_root.glob(f"runs*/{run_id}"):
            if m.is_dir():
                found_rd = m
                break
    if not found_rd:
        for m in repo_root.glob(f"runs*/**/{run_id}"):
            if m.is_dir():
                found_rd = m
                break
    if not found_rd:
        raise FileNotFoundError(f"Run directory not found for: {run_id}")

    manifest_path = found_rd / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    scenario_id = str(manifest.get("scenario_id") or "battaglia_cittadina_2_1")
    voec_cfg_path = (repo_root / "voec_sim" / "configs" / "voec_config.yaml").resolve()

    model = _load_model(found_rd)
    observations = _collect_observations(
        voec_config_path=voec_cfg_path,
        scenario_id=scenario_id,
        seeds=[42, 101, 202, 303],
        steps_per_seed=15,
        channels=getattr(model, "observation_channels", 32),
        height=getattr(model, "observation_height", 16),
        width=getattr(model, "observation_width", 16),
    )
    report = analyze_channels(model, observations, device="cpu")
    report["exists"] = True

    out_path = found_rd / "metrics" / "channel_effectiveness_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def serve(
    repo_root: Path,
    host: str,
    port: int,
    catalog_rel_path: str,
    dev_watch_paths: list[Path] | None = None,
) -> None:
    catalog_path = (repo_root / catalog_rel_path).resolve()
    if dev_watch_paths:
        t = threading.Thread(target=_watch_paths_and_exit, args=(dev_watch_paths, 1.0), daemon=True)
        t.start()

    react_root = (repo_root / "mlops" / "reporting" / "viewer_frontend" / "dist").resolve()
    legacy_root = (repo_root / "mlops" / "reporting" / "viewer_web").resolve()

    class Handler(BaseHTTPRequestHandler):
        def _send_bytes(self, body: bytes, content_type: str) -> None:
            try:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass

        def _send_json_status(self, payload: dict, status_code: int = 200) -> None:
            try:
                body = _json_bytes(payload)
                self.send_response(int(status_code))
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass

        def _content_type_for_path(self, path: Path) -> str:
            sfx = str(path.suffix or "").lower()
            if sfx == ".html":
                return "text/html; charset=utf-8"
            if sfx == ".css":
                return "text/css; charset=utf-8"
            if sfx == ".js":
                return "application/javascript; charset=utf-8"
            if sfx == ".json":
                return "application/json; charset=utf-8"
            if sfx == ".png":
                return "image/png"
            if sfx in [".jpg", ".jpeg"]:
                return "image/jpeg"
            if sfx == ".svg":
                return "image/svg+xml"
            if sfx in [".md", ".markdown"]:
                return "text/markdown; charset=utf-8"
            return "application/octet-stream"

        def _send_static_file(self, path: Path, root: Path) -> bool:
            try:
                p = path.resolve()
                r = root.resolve()
                if not str(p).lower().startswith(str(r).lower()):
                    return False
                if not p.exists() or not p.is_file():
                    return False
                self._send_bytes(p.read_bytes(), self._content_type_for_path(p))
                return True
            except Exception:
                return False

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)

            # React frontend (new default)
            if parsed.path == "/":
                self._send_static_file(react_root / "index.html", react_root)
                return
            if parsed.path == "/model":
                self._send_static_file(react_root / "index.html", react_root)
                return
            if parsed.path == "/docs":
                self.send_response(301)
                self.send_header("Location", "/docs/")
                self.end_headers()
                return
            if parsed.path.startswith("/docs/"):
                subpath = parsed.path[len("/docs/") :]
                site_root = (repo_root / "site").resolve()
                docs_root = (repo_root / "docs").resolve()
                preferred_root = site_root if (site_root / "index.html").exists() else docs_root

                if not subpath or subpath in ("index.html", ""):
                    target = preferred_root / "index.html"
                    if target.exists():
                        self._send_static_file(target, preferred_root)
                        return
                else:
                    rel_doc = unquote(subpath)
                    doc_target = (preferred_root / rel_doc).resolve()
                    if doc_target.is_dir():
                        if not parsed.path.endswith("/"):
                            self.send_response(301)
                            self.send_header("Location", parsed.path + "/")
                            self.end_headers()
                            return
                        doc_target = doc_target / "index.html"
                    if doc_target.exists() and doc_target.is_file():
                        self._send_static_file(doc_target, preferred_root)
                        return
                    alt_target = (docs_root / rel_doc).resolve()
                    if alt_target.is_dir():
                        if not parsed.path.endswith("/"):
                            self.send_response(301)
                            self.send_header("Location", parsed.path + "/")
                            self.end_headers()
                            return
                        alt_target = alt_target / "index.html"
                    if alt_target.exists() and alt_target.is_file():
                        self._send_static_file(alt_target, docs_root)
                        return
            if parsed.path.startswith("/assets/"):
                rel = unquote(parsed.path[len("/assets/") :])
                if self._send_static_file(react_root / "assets" / rel, react_root):
                    return
                site_root = (repo_root / "site").resolve()
                if self._send_static_file(site_root / "assets" / rel, site_root):
                    return
            if parsed.path.startswith("/art/"):
                rel = unquote(parsed.path[len("/art/") :])
                art_dist = (react_root / "art").resolve()
                art_src = (repo_root / "assault_ai_ui" / "public" / "art").resolve()
                if art_dist.exists() and self._send_static_file(art_dist / rel, art_dist):
                    return
                if art_src.exists() and self._send_static_file(art_src / rel, art_src):
                    return

            # Legacy fallback/reference
            if parsed.path == "/legacy":
                self._send_static_file(legacy_root / "index.html", legacy_root)
                return
            if parsed.path == "/legacy/model":
                self._send_static_file(legacy_root / "model.html", legacy_root)
                return
            if parsed.path.startswith("/legacy/assets/"):
                rel = parsed.path[len("/legacy/assets/") :]
                if self._send_static_file(legacy_root / rel, legacy_root):
                    return

            if parsed.path == "/elo":
                self._send_bytes(_elo_page_html().encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/v2/catalog":
                qs = parse_qs(parsed.query)
                rel = str(qs.get("path", [catalog_rel_path])[0] or catalog_rel_path)
                payload = _build_v2_catalog_payload(
                    repo_root=repo_root,
                    catalog_rel_path=catalog_rel_path,
                    requested_catalog_rel_path=rel,
                    load_catalog_summary_from_duckdb=load_catalog_summary_from_duckdb,
                )
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/publish-status":
                payload, status = _build_publish_status_payload(repo_root)
                self._send_json_status(payload, status_code=int(status))
                return
            if parsed.path == "/api/v2/curriculum-traceability":
                qs = parse_qs(parsed.query)
                limit = max(1, min(500, int(qs.get("limit", ["120"])[0] or 120)))
                payload = _load_curriculum_traceability_payload(repo_root=repo_root, limit=limit)
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/curriculum-compare-latest":
                qs = parse_qs(parsed.query)
                limit = max(1, min(1000, int(qs.get("limit", ["120"])[0] or 120)))
                payload = _load_curriculum_compare_latest_payload(repo_root=repo_root, limit=limit)
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/scenario":
                qs = parse_qs(parsed.query)
                sid = str(qs.get("id", [""])[0] or "").strip()
                payload = _load_scenario_detail(repo_root=repo_root, scenario_id=sid)
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/model":
                try:
                    qs = parse_qs(parsed.query)
                    out = _build_v2_model_payload(
                        repo_root=repo_root,
                        catalog_rel_path=catalog_rel_path,
                        engine=str(qs.get("engine", [""])[0] or ""),
                        model_id=str(qs.get("model", [""])[0] or ""),
                        train_limit=max(1, min(256, int(qs.get("train_limit", ["64"])[0] or 64))),
                        eval_limit=max(1, min(256, int(qs.get("eval_limit", ["64"])[0] or 64))),
                        load_model_detail_index_first=_load_model_detail_index_first,
                    )
                    self._send_bytes(_json_bytes(out if isinstance(out, dict) else {}), "application/json; charset=utf-8")
                except Exception as exc:
                    self._send_json_status({"ok": False, "error": "model_payload_failed", "message": str(exc)}, status_code=500)
                return
            if parsed.path == "/api/v2/model/evals":
                try:
                    qs = parse_qs(parsed.query)
                    include_payload_raw = str(qs.get("include_payload", ["0"])[0] or "0").strip().lower()
                    out = _build_v2_model_evals_payload(
                        repo_root=repo_root,
                        catalog_rel_path=catalog_rel_path,
                        engine=str(qs.get("engine", [""])[0] or ""),
                        model_id=str(qs.get("model", [""])[0] or ""),
                        offset=max(0, int(qs.get("offset", ["0"])[0] or 0)),
                        limit=max(1, min(200, int(qs.get("limit", ["20"])[0] or 20))),
                        train_run_id=str(qs.get("train_run_id", [""])[0] or ""),
                        scenario_id=str(qs.get("scenario_id", ["__all__"])[0] or "__all__"),
                        include_payload=include_payload_raw in {"1", "true", "yes", "on"},
                        load_eval_history_page_from_parquet=_load_eval_history_page_from_parquet,
                    )
                    self._send_bytes(_json_bytes(out), "application/json; charset=utf-8")
                except Exception as exc:
                    self._send_json_status({"ok": False, "error": "model_evals_payload_failed", "message": str(exc)}, status_code=500)
                return
            if parsed.path == "/api/v2/model/trains":
                try:
                    qs = parse_qs(parsed.query)
                    out = _build_v2_model_trains_payload(
                        repo_root=repo_root,
                        catalog_rel_path=catalog_rel_path,
                        engine=str(qs.get("engine", [""])[0] or ""),
                        model_id=str(qs.get("model", [""])[0] or ""),
                        offset=max(0, int(qs.get("offset", ["0"])[0] or 0)),
                        limit=max(1, min(200, int(qs.get("limit", ["20"])[0] or 20))),
                        load_train_history_page_from_duckdb=_load_train_history_page_from_duckdb,
                    )
                    self._send_bytes(_json_bytes(out), "application/json; charset=utf-8")
                except Exception as exc:
                    self._send_json_status({"ok": False, "error": "model_trains_payload_failed", "message": str(exc)}, status_code=500)
                return
            if parsed.path == "/api/v2/elo":
                qs = parse_qs(parsed.query)
                out = _load_elo_rows_from_duckdb(
                    repo_root=repo_root,
                    engine=str(qs.get("engine", [""])[0] or ""),
                    model_id=str(qs.get("model", ["__all__"])[0] or "__all__"),
                    side=str(qs.get("side", ["__all__"])[0] or "__all__"),
                    controller=str(qs.get("controller", ["__all__"])[0] or "__all__"),
                    scenario_id=str(qs.get("scenario_id", ["__all__"])[0] or "__all__"),
                    matchup_profile=str(qs.get("matchup_profile", ["__all__"])[0] or "__all__"),
                    eval_id_like=str(qs.get("eval_id_like", [""])[0] or ""),
                    created_at_like=str(qs.get("created_at_like", [""])[0] or ""),
                    limit=max(1, min(50000, int(qs.get("limit", ["20000"])[0] or 20000))),
                )
                self._send_bytes(_json_bytes(out), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/model/tactical-quality":
                from mlops.reporting.quality_metrics import compute_tactical_quality_metrics
                qs = parse_qs(parsed.query)
                engine = str(qs.get("engine", [""])[0] or "")
                model = str(qs.get("model", [qs.get("model_id", [""])[0] or ""])[0] or "")
                scenario = str(qs.get("scenario_id", ["__all__"])[0] or "__all__")
                phase = str(qs.get("curriculum_phase", ["__all__"])[0] or "__all__")
                eval_rows = _load_elo_rows_from_duckdb(
                    repo_root=repo_root,
                    engine=engine,
                    model_id=model if model else "__all__",
                    scenario_id=scenario,
                    limit=20000,
                )
                rows = eval_rows.get("rows", [])
                if phase != "__all__":
                    rows = [r for r in rows if str(r.get("curriculum_phase", "")).strip() == phase]
                quality = compute_tactical_quality_metrics(rows)
                self._send_bytes(_json_bytes(quality), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/train-summary":
                qs = parse_qs(parsed.query)
                run_id = str(qs.get("run_id", [""])[0] or "").strip()
                payload = _build_train_summary_payload(
                    repo_root=repo_root,
                    catalog_rel_path=catalog_rel_path,
                    run_id=run_id,
                    load_catalog_payload=_load_catalog_payload,
                )
                self._send_bytes(_json_bytes(payload if isinstance(payload, dict) else {}), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/muzero-replay":
                qs = parse_qs(parsed.query)
                payload = _build_muzero_replay_payload(
                    repo_root=repo_root,
                    eval_source_path=str(qs.get("eval_source_path", [""])[0] or ""),
                    replay_path=str(qs.get("replay_path", [""])[0] or ""),
                    episode_index=int(qs.get("episode_index", ["0"])[0] or 0),
                    full_episode=str(qs.get("full_episode", ["0"])[0] or "0").strip().lower() in {"1", "true", "yes", "on"},
                    chunk_offset=max(0, int(qs.get("chunk_offset", ["0"])[0] or 0)),
                    chunk_limit=max(1, int(qs.get("chunk_limit", ["80"])[0] or 80)),
                    load_scenario_overlay=_load_scenario_overlay,
                )
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/replay/meta":
                qs = parse_qs(parsed.query)
                eval_src = str(qs.get("eval_source_path", [""])[0] or qs.get("source_path", [""])[0] or "")
                payload = _build_v2_replay_meta_payload(
                    eval_src,
                    repo_root=repo_root,
                    load_scenario_overlay=_load_scenario_overlay,
                )
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/v2/replay/steps":
                qs = parse_qs(parsed.query)
                eval_src = str(qs.get("eval_source_path", [""])[0] or qs.get("source_path", [""])[0] or "")
                from_step = max(0, int(qs.get("from_step", ["0"])[0] or 0))
                payload = _build_v2_replay_steps_payload(
                    eval_source_path=eval_src,
                    episode_id=str(qs.get("episode_id", ["episode_0"])[0] or "episode_0"),
                    from_step=int(from_step),
                    to_step=max(from_step, int(qs.get("to_step", ["79"])[0] or 79)),
                    repo_root=repo_root,
                    load_scenario_overlay=_load_scenario_overlay,
                )
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/replay-log":
                qs = parse_qs(parsed.query)
                payload = _build_replay_log_payload(
                    eval_source_path=str(qs.get("eval_source_path", [""])[0] or ""),
                    replay_path=str(qs.get("replay_path", [""])[0] or ""),
                    episode_index=int(qs.get("episode_index", ["0"])[0] or 0),
                    upto_step=int(qs.get("upto_step", ["0"])[0] or 0),
                    full_episode_log=str(qs.get("full_episode_log", ["0"])[0] or "0").strip().lower() in {"1", "true", "yes", "on"},
                )
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            norm_path = parsed.path.rstrip("/")
            if norm_path == "/api/channel-attribution":
                qs = parse_qs(parsed.query)
                run_id = str(qs.get("run_id", [""])[0] or "").strip()
                payload = _read_channel_attribution_report(repo_root=repo_root, run_id=run_id)
                self._send_bytes(_json_bytes(payload), "application/json; charset=utf-8")
                return
            if norm_path == "/api/channel-attribution/run":
                qs = parse_qs(parsed.query)
                run_id = str(qs.get("run_id", [""])[0] or "").strip()
                if not run_id:
                    self._send_json_status({"ok": False, "error": "missing_run_id"}, status_code=400)
                    return
                try:
                    report = _run_channel_attribution_job(repo_root=repo_root, run_id=run_id)
                    self._send_json_status({"ok": True, "report": report}, status_code=200)
                except Exception as exc:
                    self._send_json_status({"ok": False, "error": str(exc)}, status_code=500)
                return
            self._send_json_status({"ok": False, "error": "not_found", "path": parsed.path}, status_code=404)

        def do_OPTIONS(self):  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            norm_path = parsed.path.rstrip("/")
            if norm_path == "/api/channel-attribution/run":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                    data = json.loads(body.decode("utf-8")) if body else {}
                    run_id = str(data.get("run_id") or "").strip()
                    if not run_id:
                        qs = parse_qs(parsed.query)
                        run_id = str(qs.get("run_id", [""])[0] or "").strip()
                    if not run_id:
                        self._send_json_status({"ok": False, "error": "missing_run_id"}, status_code=400)
                        return
                    report = _run_channel_attribution_job(repo_root=repo_root, run_id=run_id)
                    self._send_json_status({"ok": True, "report": report}, status_code=200)
                except Exception as exc:
                    self._send_json_status({"ok": False, "error": str(exc)}, status_code=500)
                return
            if norm_path == "/api/v2/delete-model":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                    data = json.loads(body.decode("utf-8")) if body else {}
                    model_id = str(data.get("model_id") or "").strip()
                    engine = str(data.get("engine") or "").strip()
                    if not model_id:
                        qs = parse_qs(parsed.query)
                        model_id = str(qs.get("model_id", [""])[0] or "").strip()
                        engine = str(qs.get("engine", [""])[0] or "").strip()
                    if not model_id:
                        self._send_json_status({"ok": False, "error": "missing_model_id"}, status_code=400)
                        return
                    result = _delete_model_experiment(repo_root=repo_root, model_id=model_id, engine=engine)
                    self._send_json_status(result, status_code=200)
                except Exception as exc:
                    self._send_json_status({"ok": False, "error": str(exc)}, status_code=500)
                return
            self._send_json_status({"ok": False, "error": "not_found", "path": parsed.path}, status_code=404)

        def log_message(self, format, *args):  # noqa: A003
            return

    import socket

    class DualStackServer(ThreadingHTTPServer):
        daemon_threads = True

        def server_bind(self):
            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except Exception:
                pass
            return super().server_bind()

        def handle_error(self, request, client_address):
            pass

    httpd = None
    if host in {"127.0.0.1", "localhost", "0.0.0.0", "", "::", "::1"}:
        try:
            DualStackServer.address_family = socket.AF_INET6
            httpd = DualStackServer(("::", port), Handler)
        except Exception:
            httpd = None

    if httpd is None:
        httpd = ThreadingHTTPServer((host, port), Handler)

    print(f"[ReportingViewer] http://127.0.0.1:{port} (and http://localhost:{port}) catalog={catalog_path} ui=react")
    print(f"[ReportingViewer] Legacy fallback: http://127.0.0.1:{port}/legacy")
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
        watch_paths = [(Path(args.repo_root).resolve() / "mlops" / "reporting")]
    serve(
        repo_root=Path(args.repo_root).resolve(),
        host=str(args.host),
        port=int(args.port),
        catalog_rel_path=str(args.catalog),
        dev_watch_paths=watch_paths,
    )
