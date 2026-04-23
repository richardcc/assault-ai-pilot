"""
Direct ranged fire mechanics.
"""

from dataclasses import dataclass
from enum import Enum, auto
import random

from assault.core.unit import Unit
from assault.core.combat.close_combat import (
    DiceColor,
    CombatSymbol,
    roll_die,
)


class RangedFireResult(Enum):
    HIT = auto()
    SUPPRESSION = auto()
    NO_EFFECT = auto()


@dataclass
class RangedFireReport:
    """
    Result of a ranged attack.
    """
    hits: int
    suppressions: int


class RangedFireResolver:
    """
    Resolves direct ranged fire mechanics.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def resolve(self, attacker: Unit) -> RangedFireReport:
        """
        Resolves a single ranged fire attack.
        """
        red, yellow, green, blue = attacker.attack_dice

        hits = 0
        suppressions = 0

        dice = (
            [DiceColor.RED] * red +
            [DiceColor.YELLOW] * yellow +
            [DiceColor.GREEN] * green +
            [DiceColor.BLUE] * blue
        )

        for die in dice:
            symbol = roll_die(die, self.rng)
            if symbol == CombatSymbol.CRITICAL or symbol == CombatSymbol.HIT:
                hits += 1
            elif symbol == CombatSymbol.SUPPRESSION:
                suppressions += 1

        return RangedFireReport(
            hits=hits,
            suppressions=suppressions,
        )