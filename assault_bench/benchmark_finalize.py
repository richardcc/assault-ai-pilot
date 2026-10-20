from __future__ import annotations

from pathlib import Path
from typing import Any

from assault_bench.transform_ops import to_dict_rows

def resolve_run_id_from_checkpoint(checkpoint_path: str) -> str:
    if not str(checkpoint_path or "").strip():
        return ""
    try:
        ckptp = Path(checkpoint_path)
        if not ckptp.is_absolute():
            ckptp = (Path.cwd() / ckptp).resolve()
        return str(ckptp.parent.parent.name)
    except Exception:
        return ""


def build_phase29_mlflow_metrics(payload: dict) -> dict[str, float]:
    return {
        "phase29_gate_pass": 1.0
        if str(payload.get("phase_2_9_promotion_gate", {}).get("status", "")).upper() == "PASS"
        else 0.0,
        "phase29_eval_reaction_activation_rate": float(
            payload.get("phase_2_9_train_eval", {}).get("eval", {}).get("reaction_fire_activation_rate", 0.0)
        ),
        "phase29_eval_melee_attempts": float(
            payload.get("phase_2_9_train_eval", {}).get("eval", {}).get("melee_attempts", 0.0)
        ),
        "phase29_eval_converted_from_progress_rate": float(
            payload.get("phase_2_9_train_eval", {}).get("eval", {}).get("converted_from_progress_rate", 0.0)
        ),
        "phase29_eval_converted_rate_near_vp": float(
            payload.get("phase_2_9_train_eval", {}).get("eval", {}).get("converted_rate_near_vp", 0.0)
        ),
        "phase29_eval_conversion_within_2_turns_after_progress": float(
            payload.get("phase_2_9_train_eval", {})
            .get("eval", {})
            .get("conversion_within_2_turns_after_progress", 0.0)
        ),
    }


def build_benchmark_payload(
    *,
    schema_version: str,
    scenario_id: str,
    run_id: str,
    results: list,
    load_train_summary_fn,
    checkpoint_path: str,
    aggregate_muzero_eval_kpis_fn,
    build_phase29_train_eval_fn,
    build_phase29_promotion_gate_fn,
    build_eval_diagnostics_summary_fn,
    build_head_diagnostics_eval_fn,
) -> dict:
    def _validate_seed_games_contract(result_rows: list[dict[str, Any]]) -> None:
        required_metric_keys = (
            "units_alive_final",
            "units_lost",
            "enemy_units_eliminated",
            "damage_dealt",
        )
        errors: list[str] = []
        for rr in list(result_rows or []):
            agent_name = str(rr.get("agent_name", "") or "")
            episodes = int(rr.get("episodes", 0) or 0)
            seed_games = list(rr.get("seed_games", []) or [])
            if episodes > 0 and len(seed_games) <= 0:
                errors.append(
                    f"agent={agent_name}: seed_games missing (episodes={episodes})"
                )
                continue
            for sg in seed_games:
                row = dict(sg or {})
                if row.get("seed", None) is None:
                    errors.append(f"agent={agent_name}: seed_games row missing seed")
                    continue
                side_metrics = dict(row.get("side_metrics", {}) or {})
                if not side_metrics:
                    errors.append(
                        f"agent={agent_name} seed={row.get('seed')}: side_metrics missing"
                    )
                    continue
                for side, metric_row in side_metrics.items():
                    m = dict(metric_row or {})
                    missing = [k for k in required_metric_keys if m.get(k, None) is None]
                    if missing:
                        errors.append(
                            "agent="
                            f"{agent_name} seed={row.get('seed')} side={str(side)} "
                            f"missing_side_metric_keys={missing}"
                        )
        if errors:
            joined = "; ".join(errors[:8])
            if len(errors) > 8:
                joined += f"; ... (+{len(errors) - 8} more)"
            raise RuntimeError(
                "benchmark payload contract violation: missing seed-level side metrics. "
                + joined
            )

    payload = {
        "schema_version": str(schema_version),
        "scenario_id": str(scenario_id),
        "run_id": str(run_id or ""),
        "results": [r.__dict__ for r in list(results or [])],
    }
    _validate_seed_games_contract(
        [dict(r or {}) for r in list(payload.get("results", []) or [])]
    )
    result_rows = to_dict_rows([getattr(r, "__dict__", {}) for r in list(results or [])])
    muzero_row = next(
        (
            r
            for r in result_rows
            if str(r.get("agent_name", "")).strip().lower()
            in {"ezv2_stub", "efficientzero_v2_stub", "muzero_stub"}
        ),
        {},
    )
    baseline_row = next((r for r in result_rows if str(r.get("agent_name", "")) == "baseline_random"), {})
    train_summary = load_train_summary_fn(checkpoint_path=checkpoint_path)
    train_phase29 = dict(train_summary.get("phase_2_9_train_kpis", {}) or {})
    eval_phase29 = aggregate_muzero_eval_kpis_fn(payload["results"]) or dict(
        muzero_row.get("phase_2_9_eval_kpis", {}) or {}
    )
    payload["phase_2_9_train_eval"] = build_phase29_train_eval_fn(
        train_kpis=train_phase29,
        eval_kpis=eval_phase29,
    )
    payload["phase_2_9_promotion_gate"] = build_phase29_promotion_gate_fn(
        train_kpis=train_phase29,
        eval_kpis=eval_phase29,
        muzero_row=muzero_row,
        baseline_row=baseline_row,
    )
    payload["diagnostics_summary_eval"] = build_eval_diagnostics_summary_fn(
        eval_kpis=eval_phase29,
        tracked_side=str(muzero_row.get("tracked_side", "") or ""),
    )
    payload["head_diagnostics_eval"] = build_head_diagnostics_eval_fn(
        train_summary=train_summary,
        eval_kpis=eval_phase29,
        muzero_row=muzero_row,
    )
    payload["doctrine_eval_kpis"] = {
        "recon_survival_rate": float(eval_phase29.get("recon_survival_rate", 1.0)),
        "fire_support_stationarity": float(eval_phase29.get("fire_support_stationarity", 1.0)),
        "spearhead_vp_capture_rate": float(eval_phase29.get("spearhead_vp_capture_rate", 0.0)),
        "doctrine_adherence_rate": float(eval_phase29.get("doctrine_adherence_rate", 0.0)),
        "doctrine_mutation_rate": float(eval_phase29.get("doctrine_mutation_rate", 0.0)),
    }
    profile_times = [
        float(r.get("profile_wall_s", 0.0) or 0.0)
        for r in result_rows
        if isinstance(r.get("profile_wall_s", None), (int, float))
    ]
    total_wall_s = float(sum(profile_times))
    total_episodes = int(sum(int(r.get("episodes", 0) or 0) for r in result_rows))
    payload["benchmark_timing"] = {
        "total_wall_s": total_wall_s,
        "profile_count": int(len(result_rows)),
        "total_episodes": total_episodes,
        "episodes_per_second": (
            float(total_episodes) / float(total_wall_s)
            if total_wall_s > 0.0
            else 0.0
        ),
    }
    return payload
