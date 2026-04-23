from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.terrain import CLEAR, WATER
from assault.core.unit import Unit, UnitType, Experience
from assault.core.actions.movement_action import MovementAction
from assault.core.actions.movement_executor import MovementExecutor


def test_unit_can_move_to_adjacent_hex():
    state = GameState()

    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, CLEAR))

    unit = Unit(
        "U",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5,
        5,
        (1, 0, 0, 0),
        1,
        (0, 0),
    )
    state.add_unit(unit)

    action = MovementAction(unit, (1, 0))
    executor = MovementExecutor(state)
    executor.execute(action)

    assert unit.position == (1, 0)


def test_unit_cannot_move_into_water():
    state = GameState()

    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, WATER))

    unit = Unit(
        "U",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5,
        5,
        (1, 0, 0, 0),
        1,
        (0, 0),
    )
    state.add_unit(unit)

    action = MovementAction(unit, (1, 0))
    assert not action.can_execute(state)