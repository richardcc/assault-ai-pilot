"""
Close Combat (Assault) resolution module.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Tuple
import random

from assault.core.unit import Unit, Experience, UnitStatus


class DiceColor(Enum):
    RED = auto()
    YELLOW = auto()
    GREEN = auto()
    BLUE = auto()


class CombatSymbol(Enum):
    CRITICAL = auto()
    HIT = auto()
    SUPPRESSION = auto()
    BLANK = auto()


DICE_FACES: Dict[DiceColor, List[CombatSymbol]] = {
    DiceColor.RED: [CombatSymbol.CRITICAL, CombatSymbol.HIT, CombatSymbol.HIT,
                    CombatSymbol.SUPPRESSION, CombatSymbol.BLANK, CombatSymbol.BLANK],
    DiceColor.YELLOW: [CombatSymbol.HIT, CombatSymbol.HIT,
                       CombatSymbol.SUPPRESSION, CombatSymbol.SUPPRESSION,
                       CombatSymbol.BLANK, CombatSymbol.BLANK],
    DiceColor.GREEN: [CombatSymbol.HIT, CombatSymbol.SUPPRESSION,
                      CombatSymbol.SUPPRESSION, CombatSymbol.BLANK,
                      CombatSymbol.BLANK, CombatSymbol.BLANK],
    DiceColor.BLUE: [CombatSymbol.SUPPRESSION, CombatSymbol.BLANK,
                     CombatSymbol.BLANK, CombatSymbol.BLANK,
                     CombatSymbol.BLANK, CombatSymbol.BLANK],
}


def roll_die(color: DiceColor, rng: random.Random) -> CombatSymbol:
    return rng.choice(DICE_FACES[color])


@dataclass
class CombatResult:
    attacker_hits: int
    defender_hits: int
    attacker_remaining_strength: int
    defender_remaining_strength: int


class CloseCombatResolver:

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def modify_attack_dice_by_status(self, unit: Unit) -> List[DiceColor]:
        red, yellow, green, blue = unit.attack_dice
        dice: List[DiceColor] = (
            [DiceColor.RED] * red +
            [DiceColor.YELLOW] * yellow +
            [DiceColor.GREEN] * green +
            [DiceColor.BLUE] * blue
        )

        if unit.experience == Experience.VETERAN:
            dice.append(DiceColor.BLUE)
        elif unit.experience == Experience.ELITE:
            dice.append(DiceColor.GREEN)

        if unit.is_suppressed() and dice:
            dice.pop()
        if unit.is_half_strength() and dice:
            dice.pop()

        return dice

    def roll_attack(self, unit: Unit) -> List[CombatSymbol]:
        dice = self.modify_attack_dice_by_status(unit)
        return [roll_die(color, self.rng) for color in dice]

    def cancel_results(self, a: List[CombatSymbol], d: List[CombatSymbol]):
        for symbol in (CombatSymbol.HIT, CombatSymbol.SUPPRESSION):
            while symbol in a and symbol in d:
                a.remove(symbol)
                d.remove(symbol)
        return a, d

    def resolve(self, attacker: Unit, defender: Unit) -> CombatResult:
        a_roll = self.roll_attack(attacker)
        d_roll = self.roll_attack(defender)

        a_final, d_final = self.cancel_results(a_roll, d_roll)

        a_hits = sum(1 for s in a_final if s in (CombatSymbol.HIT, CombatSymbol.CRITICAL))
        d_hits = sum(1 for s in d_final if s in (CombatSymbol.HIT, CombatSymbol.CRITICAL))

        attacker.apply_damage(d_hits)
        defender.apply_damage(a_hits)

        return CombatResult(
            attacker_hits=a_hits,
            defender_hits=d_hits,
            attacker_remaining_strength=attacker.strength,
            defender_remaining_strength=defender.strength,
        )
