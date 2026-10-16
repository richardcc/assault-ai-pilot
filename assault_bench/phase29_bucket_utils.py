from __future__ import annotations

from typing import Dict


def new_phase29_bucket() -> Dict[str, float]:
    return {
        "reaction_window_count": 0,
        "reaction_fire_count": 0,
        "reaction_fire_skipped_count": 0,
        "reaction_fire_kill_conversions": 0,
        "reaction_fire_damage_sum": 0.0,
        "melee_attempts": 0,
        "melee_success_count": 0,
        "melee_kills_sum": 0.0,
        "melee_damage_sum": 0.0,
        "assault_favorable_count": 0,
        "assault_unfavorable_count": 0,
        "converted_from_progress_rate": 0.0,
        "converted_rate_near_vp": 0.0,
        "conversion_within_2_turns_after_progress": 0.0,
        "xai_decision_steps": 0,
        "xai_policy_confidence_sum": 0.0,
        "xai_policy_margin_sum": 0.0,
        "xai_latent_signal_steps": 0,
        "xai_vp_capture_opportunity_steps": 0,
        "xai_vp_capture_taken_steps": 0,
        "xai_vp_immediate_capture_opportunity_steps": 0,
        "xai_vp_immediate_capture_taken_steps": 0,
    }


def finalize_phase29(bucket: Dict[str, float]) -> Dict[str, float]:
    reaction_den = max(1, int(bucket["reaction_fire_count"] + bucket["reaction_fire_skipped_count"]))
    melee_den = max(1, int(bucket["melee_attempts"]))
    xai_den = max(1, int(bucket["xai_decision_steps"]))
    xai_cap_den = max(1, int(bucket["xai_vp_capture_opportunity_steps"]))
    xai_immediate_cap_den = max(1, int(bucket["xai_vp_immediate_capture_opportunity_steps"]))
    return {
        "reaction_window_count": int(bucket["reaction_window_count"]),
        "reaction_fire_count": int(bucket["reaction_fire_count"]),
        "reaction_fire_skipped_count": int(bucket["reaction_fire_skipped_count"]),
        "reaction_fire_kill_conversions": int(bucket["reaction_fire_kill_conversions"]),
        "reaction_fire_damage_sum": float(bucket["reaction_fire_damage_sum"]),
        "reaction_fire_activation_rate": (float(bucket["reaction_fire_count"]) / float(reaction_den)),
        "reaction_fire_kill_conversion_rate": (
            float(bucket["reaction_fire_kill_conversions"]) / float(max(1, int(bucket["reaction_fire_count"])))
        ),
        "reaction_fire_damage_induced_proxy": (
            float(bucket["reaction_fire_damage_sum"]) / float(max(1, int(bucket["reaction_fire_count"])))
        ),
        "reaction_fire_damage_prevented_proxy": (
            float(bucket["reaction_fire_kill_conversions"]) / float(max(1, int(bucket["reaction_fire_count"])))
        ),
        "assault_melee_action_family_count": int(bucket["melee_attempts"]),
        "melee_attempts": int(bucket["melee_attempts"]),
        "melee_success_count": int(bucket["melee_success_count"]),
        "melee_kills_sum": float(bucket["melee_kills_sum"]),
        "melee_damage_sum": float(bucket["melee_damage_sum"]),
        "melee_success_rate": (float(bucket["melee_success_count"]) / float(melee_den)),
        "melee_kills_per_attempt": (float(bucket["melee_kills_sum"]) / float(melee_den)),
        "melee_damage_per_attempt": (float(bucket["melee_damage_sum"]) / float(melee_den)),
        "assault_favorable_count": int(bucket["assault_favorable_count"]),
        "assault_unfavorable_count": int(bucket["assault_unfavorable_count"]),
        "converted_from_progress_rate": float(bucket["converted_from_progress_rate"]),
        "converted_rate_near_vp": float(bucket["converted_rate_near_vp"]),
        "conversion_within_2_turns_after_progress": float(bucket["conversion_within_2_turns_after_progress"]),
        "xai_decision_steps": int(bucket["xai_decision_steps"]),
        "xai_policy_confidence_mean": (float(bucket["xai_policy_confidence_sum"]) / float(xai_den)),
        "xai_policy_margin_mean": (float(bucket["xai_policy_margin_sum"]) / float(xai_den)),
        "xai_latent_signal_coverage": (float(bucket["xai_latent_signal_steps"]) / float(xai_den)),
        "xai_vp_capture_opportunity_steps": int(bucket["xai_vp_capture_opportunity_steps"]),
        "xai_vp_capture_taken_steps": int(bucket["xai_vp_capture_taken_steps"]),
        "xai_vp_capture_take_rate": (
            float(bucket["xai_vp_capture_taken_steps"]) / float(xai_cap_den)
        ),
        "xai_vp_immediate_capture_opportunity_steps": int(bucket["xai_vp_immediate_capture_opportunity_steps"]),
        "xai_vp_immediate_capture_taken_steps": int(bucket["xai_vp_immediate_capture_taken_steps"]),
        "xai_vp_immediate_capture_take_rate": (
            float(bucket["xai_vp_immediate_capture_taken_steps"]) / float(xai_immediate_cap_den)
        ),
    }
