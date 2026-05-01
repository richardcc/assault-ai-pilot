import random

from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.terrain import CLEAR
from assault.core.unit import Unit, UnitType, Experience, UnitStatus
from assault.core.visibility import VisibilityService
from assault.core.combat.ranged_fire import RangedFireResolver
from assault.core.actions.ranged_fire_action import RangedFireAction
from assault.core.actions.ranged_fire_executor import RangedFireExecutor


# ---------------------------------------------------------------------------
# Test utilities
# ---------------------------------------------------------------------------

def setup_map_and_units():
    state = GameState()
    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, CLEAR))

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
        attack_dice=(0, 0, 0, 0),
        defense=1,
        position=(1, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)
    return state, attacker, defender


# ---------------------------------------------------------------------------
# Fake resolver for deterministic suppression testing
# ---------------------------------------------------------------------------

class FakeSuppressionResolver(RangedFireResolver):
    """
    Resolver that deterministically produces suppression.
    Used only for executor tests (no RNG).
    """

    def resolve(self, attacker):
        class FakeReport:
            hits = 0
            suppressions = 1

        return FakeReport()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ranged_fire_within_range_and_visible():
    state, attacker, defender = setup_map_and_units()

    action = RangedFireAction(attacker, defender, max_range=2)
    visibility = VisibilityService()

    assert action.can_execute(state, visibility)


def test_ranged_fire_out_of_range():
    state, attacker, defender = setup_map_and_units()
    defender.position = (5, 5)

    action = RangedFireAction(attacker, defender, max_range=2)
    visibility = VisibilityService()

    assert not action.can_execute(state, visibility)


def test_ranged_fire_applies_damage():
    rng = random.Random(1)
    state, attacker, defender = setup_map_and_units()

    resolver = RangedFireResolver(rng)
    executor = RangedFireExecutor(state, resolver)
    action = RangedFireAction(attacker, defender, max_range=2)

    executor.execute(action)

    assert defender.strength < defender.max_strength


def test_ranged_fire_applies_suppression():
    state, attacker, defender = setup_map_and_units()

    resolver = FakeSuppressionResolver()
    executor = RangedFireExecutor(state, resolver)
    action = RangedFireAction(attacker, defender, max_range=2)

    executor.execute(action)

    assert UnitStatus.SUPPRESSED in defender.statuses
