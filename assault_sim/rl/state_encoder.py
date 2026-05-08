# assault_sim/rl/state_encoder.py

import numpy as np
from assault_model.map.hex_utils import hex_distance


def encode_state(state, rl_side=None, max_turns=None):
    """
    SAFE and minimal state encoder for Phase 01+.

    Adds global force-balance, time pressure,
    AND egocentric enemy direction awareness.
    """

    active = state.active_unit

    # -------------------------
    # Original features
    # -------------------------
    active_hp = active.hp if active is not None else 0
    n_units = len(state.units) if state.units is not None else 0
    vp = state.vp_tracker.total_points if state.vp_tracker else 0

    # -------------------------
    # Global force balance
    # -------------------------
    if rl_side is not None and state.units is not None:
        own_units = [
            u for u in state.units
            if u.alive and u.side == rl_side
        ]
        enemy_units = [
            u for u in state.units
            if u.alive and u.side != rl_side
        ]

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
    # Time pressure (SAFE)
    # -------------------------
    if max_turns and max_turns > 0:
        time_progress = state.turn / max_turns
    else:
        time_progress = 0.0

    # -------------------------
    # ✅ Egocentric direction to closest enemy (KEY FIX)
    # -------------------------
    dq = 0.0
    dr = 0.0

    if active is not None and enemy_units:
        closest_enemy = min(
            enemy_units,
            key=lambda e: hex_distance(active.position, e.position),
        )

        dq = closest_enemy.position.q - active.position.q
        dr = closest_enemy.position.r - active.position.r

        # normalize + clamp
        dq = np.clip(dq / 10.0, -1.0, 1.0)
        dr = np.clip(dr / 10.0, -1.0, 1.0)

    return np.array(
        [
            state.turn,        # current turn
            active_hp,         # HP of active unit
            n_units,           # total units
            vp,                # victory points

            unit_balance,      # [-1, +1]
            hp_balance,        # [-1, +1]
            time_progress,     # [0, 1]

            dq,                # egocentric enemy direction (q)
            dr,                # egocentric enemy direction (r)
        ],
        dtype=np.float32,
    )