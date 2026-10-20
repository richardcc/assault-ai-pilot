from __future__ import annotations

from typing import Dict, List, Optional
from assault_bench.episode_step_models import (
    StepCoreData,
    StepPrefilterData,
    StepSignalData,
)


def build_trace_row(
    *,
    core: StepCoreData,
    signals: StepSignalData,
    prefilter: StepPrefilterData,
    mcts_out,
    latent_top_dims: str,
    policy_top_actions: List[str],
    policy_top_probs: List[float],
    mcts_action_candidates: List[Dict[str, object]],
    selected_candidate: Dict[str, object],
    decision_rank: int,
    mcts_candidates_duplicates_collapsed: int,
    why_action_vs_vp: Dict[str, object],
    policy_top_action: str,
    policy_overridden_by_mcts,
    latent_top_indices: List[int],
    latent_top_values: List[float],
    latent_l2_norm: Optional[float],
    predicted_value_root: Optional[float],
    dynamics_pred_reward: Optional[float],
    dynamics_next_latent_l2: Optional[float],
    dynamics_delta_l2: Optional[float],
    immediate_capture_legal_count: int,
    unit_positions_snapshot: List[Dict[str, object]],
    unit_hp_snapshot: Dict[str, float],
    unit_alive_snapshot: Dict[str, bool],
    unit_suppressed_snapshot: Dict[str, bool],
    before_vp_owner: Dict[str, str],
    after_vp_owner: Dict[str, str],
    transition_info: object,
    obs_terrain_type_map: Dict[str, object],
    obs_terrain_cover_map: Dict[str, object],
    obs_terrain_los_block_map: Dict[str, object],
    obs_terrain_move_cost_map: Dict[str, object],
    obs_fortification_type_map: Dict[str, object],
    obs_fortification_edge_map: Dict[str, object],
    head_states: Dict[str, Dict[str, str]],
    telemetry_coverage_status: str,
    telemetry_coverage_reason: str,
    attack_dice_rolls: List[float],
    defense_dice_rolls: List[float],
    attack_components_by_die: Dict[str, object],
    defense_components_by_die: Dict[str, object],
    runtime_events: List[Dict[str, object]],
    post_units_snapshot: List[Dict[str, object]],
    field_fn,
    trace_detail_level: str = "core",
) -> Dict[str, object]:
    detail = str(trace_detail_level or "core").strip().lower()
    full_detail = detail == "full"

    candidates_payload = list(mcts_action_candidates or [])
    if not full_detail:
        # Keep producer-side per-candidate VP/MCTS telemetry available even in
        # core mode, but compact the payload to avoid full-detail bloat.
        compact_keys = (
            "action_id",
            "action_kind",
            "unit_id",
            "policy_prior",
            "visit_count",
            "real_decision_score",
            "decision_rank",
            "selected_action",
            "selected_by",
            "decision_criterion",
            "vp_progress_delta",
            "vp_progress_source",
            "vp_target_id",
            "vp_target_source",
            "vp_distance_after",
            "vp_distance_source",
            "mcts_q_value",
            "mcts_u_value",
            "mcts_success_prob_proxy",
            "mcts_success_component",
            "mcts_puct_score",
            "decision_components",
            "vp_horizon_steps",
            "vp_horizon_signal",
            "vp_horizon_component",
            "vp_horizon_decision_component",
        )
        compact_rows = []
        for row in list(mcts_action_candidates or []):
            src = dict(row or {})
            compact = {}
            for k in compact_keys:
                if k in src:
                    compact[k] = src.get(k)
            if compact:
                compact_rows.append(compact)
        candidates_payload = compact_rows
    has_candidates_payload = bool(candidates_payload)

    terrain_type_payload = dict(obs_terrain_type_map or {}) if full_detail else {}
    terrain_cover_payload = dict(obs_terrain_cover_map or {}) if full_detail else {}
    terrain_los_payload = dict(obs_terrain_los_block_map or {}) if full_detail else {}
    terrain_move_payload = dict(obs_terrain_move_cost_map or {}) if full_detail else {}
    fort_type_payload = dict(obs_fortification_type_map or {}) if full_detail else {}
    fort_edge_payload = dict(obs_fortification_edge_map or {}) if full_detail else {}
    attack_components_payload = dict(attack_components_by_die)
    defense_components_payload = dict(defense_components_by_die)
    runtime_events_payload = list(runtime_events)

    def _source_from_candidate(field_name: str, has_value: bool) -> str:
        if not has_value:
            return "missing"
        return str(selected_candidate.get(field_name + "_source", "missing"))

    entropy_collapse = bool(
        int(len(core.legal_actions_list)) > 1
        and int(core.mcts_total_visits) > 0
        and float(core.mcts_entropy) <= 1e-6
    )
    return {
        "step": int(core.step),
        "game_turn": int(core.game_turn),
        "turn": int(core.turn),
        "to_play": str(core.active_side),
        "action_id": str(core.action),
        "mcts_chosen_action": str(core.action),
        "requested_action_id": str(core.action),
        "action_kind": str(core.action_kind),
        "legal_capture_like_options": int(core.capture_legal_count),
        "capture_like_taken": bool(core.capture_like_action_taken),
        "chosen_prob": float(core.chosen_prob),
        "policy_margin": float(core.margin),
        "chosen_action_prob": float(core.chosen_prob),
        "mcts_prior": signals.mcts_prior_value,
        "mcts_prior_source": _source_from_candidate("policy_prior", signals.mcts_prior_value is not None),
        "mcts_prior_available": bool(signals.mcts_prior_value is not None),
        "mcts_q_value": signals.mcts_q_value,
        "mcts_q_value_source": _source_from_candidate("mcts_q_value", signals.mcts_q_value is not None),
        "mcts_q_value_available": bool(signals.mcts_q_value is not None),
        "mcts_u_value": signals.mcts_u_value,
        "mcts_u_value_source": _source_from_candidate("mcts_u_value", signals.mcts_u_value is not None),
        "mcts_u_value_available": bool(signals.mcts_u_value is not None),
        "mcts_margin": float(core.margin),
        "mcts_entropy": float(core.mcts_entropy),
        "mcts_total_visits": int(core.mcts_total_visits),
        "mcts_active_actions": int(core.mcts_active_actions),
        "mcts_root_actions_count": int(len(core.root_actions_for_explain)),
        "mcts_entropy_source": "root_visit_distribution",
        "mcts_entropy_collapse": bool(entropy_collapse),
        "mcts_entropy_collapse_label": ("collapsed_root_distribution" if entropy_collapse else "ok"),
        "mcts_q_guardrail_clipped_count": int(getattr(mcts_out, "q_guardrail_clipped_count", 0)),
        "mcts_q_clipped_count": int(getattr(mcts_out, "q_guardrail_clipped_count", 0)),
        "mcts_q_clip_denominator_count": int(max(0, int(core.mcts_total_visits))),
        "mcts_q_guardrail_clip_limit": (
            float(getattr(mcts_out, "q_guardrail_clip_limit", 0.0))
            if getattr(mcts_out, "q_guardrail_clip_limit", None) is not None
            else None
        ),
        "legal_actions": list(core.legal_actions_list),
        "legal_actions_duplicates_collapsed": int(core.legal_actions_duplicates_collapsed),
        "legal_actions_decoded_target_qr": list(core.legal_actions_decoded_target_qr),
        "acting_unit_action_catalog": list(core.acting_unit_action_catalog),
        "unit_id": str(core.acting_unit_id),
        "unit_side": str(core.active_side),
        "unit_label": (
            str(getattr(core.acting_unit, "unit_label", "") or "")
            if core.acting_unit is not None
            else str(core.acting_unit_id)
        ),
        "reward": float(core.transition_reward),
        "done": bool(core.transition_done),
        "damage_dealt": float(core.enemy_damage),
        "kills_dealt": int(core.enemy_kills),
        "enemy_damage": float(core.enemy_damage),
        "enemy_kills": int(core.enemy_kills),
        "attack_target_unit_id": (str(core.action_parts[2]) if len(core.action_parts) > 2 else ""),
        "target_q": int(core.target_q) if isinstance(core.target_q, int) else None,
        "target_r": int(core.target_r) if isinstance(core.target_r, int) else None,
        "attack_distance_mean": float(core.attack_distance),
        "attack_target_cover_mean": float(core.target_cover),
        "attack_target_los_block_mean": float(core.target_los),
        "latent_top_dims": str(latent_top_dims),
        "policy_top_actions": list(policy_top_actions),
        "policy_top_probs": list(policy_top_probs),
        "mcts_action_candidates": list(candidates_payload),
        "mcts_action_candidates_duplicates_collapsed": int(mcts_candidates_duplicates_collapsed),
        "why_action_vs_vp": dict(why_action_vs_vp),
        "why_action_vs_vp_text": str(why_action_vs_vp.get("explanation", "")),
        "vp_horizon_steps": (float(signals.selected_vp_horizon_steps) if signals.selected_vp_horizon_steps is not None else None),
        "vp_horizon_signal": (float(signals.selected_vp_horizon_signal) if signals.selected_vp_horizon_signal is not None else None),
        "vp_horizon_decision_component": (
            float(signals.selected_vp_horizon_component) if signals.selected_vp_horizon_component is not None else None
        ),
        "vp_horizon_component": (float(signals.selected_vp_horizon_component) if signals.selected_vp_horizon_component is not None else None),
        "vp_horizon_source": (str(signals.vp_horizon_source) if signals.vp_horizon_available else "missing"),
        "vp_horizon_available": bool(signals.vp_horizon_available),
        "real_decision_score": signals.decision_score_value,
        "decision_score_selected_source": ("mcts_action_candidates" if signals.decision_score_value is not None else "missing"),
        "decision_score_selected_available": bool(signals.decision_score_value is not None),
        "decision_rank": int(decision_rank),
        "decision_win_basis": ("mcts_puct" if has_candidates_payload else "policy_or_random"),
        "policy_top_action": str(policy_top_action),
        "policy_overridden_by_mcts": policy_overridden_by_mcts,
        "override_sanity_consistent": (
            None
            if policy_overridden_by_mcts is None
            else int(int(policy_overridden_by_mcts) == int(str(policy_top_action) != str(core.action)))
        ),
        "latent_top_indices": list(latent_top_indices),
        "latent_top_values": list(latent_top_values),
        "latent_l2_norm": latent_l2_norm,
        "predicted_value_root": predicted_value_root,
        "dynamics_pred_reward": dynamics_pred_reward,
        "dynamics_next_latent_l2": dynamics_next_latent_l2,
        "dynamics_delta_l2": dynamics_delta_l2,
        "objective_soft_reward_component": signals.objective_soft_component_value,
        "objective_soft_reward_component_source": str(signals.objective_soft_source),
        "objective_soft_reward_component_available": bool(signals.objective_soft_available),
        "objective_soft_reward_component_reason": str(signals.objective_soft_reason),
        "global_strategy_soft_reward_component": signals.global_strategy_soft_component_value,
        "global_strategy_soft_reward_component_source": str(signals.global_strategy_soft_source),
        "global_strategy_soft_reward_component_available": bool(signals.global_strategy_soft_available),
        "reaction_fire_soft_reward_component": signals.reaction_fire_soft_component_value,
        "reaction_fire_soft_reward_component_source": str(signals.reaction_fire_soft_source),
        "reaction_fire_soft_reward_component_available": bool(signals.reaction_fire_soft_available),
        "reaction_exposure_component": signals.reaction_exposure_component_value,
        "reaction_exposure_component_source": str(signals.reaction_exposure_source),
        "reaction_exposure_component_available": bool(signals.reaction_exposure_available),
        "mcts_success_prob_proxy": signals.selected_success_proxy,
        "mcts_success_prob_proxy_source": (
            (
                "decision_components"
                if signals.selected_components.get("mcts_success_prob_proxy", signals.selected_components.get("success_prob_proxy", None)) is not None
                else "transition_info"
            )
            if signals.selected_success_proxy is not None
            else "missing"
        ),
        "mcts_success_prob_proxy_available": bool(signals.selected_success_proxy is not None),
        "mcts_success_component": signals.selected_success_component,
        "mcts_success_component_source": (
            (
                "decision_components"
                if signals.selected_components.get("mcts_success_component", signals.selected_components.get("success_component", None)) is not None
                else "transition_info"
            )
            if signals.selected_success_component is not None
            else "missing"
        ),
        "mcts_success_component_available": bool(signals.selected_success_component is not None),
        "legal_capture_options": int(immediate_capture_legal_count),
        "objective_had_opportunity": int(signals.objective_had_opportunity),
        "objective_distance_before": float(signals.objective_min_dist_before),
        "objective_distance_after": float(signals.objective_min_dist_after),
        "objective_min_dist_before": float(signals.objective_min_dist_before),
        "objective_min_dist_after": float(signals.objective_min_dist_after),
        "objective_progress_delta": signals.objective_progress_delta,
        "vp_progress_observed": (float(signals.objective_progress_delta) if signals.objective_progress_delta is not None else None),
        "vp_progress_estimated_selected": (float(signals.selected_tie_break_term) if signals.selected_tie_break_term is not None else None),
        "vp_progress": (
            float(signals.objective_progress_delta)
            if signals.objective_progress_delta is not None
            else (float(signals.selected_tie_break_term) if signals.selected_tie_break_term is not None else None)
        ),
        "vp_progress_source": (
            "objective_progress_delta"
            if signals.objective_progress_delta is not None
            else ("selected_candidate.tie_break_term" if signals.selected_tie_break_term is not None else "missing")
        ),
        "vp_progress_available": bool(signals.objective_progress_delta is not None or signals.selected_tie_break_term is not None),
        "objective_converted": int(signals.objective_converted),
        "objective_best_vp_id": str(signals.objective_best_vp_id),
        "target_vp": str(signals.objective_best_vp_id or ""),
        "target_vp_why": (
            "objective_best_vp_id"
            if str(signals.objective_best_vp_id or "").strip()
            else "missing_objective_best_vp_id"
        ),
        "strategy_label": str(signals.strategy_label),
        "macro_posture": str(
            getattr(signals, "macro_posture", None)
            or field_fn(transition_info, "macro_posture", None)
            or (
                "ASSAULT_VP"
                if sum(1 for owner in after_vp_owner.values() if str(owner).upper() == str(core.active_side).upper())
                <= sum(1 for owner in after_vp_owner.values() if str(owner).upper() not in {"", "NEUTRAL", str(core.active_side).upper()})
                else "DEFENSIVE_HOLD"
            )
        ),
        "macro_target_vp_id": str(
            getattr(signals, "macro_target_vp_id", None)
            or field_fn(transition_info, "macro_target_vp_id", None)
            or str(signals.objective_best_vp_id or "")
        ),
        "unit_macro_role": str(
            getattr(signals, "unit_macro_role", None)
            or field_fn(transition_info, "unit_macro_role", None)
            or "ROLE_SPEARHEAD"
        ),
        "role_assigned": str(
            getattr(signals, "role_assigned", None)
            or field_fn(transition_info, "role_assigned", None)
            or getattr(signals, "unit_macro_role", None)
            or field_fn(transition_info, "unit_macro_role", None)
            or "ROLE_SPEARHEAD"
        ),
        "role_is_mutated": bool(
            getattr(signals, "role_is_mutated", None)
            if getattr(signals, "role_is_mutated", None) is not None
            else field_fn(transition_info, "role_is_mutated", False)
        ),
        "role_mutation_reason": str(
            getattr(signals, "role_mutation_reason", None)
            or field_fn(transition_info, "role_mutation_reason", "DEFAULT_PROFILE")
            or "DEFAULT_PROFILE"
        ),
        "prior_boost_applied": float(
            getattr(signals, "prior_boost_applied", None)
            if getattr(signals, "prior_boost_applied", None) is not None
            else field_fn(transition_info, "prior_boost_applied", 0.0)
            or 0.0
        ),
        "badge_label": str(
            getattr(signals, "badge_label", None)
            or field_fn(transition_info, "badge_label", "")
            or ""
        ),
        "tie_break_term": (float(signals.selected_tie_break_term) if signals.selected_tie_break_term is not None else None),
        "vp_distance_vector": dict(signals.vp_distance_vector),
        "vp_distance_vector_size": int(len(signals.vp_distance_vector)),
        "unit_prefilter_enabled": bool(prefilter.unit_prefilter_enabled),
        "unit_prefilter_enabled_source": str(prefilter.unit_prefilter_enabled_source),
        "unit_prefilter_enabled_available": True,
        "unit_prefilter_selected_unit_id": str(prefilter.unit_prefilter_selected_unit_id),
        "unit_prefilter_replan_evaluated_units": list(prefilter.replan_evaluated_units),
        "unit_prefilter_replan_units_evaluated_count": int(len(prefilter.replan_evaluated_units)),
        "unit_prefilter_replan_virtual_simulations_total": int(
            sum(
                int(max(0, int(u.get("total_visits", 0) or 0)))
                for u in list(prefilter.replan_evaluated_units or [])
                if isinstance(u, dict)
            )
        ),
        "unit_prefilter_constrained_count": (
            int(prefilter.unit_prefilter_constrained_count)
            if prefilter.unit_prefilter_constrained_count is not None
            else None
        ),
        "unit_prefilter_constrained_count_source": str(prefilter.unit_prefilter_constrained_count_source),
        "unit_prefilter_constrained_count_available": bool(prefilter.unit_prefilter_constrained_count is not None),
        "unit_prefilter_global_count": (
            int(prefilter.unit_prefilter_global_count)
            if prefilter.unit_prefilter_global_count is not None
            else None
        ),
        "unit_prefilter_global_count_source": str(prefilter.unit_prefilter_global_count_source),
        "unit_prefilter_global_count_available": bool(prefilter.unit_prefilter_global_count is not None),
        "unit_positions": list(unit_positions_snapshot),
        "unit_hp_map": dict(unit_hp_snapshot),
        "unit_alive_map": dict(unit_alive_snapshot),
        "unit_suppressed_map": dict(unit_suppressed_snapshot),
        "vp_map_before": dict(before_vp_owner),
        "vp_map_after": dict(after_vp_owner),
        "vp_map": dict(after_vp_owner),
        "obs_enemy_vp_threat_map": (
            dict(field_fn(transition_info, "obs_enemy_vp_threat_map", {}) or {})
            if field_fn(transition_info, "obs_enemy_vp_threat_map", None) is not None
            else {}
        ),
        "obs_terrain_type_map": terrain_type_payload,
        "obs_terrain_cover_map": terrain_cover_payload,
        "obs_terrain_los_block_map": terrain_los_payload,
        "obs_terrain_move_cost_map": terrain_move_payload,
        "obs_fortification_type_map": fort_type_payload,
        "obs_fortification_edge_map": fort_edge_payload,
        "obs_reachable_hex_mask_by_unit": (
            dict(field_fn(transition_info, "obs_reachable_hex_mask_by_unit", {}) or {})
            if field_fn(transition_info, "obs_reachable_hex_mask_by_unit", None) is not None
            else {}
        ),
        "obs_attackable_hex_mask_by_unit": (
            dict(field_fn(transition_info, "obs_attackable_hex_mask_by_unit", {}) or {})
            if field_fn(transition_info, "obs_attackable_hex_mask_by_unit", None) is not None
            else {}
        ),
        "obs_enemy_reaction_fire_risk": (
            float(signals.obs_enemy_reaction_fire_risk_value)
            if signals.obs_enemy_reaction_fire_risk_value is not None
            else 0.0
        ),
        "obs_vp_ownership_ttl": (
            dict(field_fn(transition_info, "obs_vp_ownership_ttl", {}) or {})
            if field_fn(transition_info, "obs_vp_ownership_ttl", None) is not None
            else {}
        ),
        "objective_signal_definition_version": "vp_objective_v2",
        "telemetry_schema_version": "head_telemetry_v1",
        "telemetry_heads": dict(head_states),
        "telemetry_coverage_status": str(telemetry_coverage_status),
        "telemetry_coverage_reason": str(telemetry_coverage_reason),
        "dice_rolls": [*list(attack_dice_rolls), *list(defense_dice_rolls)],
        "attack_dice_rolls": list(attack_dice_rolls),
        "defense_dice_rolls": list(defense_dice_rolls),
        "attack_components_by_die": attack_components_payload,
        "defense_components_by_die": defense_components_payload,
        "runtime_events": runtime_events_payload,
        "action_mismatch": False,
        "units": list(post_units_snapshot),
    }
