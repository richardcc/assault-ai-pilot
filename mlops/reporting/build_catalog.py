from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _config_fingerprint(config: dict[str, Any]) -> str:
    payload = json.dumps(config or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _extract_run_id_from_checkpoint(path_s: str) -> str:
    raw = str(path_s or "").strip().replace("\\", "/")
    parts = [p for p in raw.split("/") if p]
    if not parts:
        return ""
    for idx, part in enumerate(parts):
        if part == "checkpoints" and idx > 0:
            return str(parts[idx - 1])
    for part in parts:
        if str(part).startswith("muzero_") or str(part).startswith("efficientzero_v2_"):
            return str(part)
    for idx, part in enumerate(parts):
        if part in {"runs", "runs_curriculum"} and idx + 1 < len(parts):
            return str(parts[idx + 1])
    return ""


def _policy_to_controller_label(policy_name: str) -> str:
    policy = str(policy_name or "").strip().lower()
    if policy == "mcts":
        return "MuZero"
    if policy == "random":
        return "Random"
    return "Unknown"


def _result_sides_from_decision_summary(result_row: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    summary = dict(result_row.get("eval_decision_summary", {}) or {})
    ownership_by_side = dict(summary.get("decision_ownership_by_side", {}) or {})
    for side in ownership_by_side.keys():
        key = str(side or "").strip().upper()
        if key:
            out.add(key)
    by_action_kind_and_side = dict(summary.get("by_action_kind_and_side", {}) or {})
    for row in by_action_kind_and_side.values():
        side = str((row or {}).get("unit_side", "")).strip().upper()
        if side:
            out.add(side)
    return out


def _normalize_result_controllers(result_row: dict[str, Any]) -> dict[str, Any]:
    out = dict(result_row or {})
    raw_policy_by_side = dict(out.get("policy_by_side", {}) or {})
    policy_by_side_norm = {
        str(side or "").strip().upper(): str(policy or "").strip().lower()
        for side, policy in raw_policy_by_side.items()
        if str(side or "").strip()
    }
    known_sides = _result_sides_from_decision_summary(out)
    if not known_sides:
        known_sides = set(policy_by_side_norm.keys())
    controller_by_side: dict[str, str] = {}
    legacy_unlabeled_count = 0
    for side in sorted(known_sides):
        policy_name = str(policy_by_side_norm.get(side, "")).strip()
        if not policy_name:
            controller_by_side[side] = "Legacy/Unlabeled"
            legacy_unlabeled_count += 1
            continue
        controller_by_side[side] = _policy_to_controller_label(policy_name)
    out["policy_by_side"] = policy_by_side_norm
    out["controller_by_side"] = controller_by_side
    out["controller_legacy_unlabeled_count"] = legacy_unlabeled_count
    return out


def _mlflow_commit_by_train_run(repo_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    mlruns = repo_root / "mlruns"
    if not mlruns.exists():
        return out
    for run_dir in mlruns.glob("*/*"):
        if not run_dir.is_dir():
            continue
        run_id_param = run_dir / "params" / "run_id"
        commit_tag = run_dir / "tags" / "mlflow.source.git.commit"
        if not run_id_param.exists():
            continue
        run_id = str(run_id_param.read_text(encoding="utf-8", errors="ignore").strip())
        if not run_id:
            continue
        commit = ""
        if commit_tag.exists():
            commit = str(commit_tag.read_text(encoding="utf-8", errors="ignore").strip())
        if commit:
            out[run_id] = commit
    return out


def _collect_agent_train_runs(
    repo_root: Path,
    runs_root_rel: str,
    *,
    run_prefix: str,
    engine: str,
    algorithm: str,
) -> list[dict[str, Any]]:
    runs_root = (repo_root / str(runs_root_rel)).resolve()
    out: list[dict[str, Any]] = []
    for rd in sorted(runs_root.glob(f"{run_prefix}*"), key=lambda p: p.stat().st_mtime):
        if not rd.is_dir():
            continue
        manifest_path = rd / "run_manifest.json"
        manifest = _read_json(manifest_path) if manifest_path.exists() else {}
        cfg = dict(manifest.get("config", {}) or {})
        checkpoint_dir = rd / "checkpoints"
        latest_checkpoint = ""
        if checkpoint_dir.exists():
            ckpts = sorted(checkpoint_dir.glob("iter_*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
            latest_checkpoint = str(ckpts[0]) if ckpts else ""
        resume_checkpoint = str(cfg.get("resume_checkpoint", "") or "")
        parent_run_id = _extract_run_id_from_checkpoint(resume_checkpoint)
        out.append(
            {
                "run_id": rd.name,
                "engine": engine,
                "algorithm": algorithm,
                "scenario_id": manifest.get("scenario_id"),
                "created_at_utc": _iso_from_mtime(rd),
                "config_fingerprint": _config_fingerprint(cfg),
                "config": cfg,
                "objective_reward_config": {
                    "objective_signal": dict(cfg.get("objective_signal", {}) or {}),
                    "objective_head": dict(cfg.get("objective_head", {}) or {}),
                    "objective_reporting": dict(cfg.get("objective_reporting", {}) or {}),
                    "reward_shaping": dict(
                        dict(cfg.get("selfplay", {}) or {}).get("reward_shaping", {}) or {}
                    ),
                    "preflight_warnings": list(cfg.get("config_preflight_warnings", []) or []),
                    "block_presence": {
                        "objective_signal": bool(dict(cfg.get("objective_signal", {}) or {})),
                        "objective_head": bool(dict(cfg.get("objective_head", {}) or {})),
                        "objective_reporting": bool(dict(cfg.get("objective_reporting", {}) or {})),
                        "selfplay_reward_shaping": bool(
                            dict(dict(cfg.get("selfplay", {}) or {}).get("reward_shaping", {}) or {})
                        ),
                    },
                },
                "resume_checkpoint": resume_checkpoint,
                "parent_run_id": parent_run_id,
                "is_retrain": bool(parent_run_id),
                "latest_checkpoint": latest_checkpoint,
                "metrics_summary_path": str(rd / "metrics" / "summary.json"),
            }
        )
    return out


def _collect_eval_history(repo_root: Path, runs_root_rel: str, train_run_id: str) -> list[dict[str, Any]]:
    xai_dir = (repo_root / str(runs_root_rel) / train_run_id / "xai").resolve()
    if not xai_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for p in sorted(xai_dir.glob("bench_eval_*.json"), key=lambda x: x.stat().st_mtime):
        payload = _read_json(p)
        diagnostics_eval = dict(payload.get("diagnostics_summary_eval", {}) or {})
        raw_results = list(payload.get("results", []) or [])
        normalized_results = [
            _normalize_result_controllers(dict(r or {}))
            for r in raw_results
            if isinstance(r, dict)
        ]
        rows.append(
            {
                "eval_id": p.stem.replace("bench_eval_", ""),
                "created_at_utc": _iso_from_mtime(p),
                "source_path": str(p),
                "scenario_id": payload.get("scenario_id"),
                "phase_2_9_promotion_gate": dict(payload.get("phase_2_9_promotion_gate", {}) or {}),
                "head_diagnostics_eval": dict(payload.get("head_diagnostics_eval", {}) or {}),
                "flow_traceability": {
                    "flow_source": "eval",
                    "flow_contract_version": "phase_2_9_eval_kpis.v1",
                    "flow_available": bool(diagnostics_eval),
                    "flow_fields": sorted(list(diagnostics_eval.keys())),
                },
                "diagnostics_summary_eval": diagnostics_eval,
                "results": normalized_results,
                "controller_legacy_unlabeled_rows": sum(
                    1 for r in normalized_results if int(r.get("controller_legacy_unlabeled_count", 0) or 0) > 0
                ),
            }
        )
    return rows


def _iter_runs_roots(runs_roots_rel: str | Iterable[str]) -> list[str]:
    if isinstance(runs_roots_rel, str):
        raw_items = [x.strip() for x in str(runs_roots_rel).split(",")]
    else:
        raw_items = [str(x).strip() for x in (runs_roots_rel or [])]
    out: list[str] = []
    for item in raw_items:
        if not item:
            continue
        if item not in out:
            out.append(item)
    return out


def build_reporting_catalog(
    repo_root: Path,
    runs_roots_rel: str | Iterable[str] = ("runs_curriculum", "runs"),
) -> dict[str, Any]:
    commit_by_train_run = _mlflow_commit_by_train_run(repo_root)
    run_roots = _iter_runs_roots(runs_roots_rel)
    train_runs: list[dict[str, Any]] = []
    for runs_root_rel in run_roots:
        train_runs.extend(
            _collect_agent_train_runs(
                repo_root,
                runs_root_rel=runs_root_rel,
                run_prefix="muzero_",
                engine="muzero",
                algorithm="muzero",
            )
        )
        train_runs.extend(
            _collect_agent_train_runs(
                repo_root,
                runs_root_rel=runs_root_rel,
                run_prefix="efficientzero_v2_",
                engine="efficientzero_v2",
                algorithm="efficientzero_v2",
            )
        )

    models_by_engine_and_fingerprint: dict[str, dict[str, dict[str, Any]]] = {}
    for tr in train_runs:
        engine = str(tr.get("engine", ""))
        algorithm = str(tr.get("algorithm", engine))
        fp = str(tr.get("config_fingerprint", ""))
        model_id = f"{engine}_{fp}"
        engine_bucket = models_by_engine_and_fingerprint.setdefault(engine, {})
        model_row = engine_bucket.setdefault(
            fp,
            {
                "model_id": model_id,
                "engine": engine,
                "algorithm": algorithm,
                "config_fingerprint": fp,
                "train_history": [],
                "eval_history": [],
            },
        )
        run_id = str(tr.get("run_id", ""))
        train_entry = {
            **tr,
            "git_commit": commit_by_train_run.get(run_id, ""),
        }
        model_row["train_history"].append(train_entry)
        model_row["eval_history"].extend(
            [
                {
                    **ev,
                    "train_run_id": run_id,
                    "git_commit": commit_by_train_run.get(run_id, ""),
                }
                for root_rel in run_roots
                for ev in _collect_eval_history(repo_root, runs_root_rel=root_rel, train_run_id=run_id)
            ]
        )

    for engine_models in models_by_engine_and_fingerprint.values():
        for model_row in engine_models.values():
            train_rows = list(model_row.get("train_history", []) or [])
            eval_rows = list(model_row.get("eval_history", []) or [])
            train_rows.sort(key=lambda r: str(r.get("created_at_utc", "")), reverse=True)
            eval_rows.sort(key=lambda r: str(r.get("created_at_utc", "")), reverse=True)
            scenario_train_counts: dict[str, int] = {}
            scenario_eval_counts: dict[str, int] = {}
            for tr in train_rows:
                sid = str(tr.get("scenario_id", "")).strip()
                if sid:
                    scenario_train_counts[sid] = scenario_train_counts.get(sid, 0) + 1
            for ev in eval_rows:
                sid = str(ev.get("scenario_id", "")).strip()
                if sid:
                    scenario_eval_counts[sid] = scenario_eval_counts.get(sid, 0) + 1
            scenarios_seen = sorted(set(list(scenario_train_counts.keys()) + list(scenario_eval_counts.keys())))
            model_row["train_history"] = train_rows
            model_row["eval_history"] = eval_rows
            model_row["scenarios_seen"] = scenarios_seen
            model_row["scenario_train_counts"] = scenario_train_counts
            model_row["scenario_eval_counts"] = scenario_eval_counts

    # Explicit engine buckets requested by user; keep placeholders ready.
    engines = []
    for engine_name in ["efficientzero_v2", "sb3", "muzero", "alpha"]:
        engine_models = sorted(
            list((models_by_engine_and_fingerprint.get(engine_name) or {}).values()),
            key=lambda m: m["model_id"],
        )
        engines.append(
            {
                "engine": engine_name,
                "models": engine_models,
            }
        )

    return {
        "schema_version": "reporting_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "runs_roots": run_roots,
        "engines": engines,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build curriculum reporting catalog.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path.",
    )
    parser.add_argument(
        "--out",
        default="runs_curriculum/experiments/reporting/model_catalog_latest.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--runs-root",
        default="runs_curriculum,runs",
        help="Runs roots relative to repo root (comma-separated).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    payload = build_reporting_catalog(repo_root=repo_root, runs_roots_rel=str(args.runs_root))
    out_path = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out_path), "schema_version": payload["schema_version"]}, indent=2))
