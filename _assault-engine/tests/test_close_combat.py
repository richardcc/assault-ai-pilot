import random

from assault.core.unit import Unit, UnitType, Experience
from assault.core.combat.close_combat import CloseCombatResolver


def create_test_units():
    attacker = Unit(
        unit_id="A",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(1, 1, 1, 0),
        defense=1,
        position=(0, 0),
    )

    defender = Unit(
        unit_id="D",
        unit_type=UnitType.INFANTRY,
        experience=Experience.REGULAR,
        strength=5,
        max_strength=5,
        attack_dice=(1, 1, 1, 0),
        defense=1,
        position=(1, 0),
    )

    return attacker, defender


def test_close_combat_is_reproducible():
    rng1 = random.Random(42)
    rng2 = random.Random(42)

    attacker1, defender1 = create_test_units()
    attacker2, defender2 = create_test_units()

    resolver1 = CloseCombatResolver(rng1)
    resolver2 = CloseCombatResolver(rng2)

    result1 = resolver1.resolve(attacker1, defender1)
    result2 = resolver2.resolve(attacker2, defender2)

    assert result1 == result2



def test_strength_never_goes_negative():
    rng = random.Random(123)

    attacker, defender = create_test_units()
    resolver = CloseCombatResolver(rng)

    result = resolver.resolve(attacker, defender)

    assert result.attacker_remaining_strength >= 0
    assert result.defender_remaining_strength >= 0


def test_damage_matches_hits():
    rng = random.Random(10)

    attacker, defender = create_test_units()
    resolver = CloseCombatResolver(rng)

    initial_attacker_strength = attacker.strength
    initial_defender_strength = defender.strength

    result = resolver.resolve(attacker, defender)

    assert initial_attacker_strength - attacker.strength == result.defender_hits
    assert initial_defender_strength - defender.strength == result.attacker_hits
