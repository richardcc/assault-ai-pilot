# assault/core/combat/dice.py

from enum import Enum, auto
from typing import Dict, List
import random


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
    CANCEL = auto()


DICE_FACES: Dict[DiceColor, List[CombatSymbol]] = {
    DiceColor.RED: [
        CombatSymbol.CRITICAL,
        CombatSymbol.HIT,
        CombatSymbol.HIT,
        CombatSymbol.SUPPRESSION,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
    ],
    DiceColor.YELLOW: [
        CombatSymbol.HIT,
        CombatSymbol.HIT,
        CombatSymbol.SUPPRESSION,
        CombatSymbol.SUPPRESSION,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
    ],
    DiceColor.GREEN: [
        CombatSymbol.HIT,
        CombatSymbol.SUPPRESSION,
        CombatSymbol.SUPPRESSION,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
    ],
    DiceColor.BLUE: [
        CombatSymbol.SUPPRESSION,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
        CombatSymbol.BLANK,
    ],
}


def roll_die(color: DiceColor, rng: random.Random) -> CombatSymbol:
    return rng.choice(DICE_FACES[color])