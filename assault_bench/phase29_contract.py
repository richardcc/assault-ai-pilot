from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def load_train_summary_from_checkpoint(checkpoint_path: str) -> Dict[str, object]:
    if not checkpoint_path:
        return {}
    ckpt = Path(checkpoint_path)
    if not ckpt.is_absolute():
        ckpt = (Path.cwd() / ckpt).resolve()
    run_dir = ckpt.parent.parent
    summary_path = run_dir / "metrics" / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload or {})


def load_train_phase29_from_checkpoint(checkpoint_path: str) -> Dict[str, float]:
    summary = load_train_summary_from_checkpoint(checkpoint_path=checkpoint_path)
    section = summary.get("phase_2_9_train_kpis", {}) or {}
    return dict(section)


def _phase29_value(payload: Dict[str, object], key: str) -> float:
    if key in payload:
        return float(payload.get(key, 0.0) or 0.0)
    assault_quality = dict(payload.get("assault_quality", {}) or {})
    if key in assault_quality:
        return float(assault_quality.get(key, 0.0) or 0.0)
    return 0.0


def build_phase29_train_eval(train_kpis: Dict[str, float], eval_kpis: Dict[str, float]) -> Dict[str, Dict]:
    keys = [
        "reaction_window_count",
        "reaction_fire_count",
        "reaction_fire_skipped_count",
        "reaction_fire_kill_conversions",
        "reaction_fire_damage_sum",
        "reaction_fire_activation_rate",
        "reaction_fire_kill_conversion_rate",
        "reaction_fire_damage_induced_proxy",
        "reaction_fire_damage_prevented_proxy",
        "assault_melee_action_family_count",
        "melee_attempts",
        "melee_success_count",
        "melee_kills_sum",
        "melee_damage_sum",
        "melee_success_rate",
        "melee_kills_per_attempt",
        "melee_damage_per_attempt",
        "converted_from_progress_rate",
        "converted_rate_near_vp",
        "conversion_within_2_turns_after_progress",
        "xai_decision_steps",
        "xai_policy_confidence_mean",
        "xai_policy_margin_mean",
        "xai_latent_signal_coverage",
        "xai_vp_capture_opportunity_steps",
        "xai_vp_capture_taken_steps",
        "xai_vp_capture_take_rate",
        "xai_vp_immediate_capture_opportunity_steps",
        "xai_vp_immediate_capture_taken_steps",
        "xai_vp_immediate_capture_take_rate",
        "vp_approach_rate_eligible_steps",
        "vp_approach_rate_positive_steps",
        "vp_approach_rate",
        "vp_regret_delta_count",
        "vp_regret_delta_mean",
        "vp_regret_delta_p95",
        "q_saturation_candidate_rows",
        "q_saturation_hits",
        "q_saturation_rate",
        "decision_spread_step_count",
        "decision_spread_mean",
        "decision_spread_p50",
        "decision_spread_p95",
        "path_to_capture_length_count",
        "path_to_capture_length_mean",
        "path_to_capture_length_p95",
        "opportunity_conversion_early_opportunity_steps",
        "opportunity_conversion_early_converted_steps",
        "opportunity_conversion_early_rate",
        "opportunity_conversion_mid_opportunity_steps",
        "opportunity_conversion_mid_converted_steps",
        "opportunity_conversion_mid_rate",
        "opportunity_conversion_late_opportunity_steps",
        "opportunity_conversion_late_converted_steps",
        "opportunity_conversion_late_rate",
        "recon_survival_rate",
        "fire_support_stationarity",
        "spearhead_vp_capture_rate",
        "doctrine_adherence_rate",
        "doctrine_mutation_rate",
    ]
    return {
        "train": {k: _phase29_value(train_kpis, k) for k in keys},
        "eval": {k: float(eval_kpis.get(k, 0.0)) for k in keys},
        "delta_eval_minus_train": {
            k: float(eval_kpis.get(k, 0.0)) - _phase29_value(train_kpis, k)
            for k in keys
        },
    }


def build_eval_diagnostics_summary(eval_kpis: Dict[str, float], tracked_side: str) -> Dict[str, Dict]:
    opportunities = float(max(0.0, float(eval_kpis.get("reaction_window_count", 0.0))))
    progress_actions = float(max(0.0, float(eval_kpis.get("melee_attempts", 0.0))))
    stalls = float(max(0.0, opportunities - progress_actions))
    converted_rate_near_vp = float(eval_kpis.get("converted_rate_near_vp", 0.0))
    conversions = float(max(0.0, min(progress_actions, progress_actions * converted_rate_near_vp)))
    converted_after_progress = float(
        max(
            0.0,
            min(
                conversions,
                conversions * float(eval_kpis.get("converted_from_progress_rate", 0.0)),
            ),
        )
    )
    converted_without_progress = float(max(0.0, conversions - converted_after_progress))
    progressed_but_not_converted = float(max(0.0, progress_actions - conversions))
    stalled_and_not_converted = float(stalls)
    reaction_fire_count = float(max(0.0, float(eval_kpis.get("reaction_fire_count", 0.0))))
    reaction_fire_skipped_count = float(
        max(0.0, float(eval_kpis.get("reaction_fire_skipped_count", 0.0)))
    )
    non_progress_actions = float(max(0.0, stalls - reaction_fire_skipped_count))
    global_funnel = {"opportunities": opportunities, "progress_actions": progress_actions, "conversions": conversions, "stalls": stalls}
    global_explain = {
        "conversion_path_counts": {
            "converted_after_progress": converted_after_progress,
            "converted_without_progress": converted_without_progress,
            "progressed_but_not_converted": progressed_but_not_converted,
            "stalled_and_not_converted": stalled_and_not_converted,
        },
        "no_progress_reason_counts": {
            "reaction_fire": reaction_fire_count,
            "reaction_skip": reaction_fire_skipped_count,
            "non_progress_actions": non_progress_actions,
        },
        "no_progress_reason_l2_counts": {},
    }
    tracked_side_s = str(tracked_side or "").strip()
    by_side_funnel = {tracked_side_s: dict(global_funnel)} if tracked_side_s else {}
    by_side_explain = {tracked_side_s: dict(global_explain)} if tracked_side_s else {}
    return {
        "objective_progress_funnel": {"global": global_funnel, "by_side": by_side_funnel},
        "objective_progress_explain": {"global": global_explain, "by_side": by_side_explain},
        "source": "eval.phase_2_9_eval_kpis",
    }


def build_head_diagnostics_eval(
    *,
    train_summary: Dict[str, object],
    eval_kpis: Dict[str, float],
    muzero_row: Dict,
) -> Dict[str, object]:
    decision_steps = float(max(1.0, float(eval_kpis.get("xai_decision_steps", 0.0))))
    cap_taken = float(max(0.0, float(eval_kpis.get("xai_vp_capture_taken_steps", 0.0))))
    cap_opp = float(max(1.0, float(eval_kpis.get("xai_vp_capture_opportunity_steps", 0.0))))
    immediate_cap_taken = float(max(0.0, float(eval_kpis.get("xai_vp_immediate_capture_taken_steps", 0.0))))
    immediate_cap_opp = float(max(1.0, float(eval_kpis.get("xai_vp_immediate_capture_opportunity_steps", 0.0))))
    return {
        "policy": {
            "eval_decision_steps": float(eval_kpis.get("xai_decision_steps", 0.0)),
            "eval_confidence_mean": float(eval_kpis.get("xai_policy_confidence_mean", 0.0)),
            "eval_margin_mean": float(eval_kpis.get("xai_policy_margin_mean", 0.0)),
            "eval_latent_signal_coverage": float(eval_kpis.get("xai_latent_signal_coverage", 0.0)),
            "train_policy_loss": float(train_summary.get("policy_loss", 0.0) or 0.0),
        },
        "value": {
            "train_value_loss": float(train_summary.get("value_loss", 0.0) or 0.0),
            "eval_win_rate_proxy": float(muzero_row.get("win_rate", 0.0) or 0.0),
            "eval_avg_return_proxy": float(muzero_row.get("avg_return", 0.0) or 0.0),
        },
        "reward": {
            "train_reward_loss": float(train_summary.get("reward_loss", 0.0) or 0.0),
            "eval_avg_return_proxy": float(muzero_row.get("avg_return", 0.0) or 0.0),
            "eval_avg_steps_proxy": float(muzero_row.get("avg_steps", 0.0) or 0.0),
        },
        "objective": {
            "train_objective_loss": float(train_summary.get("objective_loss", 0.0) or 0.0),
            "eval_vp_capture_opportunity_steps": float(eval_kpis.get("xai_vp_capture_opportunity_steps", 0.0)),
            "eval_vp_immediate_capture_opportunity_steps": float(eval_kpis.get("xai_vp_immediate_capture_opportunity_steps", 0.0)),
            "eval_vp_capture_taken_steps": float(eval_kpis.get("xai_vp_capture_taken_steps", 0.0)),
            "eval_vp_immediate_capture_taken_steps": float(eval_kpis.get("xai_vp_immediate_capture_taken_steps", 0.0)),
            "eval_vp_capture_take_rate": float(cap_taken / cap_opp),
            "eval_vp_immediate_capture_take_rate": float(immediate_cap_taken / immediate_cap_opp),
            "eval_vp_conversion_efficiency": float(cap_taken / decision_steps),
            "eval_vp_immediate_conversion_efficiency": float(immediate_cap_taken / decision_steps),
            "eval_vp_capture_take_rate_denominator_steps": float(cap_opp),
            "eval_vp_conversion_efficiency_denominator_steps": float(decision_steps),
            "eval_tracked_captured_avg": float(muzero_row.get("tracked_captured_avg", 0.0) or 0.0),
        },
        "consistency": {
            "train_consistency_loss": float(train_summary.get("consistency_loss", 0.0) or 0.0),
            "train_consistency_pairs": float(train_summary.get("consistency_pairs", 0.0) or 0.0),
            "train_reanalysis_coverage": float(train_summary.get("reanalysis_coverage", 0.0) or 0.0),
            "train_reanalysis_target_drift": float(train_summary.get("reanalysis_target_drift", 0.0) or 0.0),
            "train_reanalysis_policy_drift": float(train_summary.get("reanalysis_policy_drift", 0.0) or 0.0),
            "eval_latent_drift": float(eval_kpis.get("eval_latent_drift", 0.0) or eval_kpis.get("latent_drift", 0.0) or 0.0),
        },
        "mcts": {
            "eval_decision_steps": float(eval_kpis.get("xai_decision_steps", 0.0)),
            "eval_policy_confidence_mean": float(eval_kpis.get("xai_policy_confidence_mean", 0.0)),
            "eval_policy_margin_mean": float(eval_kpis.get("xai_policy_margin_mean", 0.0)),
            "eval_latent_signal_coverage": float(eval_kpis.get("xai_latent_signal_coverage", 0.0)),
            "eval_reaction_window_count": float(eval_kpis.get("reaction_window_count", 0.0)),
            "eval_melee_attempts": float(eval_kpis.get("melee_attempts", 0.0)),
        },
        "threat_map": {
            "train_threat_loss": float(train_summary.get("aux_threat_loss", 0.0) or train_summary.get("threat_loss", 0.0) or 0.0),
            "threat_coverage_ratio": float(eval_kpis.get("threat_coverage_ratio", 0.0)),
            "max_threat": float(eval_kpis.get("threat_max", 0.0)),
            "mean_threat": float(eval_kpis.get("threat_mean", 0.0)),
        },
        "final_ownership": {
            "train_final_ownership_loss": float(train_summary.get("aux_final_ownership_loss", 0.0) or train_summary.get("final_ownership_loss", 0.0) or 0.0),
            "eval_ownership_mae": float(eval_kpis.get("final_ownership_mae", 0.0) or eval_kpis.get("ownership_mae", 0.0) or 0.0),
            "territory_control_score": float(eval_kpis.get("territory_control_score", 0.0) or 0.0),
        },
        "attrition": {
            "train_attrition_loss": float(train_summary.get("aux_attrition_loss", 0.0) or train_summary.get("attrition_loss", 0.0) or 0.0),
            "predicted_exchange_ratio": float(eval_kpis.get("predicted_exchange_ratio", 0.0)),
            "predicted_friendly_casualties": float(eval_kpis.get("predicted_friendly_casualties", 0.0)),
            "predicted_enemy_casualties": float(eval_kpis.get("predicted_enemy_casualties", 0.0)),
            "casualty_prediction_error_mae": float(eval_kpis.get("casualty_prediction_error_mae", 0.0) or eval_kpis.get("casualty_prediction_error", 0.0) or 0.0),
        },
        "morale": {
            "train_morale_loss": float(train_summary.get("aux_morale_loss", 0.0) or train_summary.get("morale_loss", 0.0) or 0.0),
            "suppression_risk_score": float(eval_kpis.get("suppression_risk_score", 0.0)),
            "suppression_accuracy": float(eval_kpis.get("suppression_accuracy", 0.0) or 0.0),
        },
        "macro_intent": {
            "train_intent_loss": float(train_summary.get("aux_intent_loss", 0.0) or 0.0),
            "eval_intent_accuracy": float(eval_kpis.get("macro_intent_accuracy", 0.0) or eval_kpis.get("intent_accuracy", 0.0) or 0.0),
        },
        "multi_vp": {
            "train_multi_vp_loss": float(train_summary.get("aux_multi_vp_loss", 0.0) or 0.0),
            "eval_multi_vp_mae": float(eval_kpis.get("multi_vp_mae", 0.0) or 0.0),
        },
        "source": {"train": "metrics/summary.json", "eval": "bench.phase_2_9_eval_kpis + benchmark results"},
    }


def build_phase29_promotion_gate(
    *,
    train_kpis: Dict[str, float],
    eval_kpis: Dict[str, float],
    muzero_row: Dict,
    baseline_row: Dict,
) -> Dict[str, object]:
    def _tracked_capture_direction(metric_name: str) -> str:
        metric = str(metric_name or "").strip().lower()
        if metric in {"objectives_captured", "vp_captured", "captured"}:
            return "higher_is_better"
        return "higher_is_better"

    eval_reaction_windows = float(eval_kpis.get("reaction_window_count", 0.0))
    eval_reaction_events = float(eval_kpis.get("reaction_fire_count", 0.0)) + float(eval_kpis.get("reaction_fire_skipped_count", 0.0))
    reaction_contract_pass = ((eval_reaction_events <= eval_reaction_windows) if eval_reaction_windows > 0.0 else (eval_reaction_events == 0.0))
    assault_usage_non_zero = float(eval_kpis.get("melee_attempts", 0.0)) > 0.0
    tracked_side = str(muzero_row.get("tracked_side", "") or "").strip()
    tracked_metric = str(muzero_row.get("tracked_metric", "") or "").strip()
    winner_counts = dict(muzero_row.get("winner_side_counts", {}) or {})
    dominant_winner_side = str(max(winner_counts.items(), key=lambda kv: int(kv[1]))[0]) if winner_counts else ""
    muzero_captured = float(muzero_row.get("tracked_captured_avg", 0.0))
    baseline_captured = float(baseline_row.get("tracked_captured_avg", 0.0))
    tracked_capture_direction = _tracked_capture_direction(tracked_metric)
    capture_conversion_no_regression = (muzero_captured >= baseline_captured) if tracked_capture_direction == "higher_is_better" else (muzero_captured <= baseline_captured)
    eval_loss_rate = 1.0 - float(muzero_row.get("win_rate", 0.0))
    baseline_loss_rate = 1.0 - float(baseline_row.get("win_rate", 0.0))
    loss_rate_no_regression = eval_loss_rate <= baseline_loss_rate + 1e-9
    melee_attempt_rate = float(eval_kpis.get("melee_attempts", 0.0)) / float(max(1.0, float(eval_reaction_windows) + float(eval_kpis.get("melee_attempts", 0.0))))
    melee_success_rate = float(eval_kpis.get("melee_success_rate", 0.0))
    assault_misuse_block = bool(melee_attempt_rate > 0.15 and melee_success_rate < 0.20)
    reaction_failfast_block = bool(
        float(eval_kpis.get("reaction_fire_activation_rate", 0.0)) > _phase29_value(train_kpis, "reaction_fire_activation_rate")
        and float(muzero_row.get("win_rate", 0.0)) < float(baseline_row.get("win_rate", 0.0))
    )
    checks = {
        "reaction_contract_pass": bool(reaction_contract_pass),
        "capture_conversion_after_contact_no_regression": bool(capture_conversion_no_regression),
        "loss_rate_no_regression": bool(loss_rate_no_regression),
        "reaction_failfast_block": bool(not reaction_failfast_block),
    }
    return {
        "status": "PASS" if all(bool(v) for v in checks.values()) else "FAIL",
        "checks": checks,
        "advisory": {"assault_usage_non_zero": bool(assault_usage_non_zero), "assault_misuse_block": bool(not assault_misuse_block)},
        "promotion_mode": "vp_first",
        "tracked_capture_direction": tracked_capture_direction,
        "tracked_side": tracked_side,
        "tracked_metric": tracked_metric,
        "dominant_winner_side": dominant_winner_side,
        "muzero_tracked_captured_avg": float(muzero_captured),
        "baseline_tracked_captured_avg": float(baseline_captured),
        "eval_loss_rate": float(eval_loss_rate),
        "baseline_loss_rate": float(baseline_loss_rate),
        "melee_attempt_rate_proxy": float(melee_attempt_rate),
    }
