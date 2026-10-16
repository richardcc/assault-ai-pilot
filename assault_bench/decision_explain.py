from __future__ import annotations

from typing import Dict, List, Optional

from assault_bench.decision_signals import (
    select_action_with_probability_tie_break as _ds_select_action_with_probability_tie_break,
)
from assault_bench.vp_action_utils import (
    capturable_vp_hexes_for_side as _vp_capturable_vp_hexes_for_side,
    is_move_action_kind as _vp_is_move_action_kind,
    parse_action_target_hex as _vp_parse_action_target_hex,
)
from assault_bench.vp_explain_utils import (
    backfill_why_action_vs_vp_from_observed_transition as _vx_backfill_why_action_vs_vp_from_observed_transition,
    build_why_action_vs_vp as _vx_build_why_action_vs_vp,
)


def _select_action_with_probability_tie_break(
    *,
    sampled_action: str,
    actions: List[str],
    probs: List[float],
    visits: List[int],
    breakdown_by_action: Dict[str, Dict[str, object]],
    side: str,
    vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
    tie_tol: float = 1e-12,
) -> tuple[str, str]:
    return _ds_select_action_with_probability_tie_break(
        sampled_action=sampled_action,
        actions=actions,
        probs=probs,
        visits=visits,
        breakdown_by_action=breakdown_by_action,
        side=side,
        vp_hexes=vp_hexes,
        vp_owner_by_hex=vp_owner_by_hex,
        tie_tol=tie_tol,
        capturable_vp_hexes_for_side_fn=_vp_capturable_vp_hexes_for_side,
        parse_action_target_hex_fn=_vp_parse_action_target_hex,
        is_move_action_kind_fn=_vp_is_move_action_kind,
    )


def _build_why_action_vs_vp(
    *,
    legal_actions: List[str],
    chosen_action: str,
    priors_by_action: Optional[Dict[str, float]],
    values_by_action: Optional[Dict[str, float]],
    value_sign_by_action: Optional[Dict[str, int]],
    visits_by_action: Dict[str, int],
    c_puct: float,
    dynamics_pred_reward: Optional[float],
    acting_unit_q: Optional[int],
    acting_unit_r: Optional[int],
    step_units_snapshot: Optional[List[object]] = None,
    vp_hexes: List[object],
    active_side: str = "",
    vp_owner_by_hex: Optional[Dict[str, str]] = None,
    top_k: Optional[int] = None,
    objective_best_vp_id: str = "",
    q_clip_abs: Optional[float] = 10.0,
    value_rescale_mode: str = "tanh",
    value_rescale_temperature: float = 10.0,
) -> Dict[str, object]:
    return _vx_build_why_action_vs_vp(
        legal_actions=legal_actions,
        chosen_action=chosen_action,
        priors_by_action=priors_by_action,
        values_by_action=values_by_action,
        value_sign_by_action=value_sign_by_action,
        visits_by_action=visits_by_action,
        c_puct=c_puct,
        dynamics_pred_reward=dynamics_pred_reward,
        acting_unit_q=acting_unit_q,
        acting_unit_r=acting_unit_r,
        step_units_snapshot=step_units_snapshot,
        vp_hexes=vp_hexes,
        active_side=active_side,
        vp_owner_by_hex=vp_owner_by_hex,
        top_k=top_k,
        objective_best_vp_id=objective_best_vp_id,
        q_clip_abs=q_clip_abs,
        value_rescale_mode=value_rescale_mode,
        value_rescale_temperature=value_rescale_temperature,
    )


def _backfill_why_action_vs_vp_from_observed_transition(
    *,
    why_action_vs_vp: Dict[str, object],
    chosen_action: str,
    objective_progress_delta: Optional[float],
    objective_best_vp_id: str = "",
    legal_actions: Optional[List[str]] = None,
) -> Dict[str, object]:
    return _vx_backfill_why_action_vs_vp_from_observed_transition(
        why_action_vs_vp=why_action_vs_vp,
        chosen_action=chosen_action,
        objective_progress_delta=objective_progress_delta,
        objective_best_vp_id=objective_best_vp_id,
        legal_actions=legal_actions,
    )
