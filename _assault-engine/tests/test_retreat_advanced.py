from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.terrain import CLEAR, WATER
from assault.core.unit import Unit, UnitType, Experience
from assault.core.actions.assault_executor import AssaultExecutor


def test_retreat_prefers_opposite_direction():
    state = GameState()

    # Line: A - D - R
    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, CLEAR))
    state.add_hex(Hex(2, 0, CLEAR))

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5,
        5,
        (2, 0, 0, 0),
        1,
        (0, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5,
        5,
        (0, 0, 0, 0),
        1,
        (1, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    executor = AssaultExecutor(state, "A", "D")
    retreat_hex = executor.find_retreat_hex(defender)

    assert (retreat_hex.q, retreat_hex.r) == (2, 0)


def test_unit_eliminated_if_no_valid_retreat():
    state = GameState()

    # Defender has no valid retreat: WATER is not passable (movement_cost=99)
    state.add_hex(Hex(0, 0, WATER))
    state.add_hex(Hex(1, 0, CLEAR))

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5,
        5,
        (2, 0, 0, 0),
        1,
        (0, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5,
        5,
        (0, 0, 0, 0),
        1,
        (1, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    executor = AssaultExecutor(state, "A", "D")
    retreat_hex = executor.find_retreat_hex(defender)

    assert retreat_hex is None
