from __future__ import annotations

from typing import Dict, List


def _safe_float0(v: object) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0


def _safe_int0(v: object) -> int:
    try:
        if v is None:
            return 0
        return int(v)
    except Exception:
        return 0


def build_phase29_eval_kpis_by_side(
    phase29_seed_rows_by_side: List[Dict[str, object]],
) -> Dict[str, Dict[str, object]]:
    return {
        side: {
            "reaction_window_count": int(
                sum(int((r.get(side, {}) or {}).get("reaction_window_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "reaction_fire_count": int(
                sum(int((r.get(side, {}) or {}).get("reaction_fire_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "reaction_fire_skipped_count": int(
                sum(int((r.get(side, {}) or {}).get("reaction_fire_skipped_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "reaction_fire_kill_conversions": int(
                sum(int((r.get(side, {}) or {}).get("reaction_fire_kill_conversions", 0)) for r in phase29_seed_rows_by_side)
            ),
            "reaction_fire_damage_sum": float(
                sum(_safe_float0((r.get(side, {}) or {}).get("reaction_fire_damage_sum", 0.0)) for r in phase29_seed_rows_by_side)
            ),
            "reaction_fire_activation_rate": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("reaction_fire_activation_rate", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "reaction_fire_kill_conversion_rate": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("reaction_fire_kill_conversion_rate", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "reaction_fire_damage_induced_proxy": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("reaction_fire_damage_induced_proxy", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "reaction_fire_damage_prevented_proxy": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("reaction_fire_damage_prevented_proxy", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "assault_melee_action_family_count": int(
                sum(int((r.get(side, {}) or {}).get("assault_melee_action_family_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "melee_attempts": int(
                sum(int((r.get(side, {}) or {}).get("melee_attempts", 0)) for r in phase29_seed_rows_by_side)
            ),
            "melee_success_count": int(
                sum(int((r.get(side, {}) or {}).get("melee_success_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "melee_kills_sum": float(
                sum(_safe_float0((r.get(side, {}) or {}).get("melee_kills_sum", 0.0)) for r in phase29_seed_rows_by_side)
            ),
            "melee_damage_sum": float(
                sum(_safe_float0((r.get(side, {}) or {}).get("melee_damage_sum", 0.0)) for r in phase29_seed_rows_by_side)
            ),
            "melee_success_rate": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("melee_success_rate", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "melee_kills_per_attempt": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("melee_kills_per_attempt", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "melee_damage_per_attempt": (
                float(
                    sum(_safe_float0((r.get(side, {}) or {}).get("melee_damage_per_attempt", 0.0)) for r in phase29_seed_rows_by_side)
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "assault_favorable_count": int(
                sum(int((r.get(side, {}) or {}).get("assault_favorable_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "assault_unfavorable_count": int(
                sum(int((r.get(side, {}) or {}).get("assault_unfavorable_count", 0)) for r in phase29_seed_rows_by_side)
            ),
            "xai_decision_steps": int(
                sum(int((r.get(side, {}) or {}).get("xai_decision_steps", 0)) for r in phase29_seed_rows_by_side)
            ),
            "xai_vp_capture_opportunity_steps": int(
                sum(
                    int((r.get(side, {}) or {}).get("xai_vp_capture_opportunity_steps", 0))
                    for r in phase29_seed_rows_by_side
                )
            ),
            "xai_vp_capture_taken_steps": int(
                sum(
                    int((r.get(side, {}) or {}).get("xai_vp_capture_taken_steps", 0))
                    for r in phase29_seed_rows_by_side
                )
            ),
            "xai_vp_immediate_capture_opportunity_steps": int(
                sum(
                    int((r.get(side, {}) or {}).get("xai_vp_immediate_capture_opportunity_steps", 0))
                    for r in phase29_seed_rows_by_side
                )
            ),
            "xai_vp_immediate_capture_taken_steps": int(
                sum(
                    int((r.get(side, {}) or {}).get("xai_vp_immediate_capture_taken_steps", 0))
                    for r in phase29_seed_rows_by_side
                )
            ),
            "xai_policy_confidence_mean": (
                float(
                    sum(
                        _safe_float0((r.get(side, {}) or {}).get("xai_policy_confidence_mean", 0.0))
                        for r in phase29_seed_rows_by_side
                    )
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "xai_policy_margin_mean": (
                float(
                    sum(
                        _safe_float0((r.get(side, {}) or {}).get("xai_policy_margin_mean", 0.0))
                        for r in phase29_seed_rows_by_side
                    )
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "xai_latent_signal_coverage": (
                float(
                    sum(
                        _safe_float0((r.get(side, {}) or {}).get("xai_latent_signal_coverage", 0.0))
                        for r in phase29_seed_rows_by_side
                    )
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "xai_vp_capture_take_rate": (
                float(
                    sum(
                        _safe_float0((r.get(side, {}) or {}).get("xai_vp_capture_take_rate", 0.0))
                        for r in phase29_seed_rows_by_side
                    )
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "xai_vp_immediate_capture_take_rate": (
                float(
                    sum(
                        _safe_float0((r.get(side, {}) or {}).get("xai_vp_immediate_capture_take_rate", 0.0))
                        for r in phase29_seed_rows_by_side
                    )
                )
                / float(max(1, len(phase29_seed_rows_by_side)))
            ),
            "opportunity_conversion_turn_buckets_definition": "early: turn<=3, mid: turn 4-7, late: turn>=8",
        }
        for side in sorted(
            {
                str(side)
                for r in phase29_seed_rows_by_side
                for side in (r or {}).keys()
            }
        )
    }
