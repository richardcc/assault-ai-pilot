import random

from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.terrain import CLEAR
from assault.core.unit import Unit, UnitType, Experience
from assault.core.actions.assault_executor import AssaultExecutor
from assault.core.actions.assault_action import AssaultOutcome


def setup_simple_map():
    state = GameState()

    # Create a small 3-hex line: (0,0)-(1,0)-(2,0)
    for q in range(3):
        state.add_hex(Hex(q=q, r=0, terrain=CLEAR))

    attacker = Unit(
        unit_id="A",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(2, 0, 0, 0),
        defense=1,
        position=(0, 0),
    )

    defender = Unit(
        unit_id="D",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(0, 0, 0, 1),
        defense=1,
        position=(1, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker, defender


def test_defender_retreats_and_attacker_advances():
    state, attacker, defender = setup_simple_map()

    executor = AssaultExecutor(state, attacker.unit_id, defender.unit_id)
    report = executor.execute()

    assert report.outcome in (
        AssaultOutcome.DEFENDER_RETREATS,
        AssaultOutcome.DEFENDER_ELIMINATED,
    )

    # Attacker should not remain in original hex if advancing
    if report.attacker_advances:
        assert attacker.position != (0, 0)


def test_defender_eliminated_if_no_retreat_hex():
    state = GameState()

    # Create isolated hexes with no retreat options
    state.add_hex(Hex(q=0, r=0, terrain=CLEAR))
    state.add_hex(Hex(q=1, r=0, terrain=CLEAR))

    attacker = Unit(
        unit_id="A",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(2, 0, 0, 0),
        defense=1,
        position=(0, 0),
    )

    defender = Unit(
        unit_id="D",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=2,
        max_strength=5,
        attack_dice=(0, 0, 0, 1),
        defense=1,
        position=(1, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    executor = AssaultExecutor(state, "A", "D")
    report = executor.execute()

    assert "D" not in state.units


def test_stalemate_does_not_move_units():
    state, attacker, defender = setup_simple_map()

    attacker.attack_dice = (0, 0, 0, 1)

    executor = AssaultExecutor(state, attacker.unit_id, defender.unit_id)
    report = executor.execute()

    assert report.outcome == AssaultOutcome.STALEMATE
    assert attacker.position == (0, 0)
    assert defender.position == (1, 0)
