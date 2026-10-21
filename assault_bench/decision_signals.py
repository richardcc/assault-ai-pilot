from __future__ import annotations

from typing import Callable, Dict, List, Optional

from assault_bench.action_utils import action_kind_from_id, action_unit_id_from_id
from assault_bench.telemetry_models import normalize_side_key
from assault_bench.transform_ops import filter_rows, to_dict_rows


def _axial_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    dq = int(q2) - int(q1)
    dr = int(r2) - int(r1)
    ds = -dq - dr
    return int((abs(dq) + abs(dr) + abs(ds)) / 2)


def obs_enemy_reaction_fire_risk_for_step(
    *,
    legal_actions: List[str],
    units: List[object],
    actor_side: str,
) -> float:
    # OPPORTUNITY_FIRE decommissioned in VOEC; directly compute spatial proximity pressure
    side_norm = normalize_side_key(actor_side)
    actor_coords = []
    enemy_coords = []
    for u in list(units or []):
        if isinstance(u, dict):
            alive = bool(u.get("alive", True))
            side = normalize_side_key(u.get("side", ""))
            q = u.get("q")
            r = u.get("r")
        else:
            alive = bool(getattr(u, "alive", True))
            side = normalize_side_key(getattr(u, "side", ""))
            q = getattr(u, "q", None)
            r = getattr(u, "r", None)
        if not alive or not isinstance(q, int) or not isinstance(r, int) or not side:
            continue
        if side == side_norm:
            actor_coords.append((int(q), int(r)))
        else:
            enemy_coords.append((int(q), int(r)))

    if not actor_coords or not enemy_coords:
        return 0.0

    radius = 6.0
    min_dist = 999.0
    for aq, ar in actor_coords:
        for eq, er in enemy_coords:
            d = float(_axial_distance(aq, ar, eq, er))
            if d <= 1.0:
                return 1.0
            if d < min_dist:
                min_dist = d
    if min_dist >= radius:
        return 0.0
    return float(max(0.0, min(1.0, (radius - min_dist) / radius)))


def reaction_exposure_component_for_step(
    *,
    action_kind: str,
    obs_enemy_reaction_fire_risk: float,
    reward_shaping: Optional[Dict[str, object]],
) -> tuple[float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(cfg.get("reaction_exposure_component_enabled", True))
    if not enabled:
        return 0.0, "disabled"
    kind = str(action_kind or "").strip().upper()
    if kind.startswith("OPPORTUNITY_"):
        return 0.0, "reaction_action"
    weight = float(cfg.get("reaction_exposure_component_weight", 0.08) or 0.0)
    if weight == 0.0:
        return 0.0, "zero_weight"
    cap = abs(float(cfg.get("reaction_exposure_component_cap_abs", 0.20) or 0.20))
    risk = max(0.0, min(1.0, float(obs_enemy_reaction_fire_risk)))
    factor = 0.8
    if "MOVE" in kind:
        factor = 1.0
    elif kind in {"ASSAULT", "MELEE", "ASSAULT_MELEE"}:
        factor = 1.15
    elif kind in {"WAIT", "TIMEOUT"}:
        factor = 0.25
    component = -float(weight) * float(risk) * float(factor)
    if cap > 0.0:
        component = max(-cap, min(cap, component))
    return float(component), "risk_by_action_kind"


def reaction_fire_soft_signal_for_step(
    *,
    action_kind: str,
    expected_damage_proxy: float,
    reward_shaping: Optional[Dict[str, object]],
) -> tuple[float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(cfg.get("reaction_fire_soft_signal_enabled", True))
    if not enabled:
        return 0.0, "disabled"
    kind = str(action_kind or "").strip().upper()
    if kind != "OPPORTUNITY_FIRE":
        return 0.0, "non_reaction_action"
    weight = float(cfg.get("reaction_fire_soft_signal_weight", 0.04) or 0.0)
    if weight == 0.0:
        return 0.0, "zero_weight"
    damage_scale = float(cfg.get("reaction_fire_soft_signal_expected_damage_scale", 4.0) or 4.0)
    proxy_prob = max(0.0, min(1.0, float(expected_damage_proxy) / max(1e-6, float(damage_scale))))
    centered = (2.0 * float(proxy_prob)) - 1.0
    return float(weight * centered), "expected_damage_proxy"


def vp_horizon_soft_components_for_step(
    *,
    reward_shaping: Optional[Dict[str, object]],
    objective_had_opportunity: int,
    baseline_horizon_steps: Optional[float],
    vp_progress_delta: float,
) -> tuple[float, float, float, str]:
    cfg = dict(reward_shaping or {})
    enabled = bool(cfg.get("vp_horizon_soft_enabled", True))
    if not enabled:
        return 0.0, -1.0, 0.0, "disabled"
    if int(objective_had_opportunity) <= 0:
        return 0.0, -1.0, 0.0, "no_opportunity"
    weight = float(cfg.get("vp_horizon_soft_weight", 0.02) or 0.0)
    if weight == 0.0:
        return 0.0, -1.0, 0.0, "zero_weight"
    horizon_cap = max(1.0, float(cfg.get("vp_horizon_soft_cap_steps", 8.0) or 8.0))
    base = (
        float(baseline_horizon_steps)
        if isinstance(baseline_horizon_steps, (int, float))
        else float(horizon_cap)
    )
    projected = max(0.0, min(horizon_cap, float(base) - max(0.0, float(vp_progress_delta))))
    signal = max(0.0, min(1.0, (horizon_cap - float(projected)) / float(horizon_cap)))
    centered = max(-1.0, min(1.0, (2.0 * float(signal)) - 1.0))
    component = float(weight * centered)
    return float(component), float(projected), float(signal), "progress_projection"


def select_action_with_probability_tie_break(
    *,
    sampled_action: str,
    actions: List[str],
    probs: List[float],
    visits: List[int],
    breakdown_by_action: Dict[str, Dict[str, object]],
    side: str,
    vp_hexes: List[object],
    vp_owner_by_hex: Dict[str, str],
    capturable_vp_hexes_for_side_fn: Callable[..., set[tuple[int, int]]],
    parse_action_target_hex_fn: Callable[[str], Optional[tuple[int, int]]],
    is_move_action_kind_fn: Callable[[str], bool],
    tie_tol: float = 1e-12,
) -> tuple[str, str]:
    sampled = str(sampled_action or "")
    action_list = [str(a or "") for a in list(actions or []) if str(a or "").strip()]
    if not action_list:
        return sampled, "mcts_prob_sample"
    probs_by_action: Dict[str, float] = {}
    visits_by_action: Dict[str, int] = {}
    for aid, p in zip(action_list, list(probs or [])):
        probs_by_action[str(aid)] = float(p)
    for aid, v in zip(action_list, list(visits or [])):
        visits_by_action[str(aid)] = int(v)
    if not probs_by_action:
        return sampled if sampled else action_list[0], "mcts_prob_sample"
    max_prob = max(float(v) for v in probs_by_action.values())
    tied = [
        aid
        for aid in action_list
        if abs(float(probs_by_action.get(aid, 0.0)) - float(max_prob)) <= float(max(0.0, tie_tol))
    ]
    if len(tied) <= 1:
        return sampled if sampled else tied[0], "mcts_prob_sample"
    capturable_hexes = capturable_vp_hexes_for_side_fn(
        side=str(side),
        vp_hexes=list(vp_hexes or []),
        vp_owner_by_hex=dict(vp_owner_by_hex or {}),
    )

    def _tie_key(aid: str) -> tuple[int, int, float, float, str]:
        target = parse_action_target_hex_fn(str(aid))
        is_capture_move = int(
            is_move_action_kind_fn(action_kind_from_id(str(aid)))
            and target is not None
            and (int(target[0]), int(target[1])) in capturable_hexes
        )
        v = int(visits_by_action.get(str(aid), 0))
        b = dict(breakdown_by_action.get(str(aid), {}) or {})
        puct = float(b.get("puct_score", 0.0) or 0.0)
        q = float(b.get("q_value", 0.0) or 0.0)
        return (-is_capture_move, -v, -puct, -q, str(aid))

    best = sorted(tied, key=_tie_key)[0]
    return str(best), "mcts_prob_tie_break_capture_visits_score"
