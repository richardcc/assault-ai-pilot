import random

from assault.core.unit import Unit, UnitType, Experience
from assault.core.actions.assault_action import AssaultAction, AssaultOutcome


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


def test_assault_is_reproducible():
    rng1 = random.Random(42)
    rng2 = random.Random(42)

    a1, d1 = create_test_units()
    a2, d2 = create_test_units()

    action1 = AssaultAction(a1, d1, rng=rng1)
    action2 = AssaultAction(a2, d2, rng=rng2)

    report1 = action1.resolve()
    report2 = action2.resolve()

    assert report1.outcome == report2.outcome
    assert report1.rounds == report2.rounds


def test_assault_stops_when_unit_is_eliminated():
    rng = random.Random(7)

    attacker, defender = create_test_units()
    attacker.attack_dice = (3, 0, 0, 0)

    action = AssaultAction(attacker, defender, rng=rng, max_rounds=5)
    report = action.resolve()

    assert not defender.is_alive()
    assert report.outcome in (
        AssaultOutcome.DEFENDER_ELIMINATED,
        AssaultOutcome.BOTH_ELIMINATED,
    )


def test_assault_respects_max_rounds():
    rng = random.Random(99)

    attacker, defender = create_test_units()

    action = AssaultAction(attacker, defender, rng=rng, max_rounds=1)
    report = action.resolve()

    assert len(report.rounds) == 1


def test_assault_stalemate():
    rng = random.Random(123)

    attacker, defender = create_test_units()
    attacker.attack_dice = (0, 0, 0, 1)
    defender.attack_dice = (0, 0, 0, 1)

    action = AssaultAction(attacker, defender, rng=rng, max_rounds=2)
    report = action.resolve()

    assert report.outcome == AssaultOutcome.STALEMATE
