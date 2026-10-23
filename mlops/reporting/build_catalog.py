from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from mlops.contracts_v2 import SCHEMA_VERSION_V2
from mlops.reporting.viewer_data_access import _compact_eval_results


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


def _extract_curriculum_phase_from_text(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    # Accept names like phase1, phase1_bootstrap, phase2_mix_70_30, etc.
    import re

    m = re.search(r"(phase\d+(?:_[a-z0-9]+(?:_[a-z0-9]+)*)?)", text)
    if not m:
        return ""
    return str(m.group(1) or "").strip().lower()


def _infer_curriculum_phase(cfg: dict[str, Any], run_id: str) -> str:
    config = dict(cfg or {})
    candidates: list[Any] = [
        config.get("curriculum_phase"),
        config.get("phase"),
        dict(config.get("curriculum", {}) or {}).get("phase"),
        config.get("phase_name"),
        config.get("base_config"),
        config.get("config_path"),
        config.get("config_name"),
        run_id,
    ]
    for candidate in candidates:
        phase = _extract_curriculum_phase_from_text(candidate)
        if phase:
            return phase
    return ""


def _policy_to_controller_label(policy_name: str) -> str:
    policy = str(policy_name or "").strip().lower()
    if policy in {"mcts", "efficientzero", "efficientzero_v2", "ezv2"}:
        return "EfficientZeroV2"
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
    unknown_controller_label_count = 0
    for side in sorted(known_sides):
        policy_name = str(policy_by_side_norm.get(side, "")).strip().lower()
        if not policy_name:
            if side == "IT" and "GE" in policy_by_side_norm:
                policy_name = str(policy_by_side_norm["GE"]).strip().lower()
            elif side == "GE" and "IT" in policy_by_side_norm:
                policy_name = str(policy_by_side_norm["IT"]).strip().lower()

        if not policy_name:
            controller_by_side[side] = "Unknown"
            unknown_controller_label_count += 1
            continue
        controller_by_side[side] = _policy_to_controller_label(policy_name)
    out["policy_by_side"] = policy_by_side_norm
    out["controller_by_side"] = controller_by_side
    out["controller_unknown_label_count"] = unknown_controller_label_count
    return out


def _filter_default_matchups(results: list[dict[str, Any]], *, include_random_selfplay: bool) -> list[dict[str, Any]]:
    if include_random_selfplay:
        return list(results or [])
    return [r for r in (results or []) if str((r or {}).get("matchup_profile", "")).strip() != "random_selfplay"]


def _prune_result_for_catalog(result_row: dict[str, Any], *, include_eval_payload_details: bool) -> dict[str, Any]:
    out = dict(result_row or {})
    # Heavy per-step/per-candidate payloads belong to replay/eval artifacts, not the catalog listing.
    out.pop("eval_decision_steps_top", None)
    out.pop("eval_decisions_top", None)
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
    include_run_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    runs_root = (repo_root / str(runs_root_rel)).resolve()
    out: list[dict[str, Any]] = []
    for rd in sorted(runs_root.glob(f"{run_prefix}*"), key=lambda p: p.stat().st_mtime):
        if not rd.is_dir():
            continue
        if include_run_ids is not None and rd.name not in include_run_ids:
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
        curriculum_phase = _infer_curriculum_phase(cfg, rd.name)
        scenario_mix = dict(cfg.get("scenario_mix", {}) or {})
        scenario_cfg = dict(cfg.get("scenario", {}) or {})
        scenario_ids = [
            str(x or "").strip()
            for x in list(scenario_cfg.get("ids", scenario_mix.get("ids", [])) or [])
            if str(x or "").strip()
        ]
        if not scenario_ids:
            single_sid = str(manifest.get("scenario_id", "") or "").strip()
            if single_sid:
                scenario_ids = [single_sid]
        scenario_id_value = (
            f"multi:{'|'.join(scenario_ids)}"
            if len(scenario_ids) > 1
            else (scenario_ids[0] if scenario_ids else "")
        )
        out.append(
            {
                "run_id": rd.name,
                "engine": engine,
                "algorithm": algorithm,
                "scenario_id": scenario_id_value,
                "scenario_ids": list(scenario_ids),
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
                    "preflight_warnings": [
                        w for w in list(cfg.get("config_preflight_warnings", []) or [])
                        if not (w == "missing.train.objective_signal" and bool(dict(cfg.get("objective_signal", {}) or {})))
                        and not (w == "missing.train.objective_head" and bool(dict(cfg.get("objective_head", {}) or {})))
                        and not (w == "missing.train.objective_reporting" and bool(dict(cfg.get("objective_reporting", {}) or {})))
                        and not (w == "missing.selfplay.reward_shaping" and bool(dict(dict(cfg.get("selfplay", {}) or {}).get("reward_shaping", {}) or {})))
                    ],
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
                "curriculum_phase": str(curriculum_phase or ""),
                "latest_checkpoint": latest_checkpoint,
                "metrics_summary_path": str(rd / "metrics" / "summary.json"),
            }
        )
    return out


def _collect_eval_history(
    repo_root: Path,
    runs_root_rel: str,
    train_run_id: str,
    *,
    include_random_selfplay: bool = False,
    include_eval_payload_details: bool = True,
) -> list[dict[str, Any]]:
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
        filtered_results = _filter_default_matchups(
            normalized_results,
            include_random_selfplay=include_random_selfplay,
        )
        filtered_results = [
            _prune_result_for_catalog(r, include_eval_payload_details=include_eval_payload_details)
            for r in filtered_results
        ]
        payload_scenario_id = str(payload.get("scenario_id", "") or "").strip()
        payload_is_multi = payload_scenario_id.startswith("multi:")
        scenario_ids_seen: set[str] = set()
        missing_seed_scenario_count = 0
        for rr in filtered_results:
            seed_games = list(dict(rr or {}).get("seed_games", []) or [])
            for sg in seed_games:
                sid = str(dict(sg or {}).get("scenario_id", "") or "").strip()
                if sid:
                    scenario_ids_seen.add(sid)
                elif payload_is_multi:
                    missing_seed_scenario_count += 1
        if payload_is_multi and missing_seed_scenario_count > 0:
            raise RuntimeError(
                f"Eval payload {p} is multi-scenario but has {missing_seed_scenario_count} seed_games without scenario_id"
            )
        if payload_is_multi and not scenario_ids_seen:
            raise RuntimeError(
                f"Eval payload {p} is multi-scenario but no seed_games carry scenario_id"
            )
        if (not payload_is_multi) and (not scenario_ids_seen) and payload_scenario_id:
            scenario_ids_seen.add(payload_scenario_id)
        scenario_ids = sorted(scenario_ids_seen)
        scenario_id_value = (
            f"multi:{'|'.join(scenario_ids)}"
            if len(scenario_ids) > 1
            else (scenario_ids[0] if scenario_ids else payload_scenario_id)
        )
        rows.append(
            {
                "eval_id": p.stem.replace("bench_eval_", ""),
                "created_at_utc": _iso_from_mtime(p),
                "source_path": str(p),
                "scenario_id": scenario_id_value,
                "scenario_ids": list(scenario_ids),
                "phase_2_9_promotion_gate": dict(payload.get("phase_2_9_promotion_gate", {}) or {}),
                "head_diagnostics_eval": dict(payload.get("head_diagnostics_eval", {}) or {}),
                "flow_traceability": {
                    "flow_source": "eval",
                    "flow_contract_version": "phase_2_9_eval_kpis.v1",
                    "flow_available": bool(diagnostics_eval),
                    "flow_fields": sorted(list(diagnostics_eval.keys())),
                },
                "diagnostics_summary_eval": diagnostics_eval,
                "results": filtered_results,
                "controller_unknown_label_rows": sum(
                    1 for r in filtered_results if int(r.get("controller_unknown_label_count", 0) or 0) > 0
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


def _resolve_parent_run_id_from_manifest(run_dir: Path) -> str:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return ""
    manifest = _read_json(manifest_path)
    cfg = dict(manifest.get("config", {}) or {})
    resume_checkpoint = str(cfg.get("resume_checkpoint", "") or "")
    return _extract_run_id_from_checkpoint(resume_checkpoint)


def _build_run_dir_by_id_index(repo_root: Path, run_roots: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for root_rel in list(run_roots or []):
        root = (repo_root / str(root_rel)).resolve()
        if not root.exists():
            continue
        for rd in root.glob("*"):
            if not rd.is_dir():
                continue
            name = str(rd.name or "")
            if not name:
                continue
            if name.startswith("efficientzero_v2_") or name.startswith("muzero_"):
                out[name] = rd
    return out


def _resolve_lineage_root_run_id(
    *,
    run_id: str,
    parent_run_id: str,
    run_dir_by_id: dict[str, Path],
    memo: dict[str, str],
) -> str:
    rid = str(run_id or "").strip()
    if not rid:
        return ""
    if rid in memo:
        return memo[rid]
    seen: set[str] = set()
    current = rid
    parent = str(parent_run_id or "").strip()
    while parent and parent not in seen:
        seen.add(parent)
        next_dir = run_dir_by_id.get(parent)
        if next_dir is None:
            current = parent
            break
        current = parent
        parent = _resolve_parent_run_id_from_manifest(next_dir)
    memo[rid] = current
    return current


def build_reporting_catalog(
    repo_root: Path,
    runs_roots_rel: str | Iterable[str] = ("runs_curriculum", "runs"),
    *,
    include_random_selfplay: bool = False,
    include_eval_payload_details: bool = True,
    max_eval_history_per_model: int | None = None,
    include_run_ids: set[str] | None = None,
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
                include_run_ids=include_run_ids,
            )
        )
        train_runs.extend(
            _collect_agent_train_runs(
                repo_root,
                runs_root_rel=runs_root_rel,
                run_prefix="efficientzero_v2_",
                engine="efficientzero_v2",
                algorithm="efficientzero_v2",
                include_run_ids=include_run_ids,
            )
        )

    lineage_memo: dict[str, str] = {}
    run_dir_by_id = _build_run_dir_by_id_index(repo_root=repo_root, run_roots=run_roots)
    models_by_engine_and_lineage: dict[str, dict[str, dict[str, Any]]] = {}
    for tr in train_runs:
        engine = str(tr.get("engine", ""))
        algorithm = str(tr.get("algorithm", engine))
        fp = str(tr.get("config_fingerprint", ""))
        run_id = str(tr.get("run_id", ""))
        parent_run_id = str(tr.get("parent_run_id", "") or "")
        lineage_root_run_id = _resolve_lineage_root_run_id(
            run_id=run_id,
            parent_run_id=parent_run_id,
            run_dir_by_id=run_dir_by_id,
            memo=lineage_memo,
        )
        if not lineage_root_run_id:
            lineage_root_run_id = run_id
        model_id = f"{engine}_{lineage_root_run_id}"
        lineage_key = str(lineage_root_run_id or run_id)
        engine_bucket = models_by_engine_and_lineage.setdefault(engine, {})
        model_row = engine_bucket.setdefault(
            lineage_key,
            {
                "model_id": model_id,
                "engine": engine,
                "algorithm": algorithm,
                "lineage_root_run_id": lineage_root_run_id,
                "config_fingerprint": fp,
                "train_history": [],
                "eval_history": [],
            },
        )
        train_entry = {
            **tr,
            "lineage_root_run_id": lineage_root_run_id,
            "git_commit": commit_by_train_run.get(run_id, ""),
        }
        model_row["train_history"].append(train_entry)
        model_row["eval_history"].extend(
            [
                {
                    **ev,
                    "train_run_id": run_id,
                    "curriculum_phase": str(tr.get("curriculum_phase", "") or ""),
                    "lineage_root_run_id": lineage_root_run_id,
                    "git_commit": commit_by_train_run.get(run_id, ""),
                }
                for root_rel in run_roots
                for ev in _collect_eval_history(
                    repo_root,
                    runs_root_rel=root_rel,
                    train_run_id=run_id,
                    include_random_selfplay=include_random_selfplay,
                    include_eval_payload_details=include_eval_payload_details,
                )
            ]
        )

    for engine_models in models_by_engine_and_lineage.values():
        for model_row in engine_models.values():
            train_rows = list(model_row.get("train_history", []) or [])
            eval_rows = list(model_row.get("eval_history", []) or [])
            train_rows.sort(key=lambda r: str(r.get("created_at_utc", "")), reverse=True)
            eval_rows.sort(key=lambda r: str(r.get("created_at_utc", "")), reverse=True)
            eval_total_count = int(len(eval_rows))
            if max_eval_history_per_model is not None:
                eval_rows = eval_rows[: max(0, int(max_eval_history_per_model))]
            def _unpack_scenarios(raw_items: Any) -> list[str]:
                if not raw_items:
                    return []
                if isinstance(raw_items, str):
                    candidates = [raw_items]
                elif isinstance(raw_items, (list, tuple, set)):
                    candidates = list(raw_items)
                else:
                    return []
                out_sids: list[str] = []
                for item in candidates:
                    s = str(item or "").strip()
                    if not s:
                        continue
                    if s.startswith("multi:"):
                        s = s[len("multi:") :].strip()
                    if "|" in s:
                        out_sids.extend([p.strip() for p in s.split("|") if p.strip()])
                    else:
                        out_sids.append(s)
                seen_sids = set()
                res_sids = []
                for x in out_sids:
                    if x not in seen_sids:
                        seen_sids.add(x)
                        res_sids.append(x)
                return res_sids

            scenario_train_counts: dict[str, int] = {}
            scenario_eval_counts: dict[str, int] = {}
            for tr in train_rows:
                sids = _unpack_scenarios(tr.get("scenario_ids") or tr.get("scenario_id"))
                for sid in sids:
                    scenario_train_counts[sid] = scenario_train_counts.get(sid, 0) + 1
            for ev in eval_rows:
                raw_sids = ev.get("scenario_ids")
                if not raw_sids and ev.get("scenario_ids_json"):
                    try:
                        import json
                        raw_sids = json.loads(ev["scenario_ids_json"])
                    except Exception:
                        raw_sids = None
                if not raw_sids:
                    raw_sids = ev.get("scenario_id")
                sids = _unpack_scenarios(raw_sids)
                for sid in sids:
                    scenario_eval_counts[sid] = scenario_eval_counts.get(sid, 0) + 1
            scenarios_seen = sorted(set(list(scenario_train_counts.keys()) + list(scenario_eval_counts.keys())))
            t_date = str((train_rows[0] if train_rows else {}).get("created_at_utc", "") or "")
            e_date = str((eval_rows[0] if eval_rows else {}).get("created_at_utc", "") or "")
            model_row["latest_train_created_at_utc"] = t_date
            model_row["latest_eval_created_at_utc"] = e_date
            model_row["train_history"] = train_rows
            model_row["eval_history"] = eval_rows
            model_row["eval_history_total_count"] = eval_total_count
            model_row["eval_history_visible_count"] = int(len(eval_rows))
            model_row["eval_history_truncated"] = bool(len(eval_rows) < eval_total_count)
            model_row["scenarios_seen"] = scenarios_seen
            model_row["scenario_train_counts"] = scenario_train_counts
            model_row["scenario_eval_counts"] = scenario_eval_counts

    # Explicit engine buckets requested by user; keep placeholders ready.
    engines = []
    for engine_name in ["efficientzero_v2", "sb3", "muzero", "alpha"]:
        engine_models = sorted(
            list((models_by_engine_and_lineage.get(engine_name) or {}).values()),
            key=lambda m: (
                max(
                    str(m.get("latest_train_created_at_utc") or ""),
                    str(m.get("latest_eval_created_at_utc") or ""),
                ),
                str(m.get("model_id") or ""),
            ),
            reverse=True,
        )
        engines.append(
            {
                "engine": engine_name,
                "models": engine_models,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION_V2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "runs_roots": run_roots,
        "engines": engines,
    }


def _side_value_from_map(src: Any, side: str) -> Any:
    if not isinstance(src, dict):
        return None
    s = str(side or "").strip()
    up = _canonical_reporting_side(s)
    keys = [up, s, s.lower()]
    if up == "GE":
        # Backward compatibility for historical payloads using IT.
        keys.extend(["IT", "it"])
    for k in keys:
        if k in src:
            return src.get(k)
    return None


def _canonical_reporting_side(side: Any) -> str:
    raw = str(side or "").strip().upper()
    # Reporting canonical labels are US / GE.
    if raw == "IT":
        return "GE"
    return raw


def _controller_label_for_side(result_row: dict[str, Any], side: str) -> str:
    controller = str(_side_value_from_map(result_row.get("controller_by_side", {}), side) or "").strip()
    if controller and controller.lower() != "unknown":
        return controller
    side_up = _canonical_reporting_side(side)
    alt_side = "GE" if side_up == "IT" else "IT" if side_up == "GE" else ""
    if alt_side:
        alt_ctrl = str(_side_value_from_map(result_row.get("controller_by_side", {}), alt_side) or "").strip()
        if alt_ctrl and alt_ctrl.lower() != "unknown":
            return alt_ctrl

    pol = str(_side_value_from_map(result_row.get("policy_by_side", {}), side) or "").strip().lower()
    if not pol and alt_side:
        pol = str(_side_value_from_map(result_row.get("policy_by_side", {}), alt_side) or "").strip().lower()

    if pol in {"mcts", "efficientzero", "efficientzero_v2", "ezv2"}:
        return "EfficientZeroV2"
    if pol == "random":
        return "Random"

    prof = str(result_row.get("matchup_profile", "")).strip().lower()
    if prof:
        if "selfplay" in prof:
            return "Random" if "random" in prof else "EfficientZeroV2"
        if "side_a" in prof:
            return "EfficientZeroV2" if side_up in ("IT", "GE") else "Random"
        if "side_b" in prof:
            return "Random" if side_up in ("IT", "GE") else "EfficientZeroV2"

    return controller if controller else "Unknown"


def _opponent_controller_for_side(result_row: dict[str, Any], side: str) -> str:
    side_up = _canonical_reporting_side(side)
    candidates: set[str] = set()
    for src_key in ("controller_by_side", "policy_by_side"):
        src = dict(result_row.get(src_key, {}) or {})
        for raw_side in src.keys():
            other_side = _canonical_reporting_side(raw_side)
            if not other_side or other_side == side_up:
                continue
            candidates.add(_controller_label_for_side(result_row, other_side))
    if not candidates:
        opp_side = "US" if side_up in ("IT", "GE") else "GE"
        cand = _controller_label_for_side(result_row, opp_side)
        if cand and cand.lower() != "unknown":
            return cand
        return "Unknown"
    if len(candidates) == 1:
        return list(candidates)[0]
    return "/".join(sorted(candidates))


def _collect_result_sides(result_row: dict[str, Any]) -> list[str]:
    side_set: set[str] = set()
    for key in ("controller_by_side", "policy_by_side", "winner_side_rates", "vp_net_avg_by_side"):
        src = result_row.get(key, {})
        if isinstance(src, dict):
            for raw_side in src.keys():
                side = _canonical_reporting_side(raw_side)
                if side:
                    side_set.add(side)
    # Seed-level side metrics are the canonical source for ELO side rows.
    for sg in list(result_row.get("seed_games", []) or []):
        sg_row = dict(sg or {})
        side_metrics = dict(sg_row.get("side_metrics", {}) or {})
        for raw_side in side_metrics.keys():
            side = _canonical_reporting_side(raw_side)
            if side:
                side_set.add(side)
    return sorted(side_set)


def _build_catalog_index_rows(
    catalog_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows_models: list[dict[str, Any]] = []
    rows_evals: list[dict[str, Any]] = []
    rows_trains: list[dict[str, Any]] = []
    rows_eval_result_sides: list[dict[str, Any]] = []
    for eng in list(catalog_payload.get("engines", []) or []):
        engine_name = str((eng or {}).get("engine", "") or "")
        for model in list((eng or {}).get("models", []) or []):
            model_id = str((model or {}).get("model_id", "") or "")
            rows_models.append(
                {
                    "schema_version": SCHEMA_VERSION_V2,
                    "engine": engine_name,
                    "model_id": model_id,
                    "config_fingerprint": str((model or {}).get("config_fingerprint", "") or ""),
                    "train_runs": int(len(list((model or {}).get("train_history", []) or []))),
                    "eval_runs": int(len(list((model or {}).get("eval_history", []) or []))),
                    "latest_train_run_id": str(
                        ((list((model or {}).get("train_history", []) or [{}])[0] or {}).get("run_id", "")) or ""
                    ),
                    "latest_train_created_at_utc": str(
                        ((list((model or {}).get("train_history", []) or [{}])[0] or {}).get("created_at_utc", "")) or ""
                    ),
                    "latest_eval_created_at_utc": str(
                        ((list((model or {}).get("eval_history", []) or [{}])[0] or {}).get("created_at_utc", "")) or ""
                    ),
                }
            )
            for tr in list((model or {}).get("train_history", []) or []):
                summary_raw = dict((tr or {}).get("summary", {}) or (tr or {}).get("train_summary", {}) or {})
                obs_raw = dict((tr or {}).get("observation_channels", {}) or {})
                eff_raw = dict((tr or {}).get("channel_effectiveness", {}) or {})
                rows_trains.append(
                    {
                        "schema_version": SCHEMA_VERSION_V2,
                        "engine": engine_name,
                        "model_id": model_id,
                        "run_id": str((tr or {}).get("run_id", "") or ""),
                        "scenario_id": str((tr or {}).get("scenario_id", "") or ""),
                        "created_at_utc": str((tr or {}).get("created_at_utc", "") or ""),
                        "git_commit": str((tr or {}).get("git_commit", "") or ""),
                        "is_retrain": bool((tr or {}).get("is_retrain", False)),
                        "parent_run_id": str((tr or {}).get("parent_run_id", "") or ""),
                        "curriculum_phase": str((tr or {}).get("curriculum_phase", "") or ""),
                        "latest_checkpoint": str((tr or {}).get("latest_checkpoint", "") or ""),
                        "summary_json": json.dumps(summary_raw) if summary_raw else None,
                        "observation_channels_json": json.dumps(obs_raw) if obs_raw else None,
                        "channel_effectiveness_json": json.dumps(eff_raw) if eff_raw else None,
                    }
                )
            for ev in list((model or {}).get("eval_history", []) or []):
                eval_id = str((ev or {}).get("eval_id", "") or "")
                train_run_id = str((ev or {}).get("train_run_id", "") or "")
                scenario_id = str((ev or {}).get("scenario_id", "") or "")
                created_at_utc = str((ev or {}).get("created_at_utc", "") or "")
                source_path = str((ev or {}).get("source_path", "") or "")
                curriculum_phase = str((ev or {}).get("curriculum_phase", "") or "")
                eval_results_rows = [
                    dict(r or {})
                    for r in list((ev or {}).get("results", []) or [])
                    if isinstance(r, dict)
                ]
                compact_results = _compact_eval_results(eval_results_rows)
                head_diag = dict((ev or {}).get("head_diagnostics_eval", {}) or {})
                diag_summary = dict((ev or {}).get("diagnostics_summary_eval", {}) or {})
                phase_gate = dict((ev or {}).get("phase_2_9_promotion_gate", {}) or {})
                scen_ids = list((ev or {}).get("scenario_ids", []) or [])
                rows_evals.append(
                    {
                        "schema_version": SCHEMA_VERSION_V2,
                        "engine": engine_name,
                        "model_id": model_id,
                        "eval_id": eval_id,
                        "train_run_id": train_run_id,
                        "scenario_id": scenario_id,
                        "created_at_utc": created_at_utc,
                        "source_path": source_path,
                        "curriculum_phase": curriculum_phase,
                        "results_count": int(len(eval_results_rows)),
                        "has_results": bool(len(eval_results_rows) > 0),
                        "head_diagnostics_json": json.dumps(head_diag) if head_diag else None,
                        "diagnostics_summary_json": json.dumps(diag_summary) if diag_summary else None,
                        "phase_gate_json": json.dumps(phase_gate) if phase_gate else None,
                        "scenario_ids_json": json.dumps(scen_ids) if scen_ids else None,
                        "compact_results_json": json.dumps(compact_results) if compact_results else None,
                    }
                )
                for rr in eval_results_rows:
                    if not isinstance(rr, dict):
                        continue
                    episodes = int(rr.get("episodes", 0) or 0)
                    if episodes <= 0:
                        seed_games_probe = list(rr.get("seed_games", []) or [])
                        if seed_games_probe:
                            episodes = int(len(seed_games_probe))
                    if episodes <= 0:
                        winner_counts = dict(rr.get("winner_side_counts", {}) or {})
                        if winner_counts:
                            try:
                                episodes = int(
                                    sum(int(v or 0) for v in winner_counts.values())
                                )
                            except Exception:
                                episodes = 0
                    if episodes <= 0:
                        episodes = 1
                    scenario_outcome = dict(rr.get("scenario_outcome_class_rates", {}) or {})
                    total_victory_rate = float(scenario_outcome.get("total_victory", 0.0) or 0.0)
                    victory_rate = float(scenario_outcome.get("victory", 0.0) or 0.0)
                    draw_rate = float(scenario_outcome.get("draw", 0.0) or 0.0)
                    defeat_rate = float(scenario_outcome.get("defeat", 0.0) or 0.0)
                    total_defeat_rate = float(scenario_outcome.get("total_defeat", 0.0) or 0.0)
                    win_rate = float(total_victory_rate + victory_rate)
                    loss_rate = float(defeat_rate + total_defeat_rate)
                    side_rows = _collect_result_sides(rr)
                    if not side_rows:
                        side_rows = ["ALL"]
                    seed_games = [
                        dict(x or {})
                        for x in list(rr.get("seed_games", []) or [])
                        if isinstance(x, dict)
                    ]
                    use_seed_rows = bool(seed_games)
                    for side in side_rows:
                        controller = _controller_label_for_side(rr, side)
                        opponent_controller = _opponent_controller_for_side(rr, side)
                        if use_seed_rows:
                            for sg in seed_games:
                                seed_val = int(sg.get("seed", 0) or 0)
                                seed_scenario_id = str(sg.get("scenario_id", "") or scenario_id)
                                side_up = _canonical_reporting_side(side)
                                seed_outcome_by_side = dict(sg.get("scenario_outcome_class_by_side", {}) or {})
                                side_class = str(_side_value_from_map(seed_outcome_by_side, side_up) or "").strip().lower()
                                if side_class == "total_victory":
                                    seed_win, seed_draw, seed_loss = 1.0, 0.0, 0.0
                                    seed_total_victory, seed_victory, seed_defeat, seed_total_defeat = 1.0, 0.0, 0.0, 0.0
                                elif side_class == "victory":
                                    seed_win, seed_draw, seed_loss = 1.0, 0.0, 0.0
                                    seed_total_victory, seed_victory, seed_defeat, seed_total_defeat = 0.0, 1.0, 0.0, 0.0
                                elif side_class == "draw":
                                    seed_win, seed_draw, seed_loss = 0.0, 1.0, 0.0
                                    seed_total_victory, seed_victory, seed_defeat, seed_total_defeat = 0.0, 0.0, 0.0, 0.0
                                elif side_class == "defeat":
                                    seed_win, seed_draw, seed_loss = 0.0, 0.0, 1.0
                                    seed_total_victory, seed_victory, seed_defeat, seed_total_defeat = 0.0, 0.0, 1.0, 0.0
                                elif side_class == "total_defeat":
                                    seed_win, seed_draw, seed_loss = 0.0, 0.0, 1.0
                                    seed_total_victory, seed_victory, seed_defeat, seed_total_defeat = 0.0, 0.0, 0.0, 1.0
                                else:
                                    # Producer did not provide side outcome class for this seed/side.
                                    seed_win, seed_draw, seed_loss = 0.0, 0.0, 0.0
                                    seed_total_victory, seed_victory, seed_defeat, seed_total_defeat = 0.0, 0.0, 0.0, 0.0
                                seed_side_metrics = dict(sg.get("side_metrics", {}) or {})
                                side_metric_row = dict(seed_side_metrics.get(side_up, {}) or {})
                                rows_eval_result_sides.append(
                                    {
                                        "schema_version": SCHEMA_VERSION_V2,
                                        "engine": engine_name,
                                        "model_id": model_id,
                                        "eval_id": eval_id,
                                        "train_run_id": train_run_id,
                                        "scenario_id": seed_scenario_id,
                                        "created_at_utc": created_at_utc,
                                        "source_path": source_path,
                                        "curriculum_phase": curriculum_phase,
                                        "matchup_profile": str(rr.get("matchup_profile", "") or ""),
                                        "agent_name": str(rr.get("agent_name", "") or ""),
                                        "side": str(side),
                                        "controller": controller,
                                        "opponent_controller": opponent_controller,
                                        "seed": int(seed_val),
                                        "episodes": 1,
                                        "win_rate": float(seed_win),
                                        "draw_rate": float(seed_draw),
                                        "loss_rate": float(seed_loss),
                                        "total_victory_rate": float(seed_total_victory),
                                        "victory_rate": float(seed_victory),
                                        "defeat_rate": float(seed_defeat),
                                        "total_defeat_rate": float(seed_total_defeat),
                                        "avg_return": float(rr.get("avg_return", 0.0) or 0.0),
                                        "tracked_captured_avg": float(rr.get("tracked_captured_avg", 0.0) or 0.0),
                                        "vp_net_avg_side": (
                                            float(_side_value_from_map(rr.get("vp_net_avg_by_side", {}), side) or 0.0)
                                            if side != "ALL"
                                            else None
                                        ),
                                        "winner_rate_side": (
                                            float(_side_value_from_map(rr.get("winner_side_rates", {}), side) or 0.0)
                                            if side != "ALL"
                                            else None
                                        ),
                                        "units_alive_final": (
                                            float(side_metric_row.get("units_alive_final", 0.0))
                                            if side != "ALL" and side_metric_row.get("units_alive_final", None) is not None
                                            else None
                                        ),
                                        "units_lost": (
                                            float(side_metric_row.get("units_lost", 0.0))
                                            if side != "ALL" and side_metric_row.get("units_lost", None) is not None
                                            else None
                                        ),
                                        "enemy_units_eliminated": (
                                            float(side_metric_row.get("enemy_units_eliminated", 0.0))
                                            if side != "ALL" and side_metric_row.get("enemy_units_eliminated", None) is not None
                                            else None
                                        ),
                                        "damage_dealt": (
                                            float(side_metric_row.get("damage_dealt", 0.0))
                                            if side != "ALL" and side_metric_row.get("damage_dealt", None) is not None
                                            else None
                                        ),
                                    }
                                )
                        else:
                            scenario_outcome_by_side = dict(rr.get("scenario_outcome_class_rates_by_side", {}) or {})
                            side_outcome_rates = dict(_side_value_from_map(scenario_outcome_by_side, side) or {})
                            side_total_victory_rate = float(side_outcome_rates.get("total_victory", 0.0) or 0.0)
                            side_victory_rate = float(side_outcome_rates.get("victory", 0.0) or 0.0)
                            side_draw_rate = float(side_outcome_rates.get("draw", 0.0) or 0.0)
                            side_defeat_rate = float(side_outcome_rates.get("defeat", 0.0) or 0.0)
                            side_total_defeat_rate = float(side_outcome_rates.get("total_defeat", 0.0) or 0.0)
                            side_win_rate = float(side_total_victory_rate + side_victory_rate)
                            side_loss_rate = float(side_defeat_rate + side_total_defeat_rate)
                            rows_eval_result_sides.append(
                                {
                                    "schema_version": SCHEMA_VERSION_V2,
                                    "engine": engine_name,
                                    "model_id": model_id,
                                    "eval_id": eval_id,
                                    "train_run_id": train_run_id,
                                    "scenario_id": scenario_id,
                                    "created_at_utc": created_at_utc,
                                    "source_path": source_path,
                                    "curriculum_phase": curriculum_phase,
                                    "matchup_profile": str(rr.get("matchup_profile", "") or ""),
                                    "agent_name": str(rr.get("agent_name", "") or ""),
                                    "side": str(side),
                                    "controller": controller,
                                    "opponent_controller": opponent_controller,
                                    "seed": None,
                                    "episodes": int(episodes),
                                    "win_rate": float(side_win_rate),
                                    "draw_rate": float(side_draw_rate),
                                    "loss_rate": float(side_loss_rate),
                                    "total_victory_rate": float(side_total_victory_rate),
                                    "victory_rate": float(side_victory_rate),
                                    "defeat_rate": float(side_defeat_rate),
                                    "total_defeat_rate": float(side_total_defeat_rate),
                                    "avg_return": float(rr.get("avg_return", 0.0) or 0.0),
                                    "tracked_captured_avg": float(rr.get("tracked_captured_avg", 0.0) or 0.0),
                                    "vp_net_avg_side": (
                                        float(_side_value_from_map(rr.get("vp_net_avg_by_side", {}), side) or 0.0)
                                        if side != "ALL"
                                        else None
                                    ),
                                    "winner_rate_side": (
                                        float(_side_value_from_map(rr.get("winner_side_rates", {}), side) or 0.0)
                                        if side != "ALL"
                                        else None
                                    ),
                                    "units_alive_final": None,
                                    "units_lost": None,
                                    "enemy_units_eliminated": None,
                                    "damage_dealt": None,
                                }
                            )
    return rows_models, rows_evals, rows_trains, rows_eval_result_sides


def write_catalog_indexes_parquet(catalog_payload: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_models, rows_evals, rows_trains, rows_eval_result_sides = _build_catalog_index_rows(catalog_payload)
    ok_models = False
    ok_evals = False
    ok_trains = False
    ok_eval_result_sides = False
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore

        pq.write_table(pa.Table.from_pylist(rows_models), out_dir / "catalog_models.parquet")
        pq.write_table(pa.Table.from_pylist(rows_evals), out_dir / "catalog_evals.parquet")
        pq.write_table(pa.Table.from_pylist(rows_trains), out_dir / "catalog_trains.parquet")
        pq.write_table(pa.Table.from_pylist(rows_eval_result_sides), out_dir / "catalog_eval_result_sides.parquet")
        ok_models = True
        ok_evals = True
        ok_trains = True
        ok_eval_result_sides = True
    except Exception:
        pass
    return {
        "schema_version": SCHEMA_VERSION_V2,
        "models_rows": int(len(rows_models)),
        "evals_rows": int(len(rows_evals)),
        "trains_rows": int(len(rows_trains)),
        "eval_result_sides_rows": int(len(rows_eval_result_sides)),
        "catalog_models_parquet": bool(ok_models),
        "catalog_evals_parquet": bool(ok_evals),
        "catalog_trains_parquet": bool(ok_trains),
        "catalog_eval_result_sides_parquet": bool(ok_eval_result_sides),
    }


def _read_parquet_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        import pyarrow.parquet as pq  # type: ignore

        table = pq.read_table(path)
        return [dict(r or {}) for r in list(table.to_pylist() or [])]
    except Exception:
        return []


def _write_parquet_rows(path: Path, rows: list[dict[str, Any]]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore

        pq.write_table(pa.Table.from_pylist(list(rows or [])), path)
        return True
    except Exception:
        return False


def _upsert_rows(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    key_fn,
) -> list[dict[str, Any]]:
    merged: dict[tuple, dict[str, Any]] = {}
    for row in existing:
        merged[key_fn(row)] = dict(row or {})
    for row in incoming:
        merged[key_fn(row)] = dict(row or {})
    return list(merged.values())


def merge_catalog_indexes_parquet(catalog_payload: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """
    Incremental upsert of catalog parquet indexes.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    incoming_models, incoming_evals, incoming_trains, incoming_eval_result_sides = _build_catalog_index_rows(catalog_payload)
    models_path = out_dir / "catalog_models.parquet"
    evals_path = out_dir / "catalog_evals.parquet"
    trains_path = out_dir / "catalog_trains.parquet"
    eval_result_sides_path = out_dir / "catalog_eval_result_sides.parquet"

    prev_models = _read_parquet_rows(models_path)
    prev_evals = _read_parquet_rows(evals_path)
    prev_trains = _read_parquet_rows(trains_path)
    prev_eval_result_sides = _read_parquet_rows(eval_result_sides_path)

    merged_models = _upsert_rows(
        prev_models,
        incoming_models,
        key_fn=lambda r: (str(r.get("engine", "")), str(r.get("model_id", ""))),
    )
    merged_evals = _upsert_rows(
        prev_evals,
        incoming_evals,
        key_fn=lambda r: (
            str(r.get("engine", "")),
            str(r.get("model_id", "")),
            str(r.get("eval_id", "")),
            str(r.get("train_run_id", "")),
        ),
    )
    merged_trains = _upsert_rows(
        prev_trains,
        incoming_trains,
        key_fn=lambda r: (
            str(r.get("engine", "")),
            str(r.get("model_id", "")),
            str(r.get("run_id", "")),
        ),
    )
    merged_eval_result_sides = _upsert_rows(
        prev_eval_result_sides,
        incoming_eval_result_sides,
        key_fn=lambda r: (
            str(r.get("engine", "")),
            str(r.get("model_id", "")),
            str(r.get("eval_id", "")),
            str(r.get("matchup_profile", "")),
            str(r.get("agent_name", "")),
            str(r.get("side", "")),
            str(r.get("seed", "")),
        ),
    )

    ok_models = _write_parquet_rows(models_path, merged_models)
    ok_evals = _write_parquet_rows(evals_path, merged_evals)
    ok_trains = _write_parquet_rows(trains_path, merged_trains)
    ok_eval_result_sides = _write_parquet_rows(eval_result_sides_path, merged_eval_result_sides)

    return {
        "schema_version": SCHEMA_VERSION_V2,
        "mode": "incremental_upsert",
        "models_rows": int(len(merged_models)),
        "evals_rows": int(len(merged_evals)),
        "trains_rows": int(len(merged_trains)),
        "eval_result_sides_rows": int(len(merged_eval_result_sides)),
        "catalog_models_parquet": bool(ok_models),
        "catalog_evals_parquet": bool(ok_evals),
        "catalog_trains_parquet": bool(ok_trains),
        "catalog_eval_result_sides_parquet": bool(ok_eval_result_sides),
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
    parser.add_argument(
        "--include-random-selfplay",
        action="store_true",
        help="Include random_selfplay rows in report catalog (opt-in).",
    )
    parser.add_argument(
        "--out-parquet-dir",
        default="",
        help="Optional output directory for parquet indexes (catalog_models/catalog_evals).",
    )
    parser.add_argument(
        "--include-eval-payload-details",
        action="store_true",
        help="Include heavy per-step eval payloads in catalog JSON (debug-only).",
    )
    parser.add_argument(
        "--max-eval-history-per-model",
        type=int,
        default=0,
        help="Limit eval history per model in catalog output (0 means unlimited).",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    payload = build_reporting_catalog(
        repo_root=repo_root,
        runs_roots_rel=str(args.runs_root),
        include_random_selfplay=bool(args.include_random_selfplay),
        include_eval_payload_details=bool(args.include_eval_payload_details),
        max_eval_history_per_model=(None if int(args.max_eval_history_per_model or 0) <= 0 else int(args.max_eval_history_per_model)),
    )
    out_path = (repo_root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_index = {}
    if str(args.out_parquet_dir or "").strip():
        out_parquet_dir = (repo_root / args.out_parquet_dir).resolve() if not Path(args.out_parquet_dir).is_absolute() else Path(args.out_parquet_dir)
        out_index = write_catalog_indexes_parquet(payload, out_parquet_dir)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out_path),
                "schema_version": payload["schema_version"],
                "parquet_indexes": out_index,
            },
            indent=2,
        )
    )
