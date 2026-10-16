from __future__ import annotations

from typing import Dict, List

from assault_bench.columnar_pass import aggregate_columns_mean, aggregate_columns_sum

def _rate(num: float, den: float):
    return (float(num) / float(den)) if float(den) > 0.0 else None


def _weighted_mean(value_sum_weighted: float, weight_sum: float):
    return (float(value_sum_weighted) / float(weight_sum)) if float(weight_sum) > 0.0 else None


def build_phase29_eval_kpis_by_side_from_seed_rows(
    phase29_seed_rows_by_side: List[Dict[str, Dict[str, float]]],
) -> Dict[str, Dict[str, float]]:
    side_rows: Dict[str, List[Dict[str, float]]] = {}
    for row in list(phase29_seed_rows_by_side or []):
        rr = dict(row or {})
        for side, payload in rr.items():
            side_key = str(side)
            side_rows.setdefault(side_key, []).append(dict(payload or {}))

    out: Dict[str, Dict[str, float]] = {}
    for side in sorted(side_rows.keys()):
        rows = list(side_rows.get(side, []))
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
            "vp_approach_rate_eligible_steps",
            "vp_approach_rate_positive_steps",
            "vp_regret_delta_count",
            "q_saturation_candidate_rows",
            "q_saturation_hits",
            "decision_spread_step_count",
            "path_to_capture_length_count",
            "opportunity_conversion_early_opportunity_steps",
            "opportunity_conversion_early_converted_steps",
            "opportunity_conversion_mid_opportunity_steps",
            "opportunity_conversion_mid_converted_steps",
            "opportunity_conversion_late_opportunity_steps",
            "opportunity_conversion_late_converted_steps",
        ]
        sum_keys = ["reaction_fire_damage_sum", "melee_kills_sum", "melee_damage_sum"]
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
            "vp_regret_delta_p95",
            "decision_spread_p50",
            "decision_spread_p95",
            "path_to_capture_length_p95",
        ]
        counts = aggregate_columns_sum(rows, count_keys)
        sums = aggregate_columns_sum(rows, sum_keys)
        means = aggregate_columns_mean(rows, mean_keys)
        vp_regret_wsum = float(
            sum(float(dict(r).get("vp_regret_delta_mean", 0.0) or 0.0) * float(dict(r).get("vp_regret_delta_count", 0.0) or 0.0) for r in rows)
        )
        spread_wsum = float(
            sum(float(dict(r).get("decision_spread_mean", 0.0) or 0.0) * float(dict(r).get("decision_spread_step_count", 0.0) or 0.0) for r in rows)
        )
        path_wsum = float(
            sum(float(dict(r).get("path_to_capture_length_mean", 0.0) or 0.0) * float(dict(r).get("path_to_capture_length_count", 0.0) or 0.0) for r in rows)
        )
        out[side] = {
            **{k: int(counts[k]) for k in count_keys},
            **{k: float(sums[k]) for k in sum_keys},
            **{k: float(means[k]) for k in mean_keys},
            "vp_approach_rate": _rate(
                counts["vp_approach_rate_positive_steps"],
                counts["vp_approach_rate_eligible_steps"],
            ),
            "vp_regret_delta_mean": _weighted_mean(vp_regret_wsum, counts["vp_regret_delta_count"]),
            "q_saturation_rate": _rate(counts["q_saturation_hits"], counts["q_saturation_candidate_rows"]),
            "decision_spread_mean": _weighted_mean(spread_wsum, counts["decision_spread_step_count"]),
            "path_to_capture_length_mean": _weighted_mean(path_wsum, counts["path_to_capture_length_count"]),
            "opportunity_conversion_early_rate": _rate(
                counts["opportunity_conversion_early_converted_steps"],
                counts["opportunity_conversion_early_opportunity_steps"],
            ),
            "opportunity_conversion_mid_rate": _rate(
                counts["opportunity_conversion_mid_converted_steps"],
                counts["opportunity_conversion_mid_opportunity_steps"],
            ),
            "opportunity_conversion_late_rate": _rate(
                counts["opportunity_conversion_late_converted_steps"],
                counts["opportunity_conversion_late_opportunity_steps"],
            ),
            "opportunity_conversion_turn_buckets_definition": "early: turn<=3, mid: turn 4-7, late: turn>=8",
        }
    return out
