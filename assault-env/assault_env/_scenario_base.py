# =============================================================
# Scenario builders for assault-env
#
# Each function returns:
#   - GameState
#   - list of friendly unit IDs (italy)
#   - list of enemy unit IDs
#
# Terrain is explicit and consistent across P1–P4.
# =============================================================

from assault.core.game_state import GameState, Hex, Unit
from assault.core.terrain import Terrain, TerrainType
from assault.core.unit import UnitType, Experience


# -------------------------------------------------------------
# Common map builder (shared by all scenarios)
# -------------------------------------------------------------

def _build_base_map(state: GameState):
    """Create the standard 8x10 CLEAR terrain map."""
    for q in range(8):
        for r in range(10):
            state.add_hex(
                Hex(q, r, Terrain(TerrainType.CLEAR, 1, 0))
            )


# -------------------------------------------------------------
# P1 – Single unit duel (1 vs 1)
# -------------------------------------------------------------

def simple_duel_level7_P1_from_json():
    state = GameState()
    _build_base_map(state)

    italy = Unit(
        "IT_1",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (1, 3),
    )

    enemy = Unit(
        "EN_1",
        UnitType.INFANTRY,
        Experience.REGULAR,
        6, 6,
        (1, 0, 0, 0),
        1,
        (6, 5),
    )

    state.add_unit(italy)
    state.add_unit(enemy)

    return state, ["IT_1"], ["EN_1"]


# -------------------------------------------------------------
# P2 – Asymmetric pressure (2 vs 1, no global info)
# -------------------------------------------------------------

def simple_duel_level7_P2_from_json():
    state = GameState()
    _build_base_map(state)

    italy_1 = Unit(
        "IT_1",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (1, 2),
    )

    italy_2 = Unit(
        "IT_2",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (1, 4),
    )

    enemy = Unit(
        "EN_1",
        UnitType.INFANTRY,
        Experience.REGULAR,
        6, 6,
        (1, 0, 0, 0),
        1,
        (6, 5),
    )

    state.add_unit(italy_1)
    state.add_unit(italy_2)
    state.add_unit(enemy)

    return state, ["IT_1", "IT_2"], ["EN_1"]


# -------------------------------------------------------------
# P3 – Asymmetric pressure with global force awareness (2 vs 1)
# -------------------------------------------------------------

def simple_duel_level7_P3_from_json():
    """
    Structurally identical to P2.
    Difference is entirely in the observation space (env.py).
    """
    return simple_duel_level7_P2_from_json()


# -------------------------------------------------------------
# P4 – Symmetric engagement (2 vs 2)
# -------------------------------------------------------------

def simple_duel_level7_P4_2v2_from_json():
    state = GameState()
    _build_base_map(state)

    # ---- Italy (2 units) ----
    italy_1 = Unit(
        "IT_1",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (1, 2),
    )

    italy_2 = Unit(
        "IT_2",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (1, 4),
    )

    # ---- Enemy (2 units) ----
    enemy_1 = Unit(
        "EN_1",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (6, 4),
    )

    enemy_2 = Unit(
        "EN_2",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (1, 0, 0, 0),
        1,
        (6, 6),
    )

    state.add_unit(italy_1)
    state.add_unit(italy_2)
    state.add_unit(enemy_1)
    state.add_unit(enemy_2)

    return state, ["IT_1", "IT_2"], ["EN_1", "EN_2"]