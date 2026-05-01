from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.terrain import CLEAR
from assault.core.unit import Unit, UnitType, Experience, UnitStatus
from assault.core.visibility import VisibilityService
from assault.core.reaction.reaction_fire import ReactionFireTrigger
from assault.core.combat.ranged_fire import RangedFireResolver


# ---------------------------------------------------------------------------
# Fake resolver for deterministic reaction fire
# ---------------------------------------------------------------------------

class FakeReactionResolver(RangedFireResolver):
    """
    Fake resolver that always causes 1 hit and 1 suppression.

    This removes all randomness from tests and allows us
    to validate reaction fire logic deterministically.
    """

    def resolve(self, attacker):
        class FakeReport:
            hits = 1
            suppressions = 1
        return FakeReport()


# ---------------------------------------------------------------------------
# Test setup: ONE triggering unit, TWO reacting units
# ---------------------------------------------------------------------------

def setup_three_units():
    """
    Creates a minimal map with:
    - one triggering unit (M)
    - two reacting units (R1, R2)

    The map layout is:
        R1 --- M --- R2
    """

    state = GameState()

    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, CLEAR))
    state.add_hex(Hex(2, 0, CLEAR))

    moving_unit = Unit(
        unit_id="M",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(0, 0, 0, 0),
        defense=1,
        position=(1, 0),
    )

    reacting_unit_1 = Unit(
        unit_id="R1",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(2, 0, 0, 0),
        defense=1,
        position=(0, 0),
    )

    reacting_unit_2 = Unit(
        unit_id="R2",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(2, 0, 0, 0),
        defense=1,
        position=(2, 0),
    )

    state.add_unit(moving_unit)
    state.add_unit(reacting_unit_1)
    state.add_unit(reacting_unit_2)

    return state, moving_unit, reacting_unit_1, reacting_unit_2


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_reaction_fire_triggers_damage_and_suppression():
    """
    When a unit triggers reaction fire, all eligible enemy units react.

    With two reacting units and a fake resolver that always produces
    1 hit and 1 suppression, the triggering unit must:
    - lose exactly 2 strength
    - receive the SUPPRESSED status
    """
    state, moving_unit, r1, r2 = setup_three_units()

    visibility = VisibilityService()
    resolver = FakeReactionResolver()

    trigger = ReactionFireTrigger(state, visibility, resolver)
    trigger.trigger_reaction_fire(moving_unit)

    assert moving_unit.strength == moving_unit.max_strength - 2
    assert UnitStatus.SUPPRESSED in moving_unit.statuses


def test_unit_does_not_react_to_itself():
    """
    A unit must never shoot itself via reaction fire.

    When R1 triggers reaction fire:
    - R1 must not act as a reactor
    - Damage to R1 comes ONLY from other units (M and R2)
    """
    state, moving_unit, r1, r2 = setup_three_units()

    visibility = VisibilityService()
    resolver = FakeReactionResolver()

    trigger = ReactionFireTrigger(state, visibility, resolver)
    trigger.trigger_reaction_fire(r1)

    # R1 takes 2 hits: one from M and one from R2.
    # Crucially, none of the damage comes from R1 itself.
    assert r1.strength == r1.max_strength - 2


def test_dead_units_do_not_react():
    """
    Dead units must never participate in reaction fire.
    """
    state, moving_unit, r1, r2 = setup_three_units()

    # Kill one reacting unit
    r1.apply_damage(r1.max_strength)
    assert not r1.is_alive()

    visibility = VisibilityService()
    resolver = FakeReactionResolver()

    trigger = ReactionFireTrigger(state, visibility, resolver)
    trigger.trigger_reaction_fire(moving_unit)

    # Only R2 reacts
    assert moving_unit.strength == moving_unit.max_strength - 1
    assert UnitStatus.SUPPRESSED in moving_unit.statuses
