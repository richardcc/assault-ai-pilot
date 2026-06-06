import numpy as np

from assault_sim.rl.features.tactical_features import compute_tactical_features
from assault_model.map.hex_utils import safe_hex_distance

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
def encode_state(state, unit=None, rl_side=None, max_turns=None):

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
