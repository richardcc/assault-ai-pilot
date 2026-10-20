from __future__ import annotations

import math
from typing import Dict, List, Optional

from assault_bench.decision_candidate_utils import canonicalize_decision_candidates
from assault_bench.transform_ops import map_rows, to_dict_rows


def metric_from_row(row: Dict[str, object], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key not in row:
            continue
        raw = row.get(key, None)
        if raw is None:
            continue
        try:
            return float(raw)
        except Exception:
            continue
    return float(default)


def extract_actor_combat_dice_signals(
    *,
    transition_info: Optional[object],
    acting_unit_id: str,
) -> tuple[list[dict], list[dict], dict[str, int], dict[str, int], list[dict]]:
    info = dict(transition_info or {})
    runtime_events = to_dict_rows(info.get("runtime_events", []))
    attack_dice_rolls: list[dict] = []
    defense_dice_rolls: list[dict] = []
    attack_components: dict[str, int] = {}
    defense_components: dict[str, int] = {}
    for evt_dict in runtime_events:
        if str(evt_dict.get("type", "")) != "ACTION_EFFECT":
            continue
        payload_evt = dict(evt_dict.get("payload", {}) or {})
        attacker_evt = str(payload_evt.get("attacker", "")).strip()
        if attacker_evt and attacker_evt != str(acting_unit_id or ""):
            continue
        for dd in to_dict_rows(payload_evt.get("attacker_attack_dice", [])):
            faces = [str(x) for x in (list(dd.get("faces", []) or []))]
            attack_dice_rolls.append({"side": "attack", "color": str(dd.get("color", "")), "faces": list(faces)})
            for face in faces:
                key = str(face).strip().upper()
                if not key:
                    continue
                attack_components[key] = int(attack_components.get(key, 0)) + 1
        for dd in to_dict_rows(payload_evt.get("defender_defense_dice", [])):
            faces = [str(x) for x in (list(dd.get("faces", []) or []))]
            defense_dice_rolls.append({"side": "defense", "color": str(dd.get("color", "")), "faces": list(faces)})
            for face in faces:
                key = str(face).strip().upper()
                if not key:
                    continue
                defense_components[key] = int(defense_components.get(key, 0)) + 1
    return (
        list(attack_dice_rolls),
        list(defense_dice_rolls),
        dict(attack_components),
        dict(defense_components),
        list(runtime_events),
    )


def extract_actor_damage_kills_from_runtime_events(
    *,
    runtime_events: List[object],
    acting_unit_id: str,
) -> tuple[float, int]:
    damage_dealt = 0.0
    kills_dealt = 0
    actor_id = str(acting_unit_id or "").strip()
    for evt_dict in to_dict_rows(runtime_events):
        if str(evt_dict.get("type", "")) != "ACTION_EFFECT":
            continue
        payload_evt = dict(evt_dict.get("payload", {}) or {})
        attacker_evt = str(payload_evt.get("attacker", "")).strip()
        if attacker_evt and actor_id and attacker_evt != actor_id:
            continue

        attacker_effects = dict(payload_evt.get("attacker_effects", {}) or {})
        if "damage" in attacker_effects:
            try:
                damage_dealt += max(0.0, float(attacker_effects.get("damage", 0.0) or 0.0))
            except Exception:
                pass
        if bool(payload_evt.get("defender_killed", False)):
            kills_dealt += 1

        for rr in to_dict_rows(payload_evt.get("rounds", [])):
            rr_attacker_effects = dict(rr.get("attacker_effects", {}) or {})
            if "damage" in rr_attacker_effects:
                try:
                    damage_dealt += max(0.0, float(rr_attacker_effects.get("damage", 0.0) or 0.0))
                except Exception:
                    pass
            else:
                try:
                    hp_before = float(rr.get("defender_hp_before", 0.0) or 0.0)
                    hp_after = float(rr.get("defender_hp_after", hp_before) or hp_before)
                    damage_dealt += max(0.0, hp_before - hp_after)
                except Exception:
                    pass
            try:
                hp_before = float(rr.get("defender_hp_before", 0.0) or 0.0)
                hp_after = float(rr.get("defender_hp_after", hp_before) or hp_before)
                if hp_before > 0.0 and hp_after <= 0.0:
                    kills_dealt += 1
            except Exception:
                pass
    return float(damage_dealt), int(kills_dealt)


def extract_unit_suppressed_from_runtime_events(runtime_events: List[object]) -> Dict[str, bool]:
    out: Dict[str, bool] = {}

    def _read_bool(value: object) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        txt = str(value).strip().lower()
        if txt in {"1", "true", "yes", "y", "on"}:
            return True
        if txt in {"0", "false", "no", "n", "off"}:
            return False
        return None

    for evt_dict in to_dict_rows(runtime_events):
        payload_evt = dict(evt_dict.get("payload", {}) or {})
        rows = [payload_evt] if payload_evt else [evt_dict]
        for row in rows:
            for unit_key, state_key in (
                ("attacker", "attacker_suppressed"),
                ("defender", "defender_suppressed"),
                ("attacker_unit_id", "attacker_suppressed"),
                ("defender_unit_id", "defender_suppressed"),
                ("actor_unit_id", "is_suppressed"),
                ("target_unit_id", "is_suppressed"),
            ):
                unit_id = str(row.get(unit_key, "") or "").strip()
                if not unit_id:
                    continue
                raw = row.get(state_key, None)
                if raw is None:
                    raw = row.get("suppressed", row.get("is_suppressed", row.get("pinned", row.get("is_pinned", None))))
                parsed = _read_bool(raw)
                if parsed is not None:
                    out[unit_id] = bool(parsed)
    return out


def build_eval_decision_steps_top(
    trace_rows: List[Dict[str, object]], *, limit: int = 40
) -> List[Dict[str, object]]:
    def _num_or_none(src: Dict[str, object], key: str) -> Optional[float]:
        if key not in src:
            return None
        raw = src.get(key, None)
        if raw is None:
            return None
        try:
            val = float(raw)
        except Exception:
            return None
        return val if math.isfinite(val) else None

    def _int_or_none(src: Dict[str, object], key: str) -> Optional[int]:
        if key not in src:
            return None
        raw = src.get(key, None)
        if raw is None:
            return None
        try:
            return int(raw)
        except Exception:
            return None

    def _str_or_none(src: Dict[str, object], key: str) -> Optional[str]:
        if key not in src:
            return None
        raw = src.get(key, None)
        if raw is None:
            return None
        txt = str(raw).strip()
        return txt if txt else None

    def _normalize_candidate_strict(candidate: Dict[str, object]) -> Dict[str, object]:
        c_out = dict(candidate or {})
        c_out["action_id"] = str(c_out.get("action_id", "") or "")
        c_out["real_decision_score"] = _num_or_none(c_out, "real_decision_score")
        c_out["visit_count"] = _int_or_none(c_out, "visit_count")
        c_out["decision_rank"] = _int_or_none(c_out, "decision_rank")
        c_out["mcts_q_value"] = _num_or_none(c_out, "mcts_q_value")
        c_out["mcts_u_value"] = _num_or_none(c_out, "mcts_u_value")
        c_out["mcts_q_unclipped"] = _num_or_none(c_out, "mcts_q_unclipped")
        c_out["mcts_q_clipped"] = _num_or_none(c_out, "mcts_q_clipped")
        c_out["mcts_q_norm_applied"] = bool(c_out.get("mcts_q_norm_applied", False))
        c_out["policy_prior"] = _num_or_none(c_out, "policy_prior")
        c_out["visit_policy_prob"] = _num_or_none(c_out, "visit_policy_prob")
        c_out["policy_prior_source"] = _str_or_none(c_out, "policy_prior_source")
        c_out["policy_prior_available"] = bool(c_out.get("policy_prior_available", False))
        c_out["mcts_q_value_source"] = _str_or_none(c_out, "mcts_q_value_source")
        c_out["mcts_q_value_available"] = bool(c_out.get("mcts_q_value_available", False))
        c_out["mcts_u_value_source"] = _str_or_none(c_out, "mcts_u_value_source")
        c_out["mcts_u_value_available"] = bool(c_out.get("mcts_u_value_available", False))
        c_out["mcts_success_prob_proxy_source"] = _str_or_none(c_out, "mcts_success_prob_proxy_source")
        c_out["mcts_success_prob_proxy_available"] = bool(
            c_out.get("mcts_success_prob_proxy_available", False)
        )
        c_out["mcts_success_component_source"] = _str_or_none(c_out, "mcts_success_component_source")
        c_out["mcts_success_component_available"] = bool(
            c_out.get("mcts_success_component_available", False)
        )
        c_out["selection_source"] = _str_or_none(c_out, "selection_source")
        c_out["visit_share"] = _num_or_none(c_out, "visit_share")
        c_out["chosen_action_prob"] = _num_or_none(c_out, "chosen_action_prob")
        if not isinstance(c_out.get("decision_components", None), dict):
            c_out["decision_components"] = {}
        else:
            c_out["decision_components"] = dict(c_out.get("decision_components", {}) or {})
        return c_out

    src_rows = to_dict_rows(trace_rows)[: max(1, int(limit or 40))]
    out: List[Dict[str, object]] = []
    for row in src_rows:
        r = dict(row or {})
        chosen_action_id = str(r.get("action_id", "") or "")
        candidates = to_dict_rows(r.get("mcts_action_candidates", []))
        candidates = canonicalize_decision_candidates(
            candidate_rows=list(candidates or []),
            chosen_action_id=chosen_action_id,
            default_policy_prior_zero=False,
        )
        normalized_candidates: List[Dict[str, object]] = map_rows(candidates, _normalize_candidate_strict)
        why = dict(r.get("why_action_vs_vp", {}) or {})
        why_candidates = [dict(c or {}) for c in list(why.get("candidate_actions", []) or [])]
        if not why_candidates and normalized_candidates:
            why_candidates = [dict(c) for c in normalized_candidates]
        else:
            why_candidates = canonicalize_decision_candidates(
                candidate_rows=list(why_candidates or []),
                chosen_action_id=chosen_action_id,
                default_policy_prior_zero=False,
            )
        why["candidate_actions"] = [_normalize_candidate_strict(c) for c in why_candidates]
        out.append(
            {
                "step": int(r.get("step", 0) or 0),
                "game_turn": int(r.get("game_turn", r.get("turn", 0)) or 0),
                "action_id": str(r.get("action_id", "") or ""),
                "action_kind": str(r.get("action_kind", "") or ""),
                "unit_side": str(r.get("unit_side", "") or ""),
                "chosen_action_prob": float(r.get("chosen_action_prob", 0.0) or 0.0),
                "real_decision_score": (
                    float(r.get("real_decision_score", 0.0))
                    if r.get("real_decision_score", None) is not None
                    else None
                ),
                "decision_score_selected": (
                    float(r.get("real_decision_score", 0.0))
                    if r.get("real_decision_score", None) is not None
                    else None
                ),
                "decision_score_selected_source": str(
                    r.get("decision_score_selected_source", "missing") or "missing"
                ),
                "decision_score_selected_available": bool(
                    r.get("decision_score_selected_available", None)
                ),
                "mcts_margin": float(r.get("mcts_margin", 0.0) or 0.0),
                "mcts_total_visits": int(r.get("mcts_total_visits", 0) or 0),
                "mcts_active_actions": int(r.get("mcts_active_actions", 0) or 0),
                "mcts_q_guardrail_clipped_count": int(
                    r.get("mcts_q_guardrail_clipped_count", 0) or 0
                ),
                "mcts_q_clipped_count": int(
                    r.get(
                        "mcts_q_clipped_count",
                        r.get("mcts_q_guardrail_clipped_count", 0),
                    )
                    or 0
                ),
                "mcts_q_clip_denominator_count": int(
                    r.get("mcts_q_clip_denominator_count", r.get("mcts_total_visits", 0))
                    or 0
                ),
                "telemetry_coverage_status": str(
                    r.get("telemetry_coverage_status", "none") or "none"
                ),
                "telemetry_coverage_reason": str(
                    r.get("telemetry_coverage_reason", "") or ""
                ),
                "objective_progress_delta": float(r.get("objective_progress_delta", 0.0) or 0.0),
                "vp_progress": (
                    float(r.get("vp_progress", 0.0))
                    if r.get("vp_progress", None) is not None
                    else (
                        float(r.get("vp_progress_estimated_selected", 0.0))
                        if r.get("vp_progress_estimated_selected", None) is not None
                        else None
                    )
                ),
                "strategy_label": str(r.get("strategy_label", "") or ""),
                "unit_prefilter_enabled": (
                    bool(r.get("unit_prefilter_enabled"))
                    if r.get("unit_prefilter_enabled", None) is not None
                    else None
                ),
                "unit_prefilter_enabled_source": str(
                    r.get("unit_prefilter_enabled_source", "missing") or "missing"
                ),
                "unit_prefilter_enabled_available": bool(
                    r.get("unit_prefilter_enabled_available", None)
                ),
                "unit_prefilter_selected_unit_id": str(
                    r.get("unit_prefilter_selected_unit_id", "__none__") or "__none__"
                ),
                "unit_prefilter_replan_evaluated_units": [
                    dict(x or {})
                    for x in list(r.get("unit_prefilter_replan_evaluated_units", []) or [])
                    if isinstance(x, dict)
                ],
                "unit_prefilter_replan_units_evaluated_count": int(
                    r.get("unit_prefilter_replan_units_evaluated_count", 0) or 0
                ),
                "unit_prefilter_replan_virtual_simulations_total": int(
                    r.get("unit_prefilter_replan_virtual_simulations_total", 0) or 0
                ),
                "unit_prefilter_constrained_count": (
                    int(r.get("unit_prefilter_constrained_count", 0) or 0)
                    if r.get("unit_prefilter_constrained_count", None) is not None
                    else None
                ),
                "unit_prefilter_constrained_count_source": str(
                    r.get("unit_prefilter_constrained_count_source", "missing") or "missing"
                ),
                "unit_prefilter_constrained_count_available": bool(
                    r.get("unit_prefilter_constrained_count_available", None)
                ),
                "unit_prefilter_global_count": (
                    int(r.get("unit_prefilter_global_count", 0) or 0)
                    if r.get("unit_prefilter_global_count", None) is not None
                    else None
                ),
                "unit_prefilter_global_count_source": str(
                    r.get("unit_prefilter_global_count_source", "missing") or "missing"
                ),
                "unit_prefilter_global_count_available": bool(
                    r.get("unit_prefilter_global_count_available", None)
                ),
                "unit_positions": list(r.get("unit_positions", []) or []),
                "unit_hp_map": dict(r.get("unit_hp_map", {}) or {}),
                "unit_alive_map": dict(r.get("unit_alive_map", {}) or {}),
                "vp_map": dict(r.get("vp_map", {}) or {}),
                "obs_enemy_vp_threat_map": dict(r.get("obs_enemy_vp_threat_map", {}) or {}),
                "obs_reachable_hex_mask_by_unit": dict(r.get("obs_reachable_hex_mask_by_unit", {}) or {}),
                "obs_attackable_hex_mask_by_unit": dict(r.get("obs_attackable_hex_mask_by_unit", {}) or {}),
                "obs_terrain_type_map": dict(r.get("obs_terrain_type_map", {}) or {}),
                "obs_terrain_cover_map": dict(r.get("obs_terrain_cover_map", {}) or {}),
                "obs_terrain_los_block_map": dict(r.get("obs_terrain_los_block_map", {}) or {}),
                "obs_terrain_move_cost_map": dict(r.get("obs_terrain_move_cost_map", {}) or {}),
                "obs_fortification_type_map": dict(r.get("obs_fortification_type_map", {}) or {}),
                "obs_fortification_edge_map": dict(r.get("obs_fortification_edge_map", {}) or {}),
                "obs_enemy_reaction_fire_risk": (
                    float(r.get("obs_enemy_reaction_fire_risk", 0.0))
                    if r.get("obs_enemy_reaction_fire_risk", None) is not None
                    else None
                ),
                "obs_vp_ownership_ttl": dict(r.get("obs_vp_ownership_ttl", {}) or {}),
                "objective_soft_reward_component": (
                    float(r.get("objective_soft_reward_component", 0.0))
                    if r.get("objective_soft_reward_component", None) is not None
                    else None
                ),
                "objective_soft_reward_component_source": str(
                    r.get("objective_soft_reward_component_source", "missing") or "missing"
                ),
                "objective_soft_reward_component_available": bool(
                    r.get("objective_soft_reward_component_available", None)
                ),
                "objective_soft_reward_component_reason": str(
                    r.get("objective_soft_reward_component_reason", "missing") or "missing"
                ),
                "global_strategy_soft_reward_component": (
                    float(r.get("global_strategy_soft_reward_component", 0.0))
                    if r.get("global_strategy_soft_reward_component", None) is not None
                    else None
                ),
                "reaction_fire_soft_reward_component": (
                    float(r.get("reaction_fire_soft_reward_component", 0.0))
                    if r.get("reaction_fire_soft_reward_component", None) is not None
                    else None
                ),
                "reaction_fire_soft_reward_component_source": str(
                    r.get("reaction_fire_soft_reward_component_source", "missing") or "missing"
                ),
                "reaction_fire_soft_reward_component_available": bool(
                    r.get("reaction_fire_soft_reward_component_available", None)
                ),
                "reaction_exposure_component": (
                    float(r.get("reaction_exposure_component", 0.0))
                    if r.get("reaction_exposure_component", None) is not None
                    else None
                ),
                "reaction_exposure_component_source": str(
                    r.get("reaction_exposure_component_source", "missing") or "missing"
                ),
                "reaction_exposure_component_available": bool(
                    r.get("reaction_exposure_component_available", None)
                ),
                "mcts_prior": (
                    float(r.get("mcts_prior", 0.0))
                    if r.get("mcts_prior", None) is not None
                    else None
                ),
                "mcts_prior_source": str(r.get("mcts_prior_source", "missing") or "missing"),
                "mcts_prior_available": bool(r.get("mcts_prior_available", None)),
                "mcts_q_value": (
                    float(r.get("mcts_q_value", 0.0))
                    if r.get("mcts_q_value", None) is not None
                    else None
                ),
                "mcts_q_value_source": str(r.get("mcts_q_value_source", "missing") or "missing"),
                "mcts_q_value_available": bool(r.get("mcts_q_value_available", None)),
                "mcts_u_value": (
                    float(r.get("mcts_u_value", 0.0))
                    if r.get("mcts_u_value", None) is not None
                    else None
                ),
                "mcts_u_value_source": str(r.get("mcts_u_value_source", "missing") or "missing"),
                "mcts_u_value_available": bool(r.get("mcts_u_value_available", None)),
                "mcts_success_prob_proxy": (
                    float(r.get("mcts_success_prob_proxy", 0.0))
                    if r.get("mcts_success_prob_proxy", None) is not None
                    else None
                ),
                "mcts_success_prob_proxy_source": str(
                    r.get("mcts_success_prob_proxy_source", "missing") or "missing"
                ),
                "mcts_success_prob_proxy_available": bool(
                    r.get("mcts_success_prob_proxy_available", None)
                ),
                "mcts_success_component": (
                    float(r.get("mcts_success_component", 0.0))
                    if r.get("mcts_success_component", None) is not None
                    else None
                ),
                "mcts_success_component_source": str(
                    r.get("mcts_success_component_source", "missing") or "missing"
                ),
                "mcts_success_component_available": bool(
                    r.get("mcts_success_component_available", None)
                ),
                "vp_horizon_steps": (
                    float(r.get("vp_horizon_steps", 0.0))
                    if r.get("vp_horizon_steps", None) is not None
                    else None
                ),
                "vp_horizon_signal": (
                    float(r.get("vp_horizon_signal", 0.0))
                    if r.get("vp_horizon_signal", None) is not None
                    else None
                ),
                "vp_horizon_decision_component": (
                    float(r.get("vp_horizon_decision_component", 0.0))
                    if r.get("vp_horizon_decision_component", None) is not None
                    else None
                ),
                "vp_horizon_component": (
                    float(r.get("vp_horizon_component", 0.0))
                    if r.get("vp_horizon_component", None) is not None
                    else None
                ),
                "vp_horizon_source": str(r.get("vp_horizon_source", "missing") or "missing"),
                "vp_horizon_available": bool(r.get("vp_horizon_available", None)),
                "vp_progress_observed": (
                    float(r.get("vp_progress_observed", 0.0))
                    if r.get("vp_progress_observed", None) is not None
                    else None
                ),
                "vp_progress_estimated_selected": (
                    float(r.get("vp_progress_estimated_selected", 0.0))
                    if r.get("vp_progress_estimated_selected", None) is not None
                    else None
                ),
                "vp_progress_source": str(r.get("vp_progress_source", "missing") or "missing"),
                "vp_progress_available": bool(r.get("vp_progress_available", None)),
                "why_action_vs_vp_text": str(r.get("why_action_vs_vp_text", "") or ""),
                "macro_posture": str(r.get("macro_posture", "") or ""),
                "macro_target_vp_id": str(r.get("macro_target_vp_id", "") or ""),
                "unit_macro_role": str(r.get("unit_macro_role", "") or ""),
                "role_assigned": str(r.get("role_assigned", "") or ""),
                "role_is_mutated": bool(r.get("role_is_mutated", False)),
                "role_mutation_reason": str(r.get("role_mutation_reason", "") or ""),
                "prior_boost_applied": float(r.get("prior_boost_applied", 0.0) or 0.0),
                "badge_label": str(r.get("badge_label", "") or ""),
                "policy_overridden_by_mcts": bool(r.get("policy_overridden_by_mcts", False)),
                "mcts_action_candidates": normalized_candidates,
                "why_action_vs_vp": why,
                "vp_potential_reward_component": (
                    float(r.get("vp_potential_reward_component", 0.0))
                    if r.get("vp_potential_reward_component", None) is not None
                    else None
                ),
                "vp_potential_delta": (
                    float(r.get("vp_potential_delta", 0.0))
                    if r.get("vp_potential_delta", None) is not None
                    else None
                ),
                "turn_urgency_factor": (
                    float(r.get("turn_urgency_factor", 0.0))
                    if r.get("turn_urgency_factor", None) is not None
                    else None
                ),
                "turn_urgency_decay": (
                    float(r.get("turn_urgency_decay", 1.0))
                    if r.get("turn_urgency_decay", None) is not None
                    else None
                ),
                "paralysis_penalty": (
                    float(r.get("paralysis_penalty", 0.0))
                    if r.get("paralysis_penalty", None) is not None
                    else None
                ),
                "paralysis_units_count": (
                    int(r.get("paralysis_units_count", 0))
                    if r.get("paralysis_units_count", None) is not None
                    else None
                ),
            }
        )
    return out
