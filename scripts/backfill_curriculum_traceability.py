from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


RUN_ID_RE = re.compile(r"run_id=(?P<run_id>efficientzero_v2_[0-9a-f]+|muzero_[0-9a-f]+)")
FINAL_CKPT_RE = re.compile(r"final_checkpoint=(?P<ckpt>[^\r\n]+)")
ITER_CKPT_RE = re.compile(r"\bcheckpoint=(?P<ckpt>[^\r\n]+)")
PHASE_RE = re.compile(r"^(?P<ts>\d{8}_\d{6})_(?P<curr>.+)_(?P<phase>phase\d+_.+)$")


def _read_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except Exception:
            pass
    try:
        return raw.decode("utf-8-sig")
    except Exception:
        return raw.decode("utf-8", errors="ignore")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(_read_text_auto(path))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sha1_12(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _parse_cycle_name(cycle_id: str) -> tuple[str, str]:
    m = PHASE_RE.match(str(cycle_id or ""))
    if not m:
        return "", ""
    return str(m.group("curr") or ""), str(m.group("phase") or "")


def _resolve_curriculum_yaml(repo_root: Path, curriculum_name: str) -> Path | None:
    if not curriculum_name:
        return None
    curriculums_dir = repo_root / "curriculums"
    if not curriculums_dir.exists():
        return None
    for y in curriculums_dir.glob("**/curriculum*.yaml"):
        try:
            payload = yaml.safe_load(y.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        name = str((payload or {}).get("name", "") or y.parent.name)
        if name == curriculum_name or y.parent.name == curriculum_name:
            return y
    return None


def _extract_train_info(train_log: Path, repo_root: Path) -> tuple[str, str]:
    if not train_log.exists():
        return "", ""
    raw = _read_text_auto(train_log)
    run_ids = RUN_ID_RE.findall(raw)
    run_id = str(run_ids[-1]) if run_ids else ""

    finals = FINAL_CKPT_RE.findall(raw)
    ckpt = str(finals[-1]).strip() if finals else ""
    if not ckpt:
        iters = ITER_CKPT_RE.findall(raw)
        ckpt = str(iters[-1]).strip() if iters else ""
    ckpt = ckpt.replace("/", "\\")
    if ckpt and not Path(ckpt).is_absolute():
        ckpt = str((repo_root / ckpt).resolve())
    return run_id, ckpt


def _extract_run_manifest_mix(repo_root: Path, train_run_id: str) -> tuple[list[str], list[float], list[str], dict[str, Any]]:
    if not train_run_id:
        return [], [], [], {}
    run_manifest = repo_root / "runs_curriculum" / train_run_id / "run_manifest.json"
    payload = _read_json(run_manifest)
    cfg = dict(payload.get("config", {}) or {})
    scenario_mix = dict(cfg.get("scenario_mix", {}) or {})
    ids = [str(x) for x in list(scenario_mix.get("ids", []) or []) if str(x).strip()]
    weights = [float(x) for x in list(scenario_mix.get("weights", []) or [])]
    if not ids:
        sid = str(payload.get("scenario_id", "") or "").strip()
        if sid:
            ids = [sid]
    matchup_modes = [str(x) for x in list(dict(cfg.get("selfplay", {}) or {}).get("matchup_modes", []) or []) if str(x).strip()]
    return ids, weights, matchup_modes, cfg


def _phase_index_and_gate(curriculum_yaml: Path | None, phase_name: str) -> tuple[int | None, dict[str, Any]]:
    if curriculum_yaml is None or not curriculum_yaml.exists():
        return None, {}
    try:
        payload = yaml.safe_load(curriculum_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return None, {}
    phases = list(payload.get("phases", []) or [])
    for idx, p in enumerate(phases):
        name = str((p or {}).get("name", "") or "")
        if name == phase_name:
            return idx + 1, dict((p or {}).get("gate", {}) or {})
    return None, {}


def backfill(repo_root: Path, *, merge_existing: bool = True) -> dict[str, Any]:
    cycles_root = repo_root / "runs_curriculum" / "experiments" / "curriculum_cycles"
    out_dir = repo_root / "runs_curriculum" / "experiments" / "reporting"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_dir / "curriculum_phase_traceability.jsonl"
    out_latest = out_dir / "curriculum_phase_traceability.latest.json"

    rows: list[dict[str, Any]] = []
    if merge_existing and out_jsonl.exists():
        for line in out_jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)

    existing_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        key = (
            str(r.get("curriculum_name", "")),
            str(r.get("phase_name", "")),
            str(r.get("phase_started_at", "")),
        )
        if key not in existing_by_key:
            existing_by_key[key] = r

    manifest_paths = sorted(cycles_root.glob("**/meta/manifest.lock.json"))
    added = 0
    for manifest_path in manifest_paths:
        meta_dir = manifest_path.parent
        cycle_dir = meta_dir.parent
        lock = _read_json(manifest_path)
        cycle_id = str(lock.get("cycle_id", "") or cycle_dir.name)
        curriculum_name, phase_name = _parse_cycle_name(cycle_id)
        if not curriculum_name or not phase_name:
            continue
        status = _read_json(meta_dir / "status.json")
        phase_started_at = str(lock.get("created_at_utc", "") or "")
        phase_finished_at = str(status.get("finished_at_utc", "") or "")
        row_key = (curriculum_name, phase_name, phase_started_at)
        train_log = Path(str(dict(status.get("logs", {}) or {}).get("train", "")))
        if not train_log.is_absolute():
            train_log = cycle_dir / "logs" / "01_train.log"
        train_run_id, checkpoint_path = _extract_train_info(train_log, repo_root)
        scenario_ids, scenario_weights, matchup_profiles, gate_metrics = _extract_run_manifest_mix(repo_root, train_run_id)

        curriculum_yaml = _resolve_curriculum_yaml(repo_root, curriculum_name)
        phase_index, gate_snapshot = _phase_index_and_gate(curriculum_yaml, phase_name)
        curriculum_version = ""
        if curriculum_yaml and curriculum_yaml.exists():
            curriculum_version = _sha1_12(curriculum_yaml.read_text(encoding="utf-8", errors="ignore"))

        gate_status = "UNKNOWN"
        phase_status = str(status.get("status", "") or "").lower()
        if phase_status == "failed":
            gate_status = "FAIL"
        promotion_decision = "rollback" if gate_status == "FAIL" else "hold"
        promotion_reason = "phase_execution_failed" if gate_status == "FAIL" else "backfilled_unknown_gate_result"

        row = {
            "schema_version": "curriculum_traceability.v1",
            "recorded_at_utc": phase_finished_at or phase_started_at,
            "curriculum_name": curriculum_name,
            "curriculum_version": curriculum_version,
            "phase_name": phase_name,
            "phase_index": phase_index,
            "phase_started_at": phase_started_at,
            "phase_finished_at": phase_finished_at,
            "train_run_id": train_run_id,
            "eval_run_id": "",
            "checkpoint_path": checkpoint_path,
            "scenario_mix_ids": scenario_ids,
            "scenario_mix_weights": scenario_weights,
            "matchup_profiles_enabled": matchup_profiles,
            "seeds_hash": "",
            "gate_spec_snapshot": gate_snapshot,
            "gate_result_status": gate_status,
            "gate_fail_reasons": [str(status.get("error", "")).strip()] if gate_status == "FAIL" and str(status.get("error", "")).strip() else [],
            "promotion_decision": promotion_decision,
            "promotion_reason": promotion_reason,
            "baseline_reference": "",
            "hard_gate_badge": f"HARD GATE: {gate_status}",
            "diagnostic_status": "UNKNOWN",
            "diagnostic_badge": "DIAGNOSTIC: UNKNOWN",
            "diagnostic_warnings": ["backfilled_from_cycle_logs"],
            "diagnostic_metrics": {
                "timeout_rate": None,
                "non_timeout_resolution_rate": None,
                "resolved_non_timeout_win_rate": None,
            },
            "gate_metrics": gate_metrics if isinstance(gate_metrics, dict) else {},
            "bench_payload_path": "",
            "curriculum_yaml": str(curriculum_yaml) if curriculum_yaml else "",
            "event": "phase_completed_backfill",
            "cycle_id": cycle_id,
        }

        existing = existing_by_key.get(row_key)
        if existing is None:
            rows.append(row)
            existing_by_key[row_key] = row
            added += 1
        else:
            # Rehydrate sparse legacy rows with fields recovered from logs/manifests.
            if not str(existing.get("train_run_id", "")).strip() and train_run_id:
                existing["train_run_id"] = train_run_id
            if not str(existing.get("checkpoint_path", "")).strip() and checkpoint_path:
                existing["checkpoint_path"] = checkpoint_path
            if (not list(existing.get("scenario_mix_ids", []) or [])) and scenario_ids:
                existing["scenario_mix_ids"] = scenario_ids
            if (not list(existing.get("scenario_mix_weights", []) or [])) and scenario_weights:
                existing["scenario_mix_weights"] = scenario_weights
            if (not list(existing.get("matchup_profiles_enabled", []) or [])) and matchup_profiles:
                existing["matchup_profiles_enabled"] = matchup_profiles
            if (not dict(existing.get("gate_spec_snapshot", {}) or {})) and gate_snapshot:
                existing["gate_spec_snapshot"] = gate_snapshot
            if not str(existing.get("curriculum_yaml", "")).strip() and curriculum_yaml:
                existing["curriculum_yaml"] = str(curriculum_yaml)
            if not str(existing.get("curriculum_version", "")).strip() and curriculum_version:
                existing["curriculum_version"] = curriculum_version
            if not str(existing.get("recorded_at_utc", "")).strip():
                existing["recorded_at_utc"] = phase_finished_at or phase_started_at
            if not str(existing.get("phase_finished_at", "")).strip() and phase_finished_at:
                existing["phase_finished_at"] = phase_finished_at

    rows.sort(key=lambda r: str(r.get("recorded_at_utc", "")))
    out_jsonl.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    latest = rows[-1] if rows else {}
    out_latest.write_text(json.dumps(latest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "rows_total": len(rows), "rows_added": added, "out": str(out_jsonl)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill curriculum phase traceability JSONL from cycle artifacts.")
    ap.add_argument("--repo-root", default=".", help="Repository root path.")
    ap.add_argument("--no-merge", action="store_true", help="Do not merge with existing JSONL; rebuild from discovered cycles only.")
    args = ap.parse_args()
    result = backfill(Path(args.repo_root).resolve(), merge_existing=not bool(args.no_merge))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

