from __future__ import annotations

from typing import Dict, List, Optional


def choose_action_with_mcts(
    *,
    legal_for_step: List[str],
    obs_units: List[object],
    obs_vp_hexes: List[object],
    active_side: str,
    obs_vp_owner_by_hex: Dict[str, str],
    unit_prefilter_enabled: bool,
    unit_prefilter_replan_enabled: bool,
    unit_prefilter_top_k: int,
    unit_prefilter_vp_progress_weight: float,
    unit_prefilter_capture_opportunity_weight: float,
    unit_prefilter_threat_weight: float,
    terrain_cover_by_hex: Dict[str, float],
    terrain_los_block_by_hex: Dict[str, float],
    priors: Optional[Dict[str, float]],
    values: Optional[Dict[str, float]],
    signs: Optional[Dict[str, int]],
    mcts_simulations: int,
    mcts_c_puct: float,
    mcts_temperature: float,
    mcts_dirichlet_alpha: float,
    mcts_dirichlet_epsilon: float,
    mcts_q_clip_abs: float,
    mcts_q_root_normalization_mode: str,
    mcts_q_root_normalization_strength: float,
    mcts_value_rescale_mode: str,
    mcts_value_rescale_temperature: float,
    mcts_success_prob_enabled: bool,
    mcts_success_prob_alpha: float,
    mcts_success_prob_center: float,
    mcts_success_prob_scale: float,
    mcts_success_prob_centered_clip_abs: float,
    mcts_min_root_visits_per_action: int,
    mcts_min_root_visits_top_n: int,
    run_policy_mcts_fn,
    unit_prefilter_ranking_fn,
) -> dict[str, object]:
    legal_actions_list = [str(a) for a in list(legal_for_step or [])]
    unit_actions_index: Dict[str, List[str]] = {}
    for action_id in legal_actions_list:
        parts = str(action_id).split(":")
        if len(parts) <= 1:
            continue
        uid = str(parts[1] or "")
        if not uid:
            continue
        unit_actions_index.setdefault(uid, []).append(str(action_id))

    unit_prefilter_requested = bool(unit_prefilter_enabled) or bool(unit_prefilter_replan_enabled)
    mcts_out = None
    action = ""
    replan_evaluated_units: list[dict[str, object]] = []
    if unit_prefilter_requested and bool(unit_prefilter_replan_enabled):
        selected_unit_id, _selected_actions, ranking_rows = unit_prefilter_ranking_fn(
            legal_actions=list(legal_actions_list),
            units=[dict(u or {}) for u in list(obs_units or []) if isinstance(u, dict)],
            vp_hexes=[dict(v or {}) for v in list(obs_vp_hexes or []) if isinstance(v, dict)],
            vp_owner_by_hex=dict(obs_vp_owner_by_hex or {}),
            to_play=str(active_side),
            terrain_cover_by_hex=dict(terrain_cover_by_hex or {}),
            terrain_los_block_by_hex=dict(terrain_los_block_by_hex or {}),
            top_k=max(1, int(unit_prefilter_top_k)),
            vp_progress_weight=float(unit_prefilter_vp_progress_weight),
            capture_opportunity_weight=float(unit_prefilter_capture_opportunity_weight),
            threat_weight=float(unit_prefilter_threat_weight),
        )
        ranked_unit_ids = [str((r or {}).get("unit_id", "")).strip() for r in list(ranking_rows or [])]
        ranked_unit_ids = [u for u in ranked_unit_ids if u]
        if selected_unit_id and selected_unit_id not in ranked_unit_ids:
            ranked_unit_ids.insert(0, str(selected_unit_id))
        if not ranked_unit_ids:
            ranked_unit_ids = sorted(list(unit_actions_index.keys()))
        best_plan = None
        effective_prefilter_top_k = max(3, max(1, int(unit_prefilter_top_k)))
        for unit_id in ranked_unit_ids[:effective_prefilter_top_k]:
            unit_actions = list(unit_actions_index.get(str(unit_id), []) or [])
            if not unit_actions:
                continue
            priors_u = {str(a): float(priors.get(str(a), 0.0)) for a in unit_actions} if isinstance(priors, dict) else None
            values_u = {str(a): float(values.get(str(a), 0.0)) for a in unit_actions} if isinstance(values, dict) else None
            signs_u = {str(a): int(signs.get(str(a), 1)) for a in unit_actions} if isinstance(signs, dict) else None
            effective_min_root_visits = int(mcts_min_root_visits_per_action)
            effective_min_root_top_n = int(mcts_min_root_visits_top_n)
            mcts_u = run_policy_mcts_fn(
                legal_actions=unit_actions,
                num_simulations=mcts_simulations,
                c_puct=mcts_c_puct,
                temperature=mcts_temperature,
                dirichlet_alpha=float(mcts_dirichlet_alpha),
                dirichlet_epsilon=float(mcts_dirichlet_epsilon),
                priors_by_action=priors_u,
                values_by_action=values_u,
                value_sign_by_action=signs_u,
                q_clip_abs=float(mcts_q_clip_abs),
                q_root_normalization_mode=str(mcts_q_root_normalization_mode),
                q_root_normalization_strength=float(mcts_q_root_normalization_strength),
                value_rescale_mode=str(mcts_value_rescale_mode),
                value_rescale_temperature=float(mcts_value_rescale_temperature),
                success_prob_enabled=bool(mcts_success_prob_enabled),
                success_prob_alpha=float(mcts_success_prob_alpha),
                success_prob_center=float(mcts_success_prob_center),
                success_prob_scale=float(mcts_success_prob_scale),
                success_prob_centered_clip_abs=float(mcts_success_prob_centered_clip_abs),
                min_root_visits_per_action=int(effective_min_root_visits),
                min_root_visits_top_n=int(effective_min_root_top_n),
            )
            chosen_u = str(getattr(mcts_u, "chosen_action", "") or "")
            probs_u = [float(x) for x in list(getattr(mcts_u, "probs", []) or [])]
            actions_u = [str(x) for x in list(getattr(mcts_u, "actions", []) or [])]
            chosen_prob_u = 0.0
            for aid_u, p_u in zip(actions_u, probs_u):
                if str(aid_u) == str(chosen_u):
                    chosen_prob_u = float(p_u)
                    break
            if chosen_prob_u <= 0.0 and probs_u:
                chosen_prob_u = float(max(probs_u))
            visits_u = [int(v) for v in list(getattr(mcts_u, "visits", []) or [])]
            chosen_visits_u = 0
            for aid_u, v_u in zip(actions_u, visits_u):
                if str(aid_u) == str(chosen_u):
                    chosen_visits_u = int(v_u)
                    break
            replan_evaluated_units.append(
                {
                    "unit_id": str(unit_id),
                    "root_actions_count": int(len(actions_u)),
                    "active_actions_count": int(sum(1 for v in visits_u if int(v) > 0)),
                    "total_visits": int(sum(visits_u)),
                    "chosen_action": str(chosen_u),
                    "chosen_prob": float(chosen_prob_u),
                    "chosen_visits": int(chosen_visits_u),
                    "forced_min_root_visits_per_action": int(effective_min_root_visits),
                    "forced_min_root_visits_top_n": int(effective_min_root_top_n),
                    "actions": list(actions_u),
                    "visits": list(visits_u),
                    "probs": list(probs_u),
                }
            )
            plan = {
                "unit_id": str(unit_id),
                "mcts": mcts_u,
                "chosen_action": chosen_u,
                "chosen_prob": float(chosen_prob_u),
                "chosen_visits": int(chosen_visits_u),
            }
            if best_plan is None:
                best_plan = plan
            else:
                if (
                    float(plan["chosen_prob"]) > float(best_plan["chosen_prob"])
                    or (
                        abs(float(plan["chosen_prob"]) - float(best_plan["chosen_prob"])) <= 1e-12
                        and int(plan["chosen_visits"]) > int(best_plan["chosen_visits"])
                    )
                ):
                    best_plan = plan
        if best_plan is not None:
            mcts_out = best_plan["mcts"]
            action = str(best_plan["chosen_action"] or "")
    if mcts_out is None:
        mcts_out = run_policy_mcts_fn(
            legal_actions=list(legal_actions_list),
            num_simulations=mcts_simulations,
            c_puct=mcts_c_puct,
            temperature=mcts_temperature,
            dirichlet_alpha=float(mcts_dirichlet_alpha),
            dirichlet_epsilon=float(mcts_dirichlet_epsilon),
            priors_by_action=priors,
            values_by_action=values,
            value_sign_by_action=signs,
            q_clip_abs=float(mcts_q_clip_abs),
            q_root_normalization_mode=str(mcts_q_root_normalization_mode),
            q_root_normalization_strength=float(mcts_q_root_normalization_strength),
            value_rescale_mode=str(mcts_value_rescale_mode),
            value_rescale_temperature=float(mcts_value_rescale_temperature),
            success_prob_enabled=bool(mcts_success_prob_enabled),
            success_prob_alpha=float(mcts_success_prob_alpha),
            success_prob_center=float(mcts_success_prob_center),
            success_prob_scale=float(mcts_success_prob_scale),
            success_prob_centered_clip_abs=float(mcts_success_prob_centered_clip_abs),
            min_root_visits_per_action=int(mcts_min_root_visits_per_action),
            min_root_visits_top_n=int(mcts_min_root_visits_top_n),
        )
        action = str(getattr(mcts_out, "chosen_action", "") or "")
    return {
        "unit_prefilter_requested": bool(unit_prefilter_requested),
        "mcts_out": mcts_out,
        "action": str(action),
        "replan_evaluated_units": list(replan_evaluated_units),
    }
