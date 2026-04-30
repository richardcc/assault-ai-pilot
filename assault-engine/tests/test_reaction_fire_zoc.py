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
    """

    def resolve(self, attacker):
        class FakeReport:
            hits = 1
            suppressions = 1
        return FakeReport()


# ---------------------------------------------------------------------------
# Test setups
# ---------------------------------------------------------------------------

def setup_units_outside_zoc():
    """
    Setup where the moving unit is NOT in any enemy ZOC.
    Reaction fire must NOT occur.
    """

    state = GameState()

    # Linear hexes
    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, CLEAR))
    state.add_hex(Hex(2, 0, CLEAR))
    state.add_hex(Hex(3, 0, CLEAR))

    reacting_unit = Unit(
        unit_id="R",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(2, 0, 0, 0),
        defense=1,
        position=(0, 0),
    )

    moving_unit = Unit(
        unit_id="M",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(0, 0, 0, 0),
        defense=1,
        position=(3, 0),  # outside ZOC
    )

    state.add_unit(reacting_unit)
    state.add_unit(moving_unit)

    return state, moving_unit


def setup_units_inside_zoc():
    """
    Setup where the moving unit IS inside enemy ZOC.
    Reaction fire MUST occur.
    """

    state = GameState()

    state.add_hex(Hex(0, 0, CLEAR))
    state.add_hex(Hex(1, 0, CLEAR))
    state.add_hex(Hex(2, 0, CLEAR))

    reacting_unit = Unit(
        unit_id="R",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(2, 0, 0, 0),
        defense=1,
        position=(1, 0),
    )

    moving_unit = Unit(
        unit_id="M",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(0, 0, 0, 0),
        defense=1,
        position=(2, 0),  # adjacent → inside ZOC
    )

    state.add_unit(reacting_unit)
    state.add_unit(moving_unit)

    return state, moving_unit


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_reaction_fire_outside_enemy_zoc():
    """
    Reaction Fire must NOT trigger if the unit is outside
    all enemy Zones of Control.
    """
    state, moving_unit = setup_units_outside_zoc()

    visibility = VisibilityService()
    resolver = FakeReactionResolver()

    trigger = ReactionFireTrigger(state, visibility, resolver)
    trigger.trigger_reaction_fire(moving_unit)

    # No damage, no suppression
    assert moving_unit.strength == moving_unit.max_strength
    assert UnitStatus.SUPPRESSED not in moving_unit.statuses


def test_reaction_fire_inside_enemy_zoc():
    """
    Reaction Fire MUST trigger when the unit is inside
    an enemy Zone of Control.
    """
    state, moving_unit = setup_units_inside_zoc()

    visibility = VisibilityService()
    resolver = FakeReactionResolver()

    trigger = ReactionFireTrigger(state, visibility, resolver)
    trigger.trigger_reaction_fire(moving_unit)

    # One reacting unit → exactly one hit
    assert moving_unit.strength == moving_unit.max_strength - 1
    assert UnitStatus.SUPPRESSED in moving_unit.statuses