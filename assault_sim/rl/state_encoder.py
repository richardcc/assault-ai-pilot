import numpy as np
from assault_model.map.hex_utils import hex_distance


# =================================================
# NUMERIC STATE (USED BY RL)
# =================================================
def encode_state(state, unit=None, rl_side=None, max_turns=None):

    active = unit  # ✅ NEW (antes active_unit)

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

    if active is not None and enemy_units:
        closest_enemy = min(
            enemy_units,
            key=lambda e: hex_distance(active.position, e.position),
        )

        dq = np.clip((closest_enemy.position.q - active.position.q) / 10.0, -1.0, 1.0)
        dr = np.clip((closest_enemy.position.r - active.position.r) / 10.0, -1.0, 1.0)

    # -------------------------
    # DISTANCE TO VP
    # -------------------------
    vp_dist = 0.0

    if active is not None and state.vp_tracker:
        vp_points = getattr(state.vp_tracker.conditions, "points", [])

        if vp_points:
            target_vp = min(
                vp_points,
                key=lambda p: hex_distance(active.position, p.hex_coords)
            )

            dist = hex_distance(active.position, target_vp.hex_coords)
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
        d = hex_distance(active.position, closest_enemy.position)
        enemy_dist = np.clip(d / 10.0, 0.0, 1.0)

    # -------------------------
    # FINAL VECTOR
    # -------------------------
    return np.array([
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
    ], dtype=np.float32)


# =================================================
# SYMBOLIC / EXPLAINABLE CONTEXT
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