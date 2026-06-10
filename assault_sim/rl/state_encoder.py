import numpy as np

from assault_sim.rl.features.tactical_features import compute_tactical_features
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.terrain_config import terrain_config

# -------------------------------------------------
# MAP / TERRAIN FEATURE CONSTANTS
# -------------------------------------------------
TERRAIN_KEYS = [
    "clear",
    "water",
    "light_forest",
    "olive_vine_grove",
    "brush",
    "rocky",
    "building_single",
    "building_multi",
]

FORT_KEYS = [
    "none",
    "trench",
    "bunker",
    "casemate",
    "gun_emplacement",
    "barbed_wire",
    "minefield",
]


def _one_hot(value: str, keys: list[str]):
    vec = [0.0] * len(keys)
    try:
        idx = keys.index(value)
        vec[idx] = 1.0
    except ValueError:
        pass
    return vec


def _terrain_name_of(state, q: int, r: int) -> str:
    h = state.game_map.get_hex(q, r)
    if h is None:
        return "clear"
    return str(h.get_terrain())


def _fort_data_of(state, q: int, r: int):
    get_data = getattr(state.game_map, "get_hex_fortification_data", None)
    if callable(get_data):
        data = get_data(q, r) or {}
        ftype = str(data.get("type", "none")) if data else "none"
        orient = data.get("orientation", None)
        return ftype, orient
    get_type = getattr(state.game_map, "get_hex_fortification", None)
    if callable(get_type):
        ftype = get_type(q, r) or "none"
        return str(ftype), None
    return "none", None


def _encode_orientation_1_to_6(orientation):
    if orientation is None:
        return [0.0, 0.0]
    try:
        o = int(orientation)
        if o < 1 or o > 6:
            return [0.0, 0.0]
        angle = (o - 1) * (2.0 * np.pi / 6.0)
        return [float(np.cos(angle)), float(np.sin(angle))]
    except Exception:
        return [0.0, 0.0]


def _local_map_features(state, center_q: int, center_r: int):
    """
    Compact local map summary around active unit.
    """
    ring_offsets = [
        (+1, 0), (-1, 0), (0, +1), (0, -1), (+1, -1), (-1, +1),
    ]
    total = 0
    rough = 0
    blocked = 0
    built = 0
    fortified = 0

    for dq, dr in ring_offsets:
        q = center_q + dq
        r = center_r + dr
        h = state.game_map.get_hex(q, r)
        if h is None:
            continue
        total += 1
        t = str(h.get_terrain())
        if t in ("light_forest", "olive_vine_grove", "brush", "rocky"):
            rough += 1
        if t == "water":
            blocked += 1
        if t in ("building_single", "building_multi"):
            built += 1
        ftype, _ = _fort_data_of(state, q, r)
        if ftype != "none":
            fortified += 1

    denom = max(1, total)
    return [
        rough / denom,
        blocked / denom,
        built / denom,
        fortified / denom,
    ]


# =================================================
# NUMERIC STATE (USED BY RL)
# =================================================
def _objective_outcome_features(state, rl_side=None, scenario=None):
    """
    Encode scenario objective progress for RL.
    Returns a fixed-size vector:
      [has_rule, rl_is_tracked, captured_norm, total_norm, progress_to_next_norm, turns_pressure]
    """
    if scenario is None:
        return [0.0] * 6
    outcomes = getattr(scenario, "victory_outcomes", None) or {}
    metric = str(outcomes.get("metric", "")).strip()
    timing = str(outcomes.get("timing", "")).strip()
    tracked_side = str(outcomes.get("tracked_side", "")).strip().upper()
    table = outcomes.get("table", [])
    if metric != "objectives_captured" or timing != "end_of_last_turn" or not tracked_side or not table:
        return [0.0] * 6

    side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
    ownership_for_tracked = side_to_ownership.get(tracked_side)
    points = getattr(getattr(state, "victory", None), "points", []) or []
    total = len(points)
    captured = 0
    for vp in points:
        hs = state.hex_states.get(vp.hex_coords)
        if hs is not None and hs.ownership == ownership_for_tracked:
            captured += 1

    # nearest threshold from table for normalization guidance
    thresholds = []
    for row in table:
        if not isinstance(row, dict):
            continue
        cap = row.get("captured", {}) or {}
        try:
            thresholds.append(int(cap.get("min", 0)))
        except Exception:
            continue
    thresholds = sorted(set(thresholds))
    next_threshold = next((t for t in thresholds if captured < t), captured)
    denom = max(1, total)
    progress_to_next = (next_threshold - captured) / denom
    progress_to_next = float(np.clip(progress_to_next, 0.0, 1.0))

    max_turns = getattr(scenario, "max_turns", None) or 0
    turns_pressure = 0.0
    if max_turns > 0:
        turns_pressure = float(np.clip(state.turn / max_turns, 0.0, 1.0))

    return [
        1.0,
        1.0 if (rl_side and str(rl_side).upper() == tracked_side) else 0.0,
        float(np.clip(captured / denom, 0.0, 1.0)),
        float(np.clip(total / 10.0, 0.0, 1.0)),  # stable bounded scale
        progress_to_next,
        turns_pressure,
    ]


LAST_ACTION_KEYS = ["wait", "move", "direct", "indirect", "assault"]


def _ownership_for_side(state, side):
    side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
    key = str(getattr(side, "value", side) or "").upper()
    if not key:
        return None
    direct = side_to_ownership.get(key)
    if direct is not None:
        return direct
    for k, v in side_to_ownership.items():
        if str(getattr(k, "value", k) or "").upper() == key:
            return v
    return None


def _uncaptured_vp_hexes(state, side):
    points = getattr(getattr(state, "victory", None), "points", []) or []
    own_ownership = _ownership_for_side(state, side)
    uncaptured = []
    for vp in points:
        hs = state.hex_states.get(vp.hex_coords)
        if hs is None or hs.ownership != own_ownership:
            uncaptured.append(vp.hex_coords)
    return uncaptured


def _focus_vp_from_plan_or_nearest(state, active, rl_side, focus_vp_id: str | None):
    if active is None or getattr(active, "position", None) is None:
        return None
    uncaptured = _uncaptured_vp_hexes(state, rl_side)
    if not uncaptured:
        return None

    if focus_vp_id:
        try:
            q_s, r_s = str(focus_vp_id).split(",")
            candidate = (int(q_s), int(r_s))
            if candidate in uncaptured:
                return candidate
        except Exception:
            pass

    return min(uncaptured, key=lambda p: safe_hex_distance(active.position, p))


def _lote_a_macro_vp_features(state, active, rl_side, focus_vp_id: str | None):
    if active is None or getattr(active, "position", None) is None or rl_side is None:
        return 0.0, 0.0, 0.0

    focus_vp = _focus_vp_from_plan_or_nearest(state, active, rl_side, focus_vp_id)
    if focus_vp is None:
        return 0.0, 0.0, 0.0

    dist = safe_hex_distance(active.position, focus_vp)
    focus_vp_dist_norm = float(np.clip(dist / 10.0, 0.0, 1.0))

    actions = ActionCatalog(state, active, terrain_config).actions()
    reachable_now = 0.0
    enterable_now = 0.0
    uncaptured = set(_uncaptured_vp_hexes(state, rl_side))
    for action in actions:
        if getattr(getattr(action, "action_type", None), "category", None) != ActionCategory.MOVEMENT:
            continue
        path = getattr(action, "path", None) or []
        if not path:
            continue
        end = path[-1]
        end_pos = (end.q, end.r)
        if safe_hex_distance(end, focus_vp) < dist:
            reachable_now = 1.0
        if end_pos in uncaptured:
            enterable_now = 1.0
        if reachable_now >= 1.0 and enterable_now >= 1.0:
            break

    return focus_vp_dist_norm, reachable_now, enterable_now


def _lote_c_coordination_features(
    state,
    active,
    rl_side,
    focus_vp_id: str | None,
    own_activated_ratio: float,
    enemy_activated_ratio: float,
    role_quota_remaining_norm: float,
):
    if active is None or getattr(active, "position", None) is None or rl_side is None:
        return 0.0, float(np.clip(role_quota_remaining_norm, 0.0, 1.0)), float(np.clip(1.0 - own_activated_ratio, 0.0, 1.0)), float(np.clip(1.0 - enemy_activated_ratio, 0.0, 1.0))

    focus_vp = _focus_vp_from_plan_or_nearest(state, active, rl_side, focus_vp_id)
    if focus_vp is None:
        allies_supporting_focus_ratio = 0.0
    else:
        allies = [
            u for u in (state.units or [])
            if getattr(u, "alive", True)
            and getattr(u, "position", None) is not None
            and str(getattr(u, "side", "")).upper() == str(rl_side).upper()
        ]
        if not allies:
            allies_supporting_focus_ratio = 0.0
        else:
            supporting = sum(1 for u in allies if safe_hex_distance(u.position, focus_vp) <= 3)
            allies_supporting_focus_ratio = float(supporting) / float(max(1, len(allies)))

    own_unactivated_ratio = float(np.clip(1.0 - own_activated_ratio, 0.0, 1.0))
    enemy_unactivated_ratio = float(np.clip(1.0 - enemy_activated_ratio, 0.0, 1.0))
    return (
        float(np.clip(allies_supporting_focus_ratio, 0.0, 1.0)),
        float(np.clip(role_quota_remaining_norm, 0.0, 1.0)),
        own_unactivated_ratio,
        enemy_unactivated_ratio,
    )


def _enemy_hex_risk(state, rl_side, pos) -> float:
    if pos is None or rl_side is None:
        return 0.0
    enemies = [
        u for u in (state.units or [])
        if getattr(u, "alive", True)
        and getattr(u, "position", None) is not None
        and str(getattr(u, "side", "")).upper() != str(rl_side).upper()
    ]
    risk = 0.0
    for e in enemies:
        d = safe_hex_distance(pos, e.position)
        if d <= 0:
            risk += 1.0
        elif d <= 4:
            risk += 1.0 / float(d)
    return float(np.clip(risk / 2.0, 0.0, 1.0))


def _los_exposure_for_hex(state, q: int, r: int) -> float:
    terrain_name = _terrain_name_of(state, q, r)
    los = str(terrain_config.get_los(terrain_name)).upper()
    if los == "BLOCKED":
        return 0.2
    if los == "HINDERED":
        return 0.6
    return 1.0


def _movement_type_for_unit(active) -> str:
    if active is None:
        return "infantry"
    cls = str(getattr(getattr(active, "unit_type", None), "classification", "")).upper()
    if "VEHICLE" in cls:
        return "vehicle"
    return "infantry"


def _lote_b_risk_terrain_features(state, active, rl_side, focus_vp_id: str | None):
    if active is None or getattr(active, "position", None) is None or rl_side is None:
        return 0.0, 0.0, 0.0, 0.0

    current_risk = _enemy_hex_risk(state, rl_side, active.position)
    best_progress_risk = current_risk
    terrain_mobility_cost_norm = 0.0
    los_exposure_next_hex = 0.0

    focus_vp = _focus_vp_from_plan_or_nearest(state, active, rl_side, focus_vp_id)
    if focus_vp is None:
        return current_risk, best_progress_risk, terrain_mobility_cost_norm, los_exposure_next_hex

    dist_now = safe_hex_distance(active.position, focus_vp)
    move_type = _movement_type_for_unit(active)
    best_move = None
    best_dist = None
    actions = ActionCatalog(state, active, terrain_config).actions()
    for action in actions:
        if getattr(getattr(action, "action_type", None), "category", None) != ActionCategory.MOVEMENT:
            continue
        path = getattr(action, "path", None) or []
        if not path:
            continue
        end = path[-1]
        end_dist = safe_hex_distance(end, focus_vp)
        if end_dist >= dist_now:
            continue
        if best_move is None or end_dist < best_dist:
            best_move = end
            best_dist = end_dist

    if best_move is not None:
        best_progress_risk = _enemy_hex_risk(state, rl_side, best_move)
        terrain_name = _terrain_name_of(state, best_move.q, best_move.r)
        move_cost = terrain_config.get_move_cost(terrain_name, move_type, default=1)
        cost_raw = float(move_cost if move_cost is not None else 4.0)
        terrain_mobility_cost_norm = float(np.clip((cost_raw - 1.0) / 3.0, 0.0, 1.0))
        los_exposure_next_hex = _los_exposure_for_hex(state, best_move.q, best_move.r)

    return (
        float(np.clip(current_risk, 0.0, 1.0)),
        float(np.clip(best_progress_risk, 0.0, 1.0)),
        float(np.clip(terrain_mobility_cost_norm, 0.0, 1.0)),
        float(np.clip(los_exposure_next_hex, 0.0, 1.0)),
    )


def _is_attack_like_action(action) -> bool:
    name = str(getattr(action.__class__, "__name__", "")).lower()
    return any(k in name for k in ("attack", "assault", "fire", "shoot"))


def _lote_e_opportunity_features(state, active, rl_side, focus_vp_id: str | None):
    if active is None or getattr(active, "position", None) is None or rl_side is None:
        return 0.0, 0.0, 0.0, 0.0

    focus_vp = _focus_vp_from_plan_or_nearest(state, active, rl_side, focus_vp_id)
    if focus_vp is None:
        return 0.0, 0.0, 0.0, 0.0

    dist_now = safe_hex_distance(active.position, focus_vp)
    own_ownership = _ownership_for_side(state, rl_side)
    actions = ActionCatalog(state, active, terrain_config).actions()

    best_advance_score = -1.0
    capture_window_open = 0.0
    for action in actions:
        if getattr(getattr(action, "action_type", None), "category", None) != ActionCategory.MOVEMENT:
            continue
        path = getattr(action, "path", None) or []
        if not path:
            continue
        end = path[-1]
        end_dist = safe_hex_distance(end, focus_vp)
        progress = float(dist_now - end_dist)
        progress_norm = float(np.clip(progress / 3.0, -1.0, 1.0))
        end_pos = (end.q, end.r)
        hs = state.hex_states.get(end_pos)
        enters_uncaptured_vp = 0.0
        if end_pos == focus_vp and (hs is None or hs.ownership != own_ownership):
            enters_uncaptured_vp = 1.0
        risk_penalty = _enemy_hex_risk(state, rl_side, end) * 0.6
        score = float(np.clip(progress_norm + enters_uncaptured_vp - risk_penalty, -1.0, 1.0))
        if score > best_advance_score:
            best_advance_score = score
        if enters_uncaptured_vp >= 1.0 and risk_penalty <= 0.4:
            capture_window_open = 1.0

    expected_vp_swing_if_advance = float(np.clip(best_advance_score, -1.0, 1.0))

    best_attack_score = -1.0
    for action in actions:
        if not _is_attack_like_action(action):
            continue
        target = getattr(action, "target", None)
        if target is None:
            tid = getattr(action, "target_id", None)
            if tid:
                target = next((u for u in (state.units or []) if getattr(u, "unit_id", None) == tid), None)
        if target is None or not getattr(target, "alive", False):
            continue
        adv_fn = getattr(active, "get_combat_advantage", None)
        exp_fn = getattr(active, "get_expected_damage", None)
        adv = float(adv_fn(target)) if callable(adv_fn) else 0.0
        exp_dmg = float(exp_fn(target)) if callable(exp_fn) else 0.0
        score = float(np.clip(0.7 * adv + 0.3 * np.clip(exp_dmg / 3.0, 0.0, 1.0), -1.0, 1.0))
        if score > best_attack_score:
            best_attack_score = score

    expected_trade_if_attack = float(np.clip(best_attack_score, -1.0, 1.0))

    attack_opportunity_cost_near_vp_norm = 0.0
    if dist_now <= 2:
        delta = expected_vp_swing_if_advance - expected_trade_if_attack
        attack_opportunity_cost_near_vp_norm = float(np.clip((delta + 1.0) / 2.0, 0.0, 1.0))

    return (
        attack_opportunity_cost_near_vp_norm,
        capture_window_open,
        expected_vp_swing_if_advance,
        expected_trade_if_attack,
    )


def encode_state(
    state,
    unit=None,
    rl_side=None,
    max_turns=None,
    scenario=None,
    own_activated_ratio: float = 0.0,
    enemy_activated_ratio: float = 0.0,
    last_action_type: str | None = None,
    focus_vp_progress_last_step: float = 0.0,
    focus_vp_id: str | None = None,
    role_quota_remaining_norm: float = 1.0,
    unit_stuck_steps_norm: float = 0.0,
    plan_commitment_age_norm: float = 0.0,
    intent_alignment_last_k: float = 0.0,
    last_failure_reason_onehot: list[float] | None = None,
):

    active = unit
    if active is None and rl_side is not None:
        # Fallback to first alive unit on RL side for global calls.
        active = next(
            (
                u for u in (state.units or [])
                if getattr(u, "alive", True) and u.side == rl_side and u.position is not None
            ),
            None,
        )

    # -------------------------
    # BASIC FEATURES
    # -------------------------
    active_hp = active.hp if active is not None else 0
    n_units = len(state.units) if state.units is not None else 0
    vp = state.vp_tracker.total_points if state.vp_tracker else 0

    # -------------------------
    # GLOBAL FORCE BALANCE
    # -------------------------
    if rl_side is not None and state.units is not None:
        own_units = [u for u in state.units if u.alive and u.side == rl_side]
        enemy_units = [u for u in state.units if u.alive and u.side != rl_side]

        own_units_alive = len(own_units)
        enemy_units_alive = len(enemy_units)

        own_total_hp = sum(u.hp for u in own_units)
        enemy_total_hp = sum(u.hp for u in enemy_units)
    else:
        own_units_alive = 0
        enemy_units_alive = 0
        own_total_hp = 0
        enemy_total_hp = 0
        own_units = []
        enemy_units = []

    max_units = max(1, n_units)
    max_hp = max(1, own_total_hp + enemy_total_hp)

    unit_balance = (own_units_alive - enemy_units_alive) / max_units
    hp_balance = (own_total_hp - enemy_total_hp) / max_hp

    # -------------------------
    # TIME PRESSURE
    # -------------------------
    if max_turns and max_turns > 0:
        time_progress = state.turn / max_turns
    else:
        time_progress = 0.0

    # -------------------------
    # DIRECTION TO ENEMY
    # -------------------------
    dq, dr = 0.0, 0.0
    closest_enemy = None

    if active is not None and enemy_units and active.position is not None:
        closest_enemy = min(
            enemy_units,
            key=lambda e: safe_hex_distance(active.position, e.position),
        )

        dq = np.clip((closest_enemy.position.q - active.position.q) / 10.0, -1.0, 1.0)
        dr = np.clip((closest_enemy.position.r - active.position.r) / 10.0, -1.0, 1.0)

    # -------------------------
    # DISTANCE TO VP
    # -------------------------
    vp_dist = 0.0

    if active is not None and state.vp_tracker and active.position is not None:
        vp_points = getattr(state.vp_tracker.conditions, "points", [])

        if vp_points:
            target_vp = min(
                vp_points,
                key=lambda p: safe_hex_distance(active.position, p.hex_coords)
            )

            dist = safe_hex_distance(active.position, target_vp.hex_coords)
            vp_dist = np.clip(dist / 10.0, 0.0, 1.0)

    # -------------------------
    # VISIBILITY
    # -------------------------
    visible_enemy = 0.0

    if active is not None and closest_enemy is not None:
        if closest_enemy.unit_id in getattr(active, "spotted_enemies", []):
            visible_enemy = 1.0

    # -------------------------
    # DISTANCE TO ENEMY
    # -------------------------
    enemy_dist = 0.0

    if active is not None and closest_enemy is not None:
        d = safe_hex_distance(active.position, closest_enemy.position)
        enemy_dist = np.clip(d / 10.0, 0.0, 1.0)

    # -------------------------
    # BASE VECTOR
    # -------------------------
    obs = [
        state.turn,
        active_hp,
        n_units,
        vp,

        unit_balance,
        hp_balance,
        time_progress,

        dq,
        dr,

        vp_dist,

        visible_enemy,
        enemy_dist,
    ]

    # =================================================
    # MAP AWARE FEATURES (terrain + fortifications)
    # =================================================
    if active is not None and active.position is not None:
        aq, ar = active.position.q, active.position.r
        terrain_here = _terrain_name_of(state, aq, ar)
        fort_here, orient_here = _fort_data_of(state, aq, ar)
        obs.extend(_one_hot(terrain_here, TERRAIN_KEYS))
        obs.extend(_one_hot(fort_here if fort_here in FORT_KEYS else "none", FORT_KEYS))
        obs.extend(_encode_orientation_1_to_6(orient_here))
        obs.extend(_local_map_features(state, aq, ar))
    else:
        obs.extend([0.0] * len(TERRAIN_KEYS))
        obs.extend([0.0] * len(FORT_KEYS))
        obs.extend([0.0, 0.0])  # orientation cos/sin
        obs.extend([0.0, 0.0, 0.0, 0.0])  # local map summary

    # =================================================
    # ✅ NEW: TACTICAL FEATURES (MODULAR)
    # =================================================
    obs.extend(compute_tactical_features(state, rl_side))
    obs.extend(_objective_outcome_features(state, rl_side=rl_side, scenario=scenario))
    obs.extend([
        float(np.clip(own_activated_ratio, 0.0, 1.0)),
        float(np.clip(enemy_activated_ratio, 0.0, 1.0)),
    ])
    obs.extend(_one_hot(str(last_action_type or ""), LAST_ACTION_KEYS))

    # =================================================
    # P4.2 LOT A: macro VP planning features
    # =================================================
    focus_vp_dist_norm, focus_vp_reachable_now, focus_vp_enterable_now = _lote_a_macro_vp_features(
        state=state,
        active=active,
        rl_side=rl_side,
        focus_vp_id=focus_vp_id,
    )
    obs.extend(
        [
            float(np.clip(focus_vp_dist_norm, 0.0, 1.0)),
            float(np.clip(focus_vp_progress_last_step, -1.0, 1.0)),
            float(np.clip(focus_vp_reachable_now, 0.0, 1.0)),
            float(np.clip(focus_vp_enterable_now, 0.0, 1.0)),
        ]
    )

    # =================================================
    # P4.2 LOT C: team coordination features
    # =================================================
    (
        allies_supporting_focus_ratio,
        role_quota_remaining_norm,
        own_unactivated_ratio,
        enemy_unactivated_ratio,
    ) = _lote_c_coordination_features(
        state=state,
        active=active,
        rl_side=rl_side,
        focus_vp_id=focus_vp_id,
        own_activated_ratio=own_activated_ratio,
        enemy_activated_ratio=enemy_activated_ratio,
        role_quota_remaining_norm=role_quota_remaining_norm,
    )
    obs.extend(
        [
            allies_supporting_focus_ratio,
            role_quota_remaining_norm,
            own_unactivated_ratio,
            enemy_unactivated_ratio,
        ]
    )

    # =================================================
    # P4.2 LOT B: risk and terrain features
    # =================================================
    (
        hex_risk_current,
        hex_risk_best_progress_path,
        terrain_mobility_cost_norm,
        los_exposure_next_hex,
    ) = _lote_b_risk_terrain_features(
        state=state,
        active=active,
        rl_side=rl_side,
        focus_vp_id=focus_vp_id,
    )
    obs.extend(
        [
            hex_risk_current,
            hex_risk_best_progress_path,
            terrain_mobility_cost_norm,
            los_exposure_next_hex,
        ]
    )

    # =================================================
    # P4.2 LOT D: plan memory features
    # =================================================
    onehot = list(last_failure_reason_onehot or [0.0, 0.0, 0.0, 0.0])
    if len(onehot) < 4:
        onehot.extend([0.0] * (4 - len(onehot)))
    onehot = [float(np.clip(v, 0.0, 1.0)) for v in onehot[:4]]
    obs.extend(
        [
            float(np.clip(unit_stuck_steps_norm, 0.0, 1.0)),
            float(np.clip(plan_commitment_age_norm, 0.0, 1.0)),
            float(np.clip(intent_alignment_last_k, 0.0, 1.0)),
            onehot[0],
            onehot[1],
            onehot[2],
            onehot[3],
        ]
    )

    # =================================================
    # P4.2 LOT E: opportunity vs opportunism features
    # (observability-only; no policy behavior change here)
    # =================================================
    (
        attack_opportunity_cost_near_vp_norm,
        capture_window_open,
        expected_vp_swing_if_advance,
        expected_trade_if_attack,
    ) = _lote_e_opportunity_features(
        state=state,
        active=active,
        rl_side=rl_side,
        focus_vp_id=focus_vp_id,
    )
    obs.extend(
        [
            float(np.clip(attack_opportunity_cost_near_vp_norm, 0.0, 1.0)),
            float(np.clip(capture_window_open, 0.0, 1.0)),
            float(np.clip(expected_vp_swing_if_advance, -1.0, 1.0)),
            float(np.clip(expected_trade_if_attack, -1.0, 1.0)),
        ]
    )

    # -------------------------
    # FINAL VECTOR
    # -------------------------
    return np.array(obs, dtype=np.float32)


# =================================================
# SYMBOLIC / EXPLAINABLE CONTEXT (NO CAMBIAR)
# =================================================
def explainable_context(state, rl_side=None, max_turns=None):

    units = state.units or []

    own_units = [u for u in units if u.alive and u.side == rl_side]
    enemy_units = [u for u in units if u.alive and u.side != rl_side]

    if len(own_units) > len(enemy_units):
        friendly_strength = "HIGH"
    elif len(own_units) < len(enemy_units):
        friendly_strength = "LOW"
    else:
        friendly_strength = "EVEN"

    if not enemy_units:
        enemy_pressure = "NONE"
    elif len(enemy_units) >= len(own_units):
        enemy_pressure = "HIGH"
    else:
        enemy_pressure = "LOW"

    if max_turns and max_turns > 0:
        progress = state.turn / max_turns
        if progress < 0.33:
            objective_distance = "FAR"
        elif progress < 0.66:
            objective_distance = "MEDIUM"
        else:
            objective_distance = "CLOSE"
    else:
        objective_distance = "UNKNOWN"

    return {
        "friendly_strength": friendly_strength,
        "enemy_pressure": enemy_pressure,
        "objective_distance": objective_distance,
    }
