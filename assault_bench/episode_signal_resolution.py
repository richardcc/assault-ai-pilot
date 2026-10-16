from __future__ import annotations

import math
from typing import Dict, List, Optional

from assault_bench.signal_utils import first_non_none, safe_float_or_none


def resolve_step_signals(
    *,
    action: str,
    mcts_action_candidates: List[Dict[str, object]],
    selected_candidate: Dict[str, object],
    transition_info,
    objective_had_opportunity: int,
    objective_min_dist_before: float,
    objective_progress_delta: Optional[float],
    reward_shaping: Dict[str, object],
    action_kind: str,
    active_side: str,
    eval_side: str,
    before_vp_owner: Dict[str, str],
    after_vp_owner: Dict[str, str],
    obs_vp_hexes: List[object],
    obs_units: List[object],
    post_obs_units: List[object],
    vp_captures_eval: int,
    enemy_damage: float,
    sustained_advantage_turns_by_side: Dict[str, int],
    pending_setup_strength_by_side: Dict[str, float],
    legal_actions_list: List[str],
    field_fn,
    resolve_vp_horizon_selected_fields_fn,
    vp_horizon_soft_components_for_step_fn,
    normalize_side_key_fn,
    units_snapshot_fn,
    resolve_global_strategy_component_fn,
    reaction_fire_soft_signal_for_step_fn,
    reaction_exposure_component_for_step_fn,
    obs_enemy_reaction_fire_risk_for_step_fn,
) -> dict[str, object]:
    candidate_rows = list(mcts_action_candidates or [])
    selected_candidate = dict(selected_candidate or {})
    if not selected_candidate and candidate_rows:
        selected_candidate = dict(candidate_rows[0] or {})
    reward_shaping_map = dict(reward_shaping or {})
    before_vp_owner_map = dict(before_vp_owner or {})
    after_vp_owner_map = dict(after_vp_owner or {})
    obs_vp_hexes_list = list(obs_vp_hexes or [])
    obs_units_list = list(obs_units or [])
    post_obs_units_list = list(post_obs_units or [])
    sustained_by_side = dict(sustained_advantage_turns_by_side or {})
    pending_setup_by_side = dict(pending_setup_strength_by_side or {})
    legal_actions_list_local = list(legal_actions_list or [])
    (
        selected_vp_horizon_steps,
        selected_vp_horizon_signal,
        selected_vp_horizon_component,
        vp_horizon_source,
        vp_horizon_available,
    ) = resolve_vp_horizon_selected_fields_fn(
        selected_candidate=dict(selected_candidate),
        transition_info=transition_info,
    )
    selected_components = (
        dict(selected_candidate.get("decision_components", {}) or {})
        if isinstance(selected_candidate.get("decision_components", None), dict)
        else {}
    )
    raw_tie_break_term = (
        selected_components.get("tie_break_term", None)
        if isinstance(selected_components, dict)
        else None
    )
    if raw_tie_break_term is None:
        raw_tie_break_term = field_fn(transition_info, "tie_break_term", None)
    try:
        selected_tie_break_term = float(raw_tie_break_term) if raw_tie_break_term is not None else None
    except Exception:
        selected_tie_break_term = None
    if not bool(vp_horizon_available):
        vp_progress_for_horizon = (
            float(selected_tie_break_term)
            if selected_tie_break_term is not None
            else (
                float(objective_progress_delta)
                if objective_progress_delta is not None
                else 0.0
            )
        )
        (
            vp_h_comp_fallback,
            vp_h_steps_fallback,
            vp_h_signal_fallback,
            vp_h_source_fallback,
        ) = vp_horizon_soft_components_for_step_fn(
            reward_shaping=dict(reward_shaping_map),
            objective_had_opportunity=int(objective_had_opportunity),
            baseline_horizon_steps=(
                float(objective_min_dist_before)
                if float(objective_min_dist_before) >= 0.0
                else None
            ),
            vp_progress_delta=float(vp_progress_for_horizon),
        )
        selected_vp_horizon_steps = float(vp_h_steps_fallback)
        selected_vp_horizon_signal = float(vp_h_signal_fallback)
        selected_vp_horizon_component = float(vp_h_comp_fallback)
        vp_horizon_source = "computed_" + str(vp_h_source_fallback)
        vp_horizon_available = True

    raw_mcts_prior = selected_candidate.get("policy_prior", None)
    raw_mcts_q = selected_candidate.get("mcts_q_value", None)
    raw_mcts_u = selected_candidate.get("mcts_u_value", None)
    raw_decision_score = next(
        (
            c.get("real_decision_score", c.get("final_score", None))
            for c in candidate_rows
            if str(c.get("action_id", "")) == str(action)
        ),
        None,
    )
    raw_selected_success_proxy = first_non_none(
        selected_components.get("mcts_success_prob_proxy", None),
        selected_components.get("success_prob_proxy", None),
        field_fn(transition_info, "mcts_success_prob_proxy", None),
        field_fn(transition_info, "success_prob_proxy", None),
    )
    raw_selected_success_component = first_non_none(
        selected_components.get("mcts_success_component", None),
        selected_components.get("success_component", None),
        field_fn(transition_info, "mcts_success_component", None),
        field_fn(transition_info, "success_component", None),
    )

    mcts_prior_value = safe_float_or_none(raw_mcts_prior)
    mcts_q_value = safe_float_or_none(raw_mcts_q)
    mcts_u_value = safe_float_or_none(raw_mcts_u)
    decision_score_value = safe_float_or_none(raw_decision_score)
    selected_success_proxy = safe_float_or_none(raw_selected_success_proxy)
    selected_success_component = safe_float_or_none(raw_selected_success_component)

    reward_components_map = dict(field_fn(transition_info, "reward_components", {}) or {})
    objective_soft_from_info = safe_float_or_none(
        field_fn(transition_info, "objective_soft_reward_component", None)
    )
    objective_soft_component_value = objective_soft_from_info
    objective_soft_source = "missing"
    if objective_soft_component_value is not None:
        objective_soft_source = "transition_info"
    else:
        obj_parts = []
        for k in ("objective_progress", "objective_no_progress", "objective_no_progress_attack"):
            v = safe_float_or_none(reward_components_map.get(k, None))
            if v is not None:
                obj_parts.append(float(v))
        if obj_parts:
            objective_soft_component_value = float(sum(obj_parts))
            objective_soft_source = "transition_info.reward_components.objective_sum"
    if objective_soft_component_value is None:
        try:
            rs = dict(reward_shaping_map)
            opp = int(objective_had_opportunity)
            conv = int(field_fn(transition_info, "objective_converted", 0) or 0)
            prog = float(objective_progress_delta or 0.0)
            objective_progress_bonus_per_hex = float(rs.get("objective_progress_bonus_per_hex", 0.0) or 0.0)
            objective_no_progress_penalty = float(rs.get("objective_no_progress_penalty", 0.0) or 0.0)
            objective_no_progress_attack_penalty = float(rs.get("objective_no_progress_attack_penalty", 0.0) or 0.0)
            attacker_progress_mult = float(rs.get("attacker_objective_progress_multiplier", 1.0) or 1.0)
            defender_progress_mult = float(rs.get("defender_objective_progress_multiplier", 0.25) or 0.25)
            attacker_no_progress_mult = float(rs.get("attacker_objective_no_progress_multiplier", 1.0) or 1.0)
            defender_no_progress_mult = float(rs.get("defender_objective_no_progress_multiplier", 0.25) or 0.25)
            attacker_no_progress_attack_mult = float(rs.get("attacker_objective_no_progress_attack_multiplier", 1.0) or 1.0)
            defender_no_progress_attack_mult = float(rs.get("defender_objective_no_progress_attack_multiplier", 0.25) or 0.25)
            side_norm = normalize_side_key_fn(str(active_side))
            tracked_norm = normalize_side_key_fn(str(eval_side))
            is_tracked_actor = bool(side_norm and tracked_norm and side_norm == tracked_norm)
            progress_scale = attacker_progress_mult if is_tracked_actor else defender_progress_mult
            no_progress_scale = attacker_no_progress_mult if is_tracked_actor else defender_no_progress_mult
            no_progress_attack_scale = attacker_no_progress_attack_mult if is_tracked_actor else defender_no_progress_attack_mult
            objective_soft_fallback = 0.0
            if opp > 0 and conv <= 0:
                prog_pos = max(0.0, prog)
                objective_soft_fallback += (prog_pos * objective_progress_bonus_per_hex * progress_scale)
                if prog_pos <= 0.0:
                    objective_soft_fallback += (-max(0.0, objective_no_progress_penalty) * no_progress_scale)
                    action_kind_upper = str(action_kind or "").strip().upper()
                    if action_kind_upper not in {"", "MOVE", "WAIT", "TIMEOUT", "OPPORTUNITY_SKIP"}:
                        objective_soft_fallback += (
                            -max(0.0, objective_no_progress_attack_penalty) * no_progress_attack_scale
                        )
            objective_soft_component_value = float(objective_soft_fallback)
            objective_soft_source = "computed_reward_shaping_objective"
        except Exception:
            pass
    objective_soft_available = bool(objective_soft_component_value is not None)
    objective_soft_reason = "missing"
    if objective_soft_available:
        objective_soft_reason = "nonzero_signal"
        try:
            objective_soft_abs = abs(float(objective_soft_component_value))
        except Exception:
            objective_soft_abs = 0.0
        if objective_soft_abs <= 1e-12:
            if int(field_fn(transition_info, "objective_converted", 0) or 0) > 0:
                objective_soft_reason = "zero_due_to_conversion"
            elif int(objective_had_opportunity) <= 0:
                objective_soft_reason = "zero_no_opportunity"
            elif objective_progress_delta is not None and float(objective_progress_delta) <= 0.0:
                objective_soft_reason = "zero_no_progress_or_canceled_terms"
            else:
                objective_soft_reason = "zero_from_components"

    global_strategy_soft_component_value, global_strategy_soft_source, sustained_by_side, pending_setup_by_side = resolve_global_strategy_component_fn(
        active_side=str(active_side),
        action_kind=str(action_kind),
        reward_shaping=dict(reward_shaping_map),
        before_vp_owner=dict(before_vp_owner_map),
        after_vp_owner=dict(after_vp_owner_map),
        obs_vp_hexes=list(obs_vp_hexes_list),
        obs_units=list(obs_units_list),
        post_obs_units=list(post_obs_units_list),
        vp_captures_eval=int(vp_captures_eval),
        source_value_from_transition=safe_float_or_none(
            field_fn(transition_info, "global_strategy_soft_reward_component", None)
        ),
        sustained_advantage_turns_by_side=dict(sustained_by_side),
        pending_setup_strength_by_side=dict(pending_setup_by_side),
        normalize_side_key_fn=normalize_side_key_fn,
        units_snapshot_fn=units_snapshot_fn,
    )
    global_strategy_soft_available = bool(global_strategy_soft_component_value is not None)

    reaction_fire_soft_from_info = safe_float_or_none(
        field_fn(transition_info, "reaction_fire_soft_reward_component", None)
    )
    reaction_fire_soft_component_value = reaction_fire_soft_from_info
    reaction_fire_soft_source = "missing"
    if reaction_fire_soft_component_value is not None:
        reaction_fire_soft_source = "transition_info"
    else:
        rx_parts = []
        for k in ("reaction_fire_miss", "opportunity_fire_no_progress", "opportunity_skip_capture_preserve"):
            v = safe_float_or_none(reward_components_map.get(k, None))
            if v is not None:
                rx_parts.append(float(v))
        if rx_parts:
            reaction_fire_soft_component_value = float(sum(rx_parts))
            reaction_fire_soft_source = "transition_info.reward_components.reaction_sum"
    if reaction_fire_soft_component_value is None:
        computed_rx_soft, computed_rx_soft_source = reaction_fire_soft_signal_for_step_fn(
            action_kind=str(action_kind),
            expected_damage_proxy=float(enemy_damage),
            reward_shaping=dict(reward_shaping_map),
        )
        reaction_fire_soft_component_value = float(computed_rx_soft)
        reaction_fire_soft_source = "computed_" + str(computed_rx_soft_source)
    reaction_fire_soft_available = bool(reaction_fire_soft_component_value is not None)

    obs_enemy_reaction_fire_risk_runtime = None
    try:
        _risk_raw = field_fn(transition_info, "obs_enemy_reaction_fire_risk", None)
        if _risk_raw is not None:
            _risk_f = float(_risk_raw)
            if math.isfinite(_risk_f):
                obs_enemy_reaction_fire_risk_runtime = float(_risk_f)
    except Exception:
        obs_enemy_reaction_fire_risk_runtime = None
    obs_enemy_reaction_fire_risk_fallback = obs_enemy_reaction_fire_risk_for_step_fn(
        legal_actions=list(legal_actions_list_local),
        units=list(obs_units_list),
        actor_side=str(active_side),
    )
    if (
        obs_enemy_reaction_fire_risk_runtime is None
        or (
            float(obs_enemy_reaction_fire_risk_runtime) <= 0.0
            and float(obs_enemy_reaction_fire_risk_fallback) > 0.0
        )
    ):
        obs_enemy_reaction_fire_risk_value = float(obs_enemy_reaction_fire_risk_fallback)
    else:
        obs_enemy_reaction_fire_risk_value = float(obs_enemy_reaction_fire_risk_runtime)

    reaction_exposure_component_value = safe_float_or_none(
        field_fn(transition_info, "reaction_exposure_component", None)
    )
    reaction_exposure_source = "transition_info" if reaction_exposure_component_value is not None else "missing"
    if reaction_exposure_component_value is None:
        computed_reaction_exposure, computed_reaction_exposure_source = reaction_exposure_component_for_step_fn(
            action_kind=str(action_kind),
            obs_enemy_reaction_fire_risk=float(obs_enemy_reaction_fire_risk_value or 0.0),
            reward_shaping=dict(reward_shaping_map),
        )
        reaction_exposure_component_value = float(computed_reaction_exposure)
        reaction_exposure_source = "computed_" + str(computed_reaction_exposure_source)
    reaction_exposure_available = bool(reaction_exposure_component_value is not None)

    return {
        "selected_candidate": dict(selected_candidate),
        "selected_components": dict(selected_components),
        "selected_tie_break_term": selected_tie_break_term,
        "selected_vp_horizon_steps": selected_vp_horizon_steps,
        "selected_vp_horizon_signal": selected_vp_horizon_signal,
        "selected_vp_horizon_component": selected_vp_horizon_component,
        "vp_horizon_source": str(vp_horizon_source),
        "vp_horizon_available": bool(vp_horizon_available),
        "mcts_prior_value": mcts_prior_value,
        "mcts_q_value": mcts_q_value,
        "mcts_u_value": mcts_u_value,
        "decision_score_value": decision_score_value,
        "selected_success_proxy": selected_success_proxy,
        "selected_success_component": selected_success_component,
        "objective_soft_component_value": objective_soft_component_value,
        "objective_soft_source": str(objective_soft_source),
        "objective_soft_available": bool(objective_soft_available),
        "objective_soft_reason": str(objective_soft_reason),
        "global_strategy_soft_component_value": global_strategy_soft_component_value,
        "global_strategy_soft_source": str(global_strategy_soft_source),
        "global_strategy_soft_available": bool(global_strategy_soft_available),
        "reaction_fire_soft_component_value": reaction_fire_soft_component_value,
        "reaction_fire_soft_source": str(reaction_fire_soft_source),
        "reaction_fire_soft_available": bool(reaction_fire_soft_available),
        "obs_enemy_reaction_fire_risk_value": obs_enemy_reaction_fire_risk_value,
        "reaction_exposure_component_value": reaction_exposure_component_value,
        "reaction_exposure_source": str(reaction_exposure_source),
        "reaction_exposure_available": bool(reaction_exposure_available),
        "sustained_advantage_turns_by_side": dict(sustained_by_side),
        "pending_setup_strength_by_side": dict(pending_setup_by_side),
    }
