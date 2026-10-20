from __future__ import annotations

from typing import Dict, List

from assault_bench.columnar_pass import (
    aggregate_columns_mean,
    aggregate_columns_sum,
    aggregate_columns_weighted_mean,
)
from assault_bench.transform_ops import filter_rows, to_dict_rows

def _sum_kpi_keys(rows: List[Dict], keys: List[str]) -> Dict[str, float]:
    nested_rows = [
        dict(dict(r or {}).get("phase_2_9_eval_kpis", {}) or {})
        for r in to_dict_rows(rows)
    ]
    return aggregate_columns_sum(nested_rows, keys)


def _weighted_mean_kpi_keys(rows: List[Dict], keys: List[str]) -> Dict[str, float]:
    weighted_rows = [
        {
            **dict(dict(r or {}).get("phase_2_9_eval_kpis", {}) or {}),
            "episodes_weight": float(max(1, int(dict(r or {}).get("episodes", 0) or 0))),
        }
        for r in to_dict_rows(rows)
    ]
    return aggregate_columns_weighted_mean(
        weighted_rows,
        value_keys=keys,
        weight_key="episodes_weight",
    )


def aggregate_muzero_eval_kpis(result_rows: List[Dict]) -> Dict[str, float]:
    agent_rows = filter_rows(
        to_dict_rows(result_rows),
        lambda r: str(r.get("agent_name", "")).startswith("ezv2") or str(r.get("agent_name", "")).startswith("muzero"),
    )
    if not agent_rows:
        return {}
    count_keys = [
        "reaction_window_count",
        "reaction_fire_count",
        "reaction_fire_skipped_count",
        "reaction_fire_kill_conversions",
        "reaction_fire_damage_sum",
        "assault_melee_action_family_count",
        "melee_attempts",
        "melee_success_count",
        "melee_kills_sum",
        "melee_damage_sum",
        "assault_favorable_count",
        "assault_unfavorable_count",
        "xai_decision_steps",
        "xai_vp_capture_opportunity_steps",
        "xai_vp_capture_taken_steps",
        "xai_vp_immediate_capture_opportunity_steps",
        "xai_vp_immediate_capture_taken_steps",
        "vp_approach_rate_eligible_steps",
        "vp_approach_rate_positive_steps",
        "vp_regret_delta_count",
        "q_saturation_candidate_rows",
        "q_saturation_hits",
        "decision_spread_step_count",
        "path_to_capture_length_count",
        "vp_progress_observed_count",
        "vp_progress_estimated_count",
        "vp_progress_available_count",
        "vp_progress_missing_count",
        "vp_progress_zero_count",
        "tie_break_present_count",
        "tie_break_zero_count",
        "opportunity_conversion_early_opportunity_steps",
        "opportunity_conversion_early_converted_steps",
        "opportunity_conversion_mid_opportunity_steps",
        "opportunity_conversion_mid_converted_steps",
        "opportunity_conversion_late_opportunity_steps",
        "opportunity_conversion_late_converted_steps",
        "recon_initial_count",
        "recon_final_alive",
        "fire_support_total_actions",
        "fire_support_stationary_actions",
        "vp_captures_total",
        "spearhead_vp_captures",
        "total_decisions",
        "boosted_decisions",
        "total_unit_steps",
        "mutated_unit_steps",
    ]
    rate_keys = [
        "reaction_fire_activation_rate",
        "reaction_fire_kill_conversion_rate",
        "reaction_fire_damage_induced_proxy",
        "reaction_fire_damage_prevented_proxy",
        "melee_success_rate",
        "melee_kills_per_attempt",
        "melee_damage_per_attempt",
        "converted_from_progress_rate",
        "converted_rate_near_vp",
        "conversion_within_2_turns_after_progress",
        "xai_policy_confidence_mean",
        "xai_policy_margin_mean",
        "xai_latent_signal_coverage",
        "xai_vp_capture_take_rate",
        "xai_vp_immediate_capture_take_rate",
        "vp_approach_rate",
        "vp_regret_delta_mean",
        "vp_regret_delta_p95",
        "q_saturation_rate",
        "decision_spread_mean",
        "decision_spread_p50",
        "decision_spread_p95",
        "vp_progress_observed_rate",
        "vp_progress_estimated_rate",
        "vp_progress_available_rate",
        "vp_progress_zero_rate",
        "tie_break_present_rate",
        "tie_break_zero_rate",
        "path_to_capture_length_mean",
        "path_to_capture_length_p95",
        "opportunity_conversion_early_rate",
        "opportunity_conversion_mid_rate",
        "opportunity_conversion_late_rate",
        "threat_coverage_ratio",
        "threat_max",
        "threat_mean",
        "predicted_exchange_ratio",
        "predicted_friendly_casualties",
        "predicted_enemy_casualties",
        "suppression_risk_score",
        "objective_pred_prob",
        "recon_survival_rate",
        "fire_support_stationarity",
        "spearhead_vp_capture_rate",
        "doctrine_adherence_rate",
        "doctrine_mutation_rate",
    ]
    out: Dict[str, float] = {}
    out.update(_sum_kpi_keys(agent_rows, count_keys))
    out.update(_weighted_mean_kpi_keys(agent_rows, rate_keys))
    return out


def build_phase29_eval_kpis_from_seed_rows(
    phase29_seed_rows: List[Dict[str, object]],
) -> Dict[str, object]:
    rows = to_dict_rows(phase29_seed_rows)
    count_keys = [
        "reaction_window_count",
        "reaction_fire_count",
        "reaction_fire_skipped_count",
        "reaction_fire_kill_conversions",
        "assault_melee_action_family_count",
        "melee_attempts",
        "melee_success_count",
        "assault_favorable_count",
        "assault_unfavorable_count",
        "xai_decision_steps",
        "xai_vp_capture_opportunity_steps",
        "xai_vp_capture_taken_steps",
        "xai_vp_immediate_capture_opportunity_steps",
        "xai_vp_immediate_capture_taken_steps",
        "opportunity_conversion_early_opportunity_steps",
        "opportunity_conversion_early_converted_steps",
        "opportunity_conversion_mid_opportunity_steps",
        "opportunity_conversion_mid_converted_steps",
        "opportunity_conversion_late_opportunity_steps",
        "opportunity_conversion_late_converted_steps",
        "recon_initial_count",
        "recon_final_alive",
        "fire_support_total_actions",
        "fire_support_stationary_actions",
        "vp_captures_total",
        "spearhead_vp_captures",
        "total_decisions",
        "boosted_decisions",
        "total_unit_steps",
        "mutated_unit_steps",
    ]
    mean_keys = [
        "reaction_fire_activation_rate",
        "reaction_fire_kill_conversion_rate",
        "reaction_fire_damage_induced_proxy",
        "reaction_fire_damage_prevented_proxy",
        "melee_success_rate",
        "melee_kills_per_attempt",
        "melee_damage_per_attempt",
        "xai_policy_confidence_mean",
        "xai_policy_margin_mean",
        "xai_latent_signal_coverage",
        "xai_vp_capture_take_rate",
        "xai_vp_immediate_capture_take_rate",
        "threat_coverage_ratio",
        "threat_max",
        "threat_mean",
        "predicted_exchange_ratio",
        "predicted_friendly_casualties",
        "predicted_enemy_casualties",
        "suppression_risk_score",
        "objective_pred_prob",
        "recon_survival_rate",
        "fire_support_stationarity",
        "spearhead_vp_capture_rate",
        "doctrine_adherence_rate",
        "doctrine_mutation_rate",
    ]
    sum_keys = [
        "reaction_fire_damage_sum",
        "melee_kills_sum",
        "melee_damage_sum",
    ]
    counts = aggregate_columns_sum(rows, count_keys)
    means = aggregate_columns_mean(rows, mean_keys)
    sums = aggregate_columns_sum(rows, sum_keys)
    opp_early = int(counts["opportunity_conversion_early_opportunity_steps"])
    conv_early = int(counts["opportunity_conversion_early_converted_steps"])
    opp_mid = int(counts["opportunity_conversion_mid_opportunity_steps"])
    conv_mid = int(counts["opportunity_conversion_mid_converted_steps"])
    opp_late = int(counts["opportunity_conversion_late_opportunity_steps"])
    conv_late = int(counts["opportunity_conversion_late_converted_steps"])
    return {
        "reaction_window_count": int(counts["reaction_window_count"]),
        "reaction_fire_count": int(counts["reaction_fire_count"]),
        "reaction_fire_skipped_count": int(counts["reaction_fire_skipped_count"]),
        "reaction_fire_kill_conversions": int(counts["reaction_fire_kill_conversions"]),
        "reaction_fire_damage_sum": float(sums["reaction_fire_damage_sum"]),
        "reaction_fire_activation_rate": float(means["reaction_fire_activation_rate"]),
        "reaction_fire_kill_conversion_rate": float(means["reaction_fire_kill_conversion_rate"]),
        "reaction_fire_damage_induced_proxy": float(means["reaction_fire_damage_induced_proxy"]),
        "reaction_fire_damage_prevented_proxy": float(means["reaction_fire_damage_prevented_proxy"]),
        "assault_melee_action_family_count": int(counts["assault_melee_action_family_count"]),
        "melee_attempts": int(counts["melee_attempts"]),
        "melee_success_count": int(counts["melee_success_count"]),
        "melee_kills_sum": float(sums["melee_kills_sum"]),
        "melee_damage_sum": float(sums["melee_damage_sum"]),
        "melee_success_rate": float(means["melee_success_rate"]),
        "melee_kills_per_attempt": float(means["melee_kills_per_attempt"]),
        "melee_damage_per_attempt": float(means["melee_damage_per_attempt"]),
        "assault_favorable_count": int(counts["assault_favorable_count"]),
        "assault_unfavorable_count": int(counts["assault_unfavorable_count"]),
        "xai_decision_steps": int(counts["xai_decision_steps"]),
        "xai_vp_capture_opportunity_steps": int(counts["xai_vp_capture_opportunity_steps"]),
        "xai_vp_capture_taken_steps": int(counts["xai_vp_capture_taken_steps"]),
        "xai_vp_immediate_capture_opportunity_steps": int(counts["xai_vp_immediate_capture_opportunity_steps"]),
        "xai_vp_immediate_capture_taken_steps": int(counts["xai_vp_immediate_capture_taken_steps"]),
        "xai_policy_confidence_mean": float(means["xai_policy_confidence_mean"]),
        "xai_policy_margin_mean": float(means["xai_policy_margin_mean"]),
        "xai_latent_signal_coverage": float(means["xai_latent_signal_coverage"]),
        "xai_vp_capture_take_rate": float(means["xai_vp_capture_take_rate"]),
        "xai_vp_immediate_capture_take_rate": float(means["xai_vp_immediate_capture_take_rate"]),
        "threat_coverage_ratio": float(means.get("threat_coverage_ratio", 0.0)),
        "threat_max": float(means.get("threat_max", 0.0)),
        "threat_mean": float(means.get("threat_mean", 0.0)),
        "predicted_exchange_ratio": float(means.get("predicted_exchange_ratio", 0.0)),
        "predicted_friendly_casualties": float(means.get("predicted_friendly_casualties", 0.0)),
        "predicted_enemy_casualties": float(means.get("predicted_enemy_casualties", 0.0)),
        "suppression_risk_score": float(means.get("suppression_risk_score", 0.0)),
        "objective_pred_prob": float(means.get("objective_pred_prob", 0.0)),
        "opportunity_conversion_early_opportunity_steps": opp_early,
        "opportunity_conversion_early_converted_steps": conv_early,
        "opportunity_conversion_early_rate": (
            float(conv_early) / float(opp_early) if opp_early > 0 else None
        ),
        "opportunity_conversion_mid_opportunity_steps": opp_mid,
        "opportunity_conversion_mid_converted_steps": conv_mid,
        "opportunity_conversion_mid_rate": (
            float(conv_mid) / float(opp_mid) if opp_mid > 0 else None
        ),
        "opportunity_conversion_late_opportunity_steps": opp_late,
        "opportunity_conversion_late_converted_steps": conv_late,
        "opportunity_conversion_late_rate": (
            float(conv_late) / float(opp_late) if opp_late > 0 else None
        ),
        "recon_survival_rate": float(means.get("recon_survival_rate", 1.0)),
        "fire_support_stationarity": float(means.get("fire_support_stationarity", 1.0)),
        "spearhead_vp_capture_rate": float(means.get("spearhead_vp_capture_rate", 0.0)),
        "doctrine_adherence_rate": float(means.get("doctrine_adherence_rate", 0.0)),
        "doctrine_mutation_rate": float(means.get("doctrine_mutation_rate", 0.0)),
    }
