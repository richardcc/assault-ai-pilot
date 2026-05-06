# assault_sim/rl/state_encoder.py

import numpy as np


def encode_state(state):
    """
    SAFE and minimal state encoder for Phase 01.

    Uses only attributes that are guaranteed to exist
    in UnitInstance and GameState.
    """

    active = state.active_unit

    active_hp = active.hp if active is not None else 0
    n_units = len(state.units) if state.units is not None else 0
    vp = state.vp_tracker.total_points if state.vp_tracker else 0

    return np.array(
        [
            state.turn,     # current turn number
            active_hp,      # HP of active unit
            n_units,        # total number of units
            vp,             # victory points
        ],
        dtype=np.float32,
    )