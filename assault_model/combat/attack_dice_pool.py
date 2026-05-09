# assault_model/combat/attack_dice_pool.py
#
# Attack dice pool.
#
# RESPONSIBILITY:
# - Hold a list of attack dice colors
# - Roll all dice using BattleDie
# - Return DiceResult objects ONLY
#
# IMPORTANT:
# - NO legacy tuple support
# - NO random logic here
# - BattleDie is the single authority for dice rolling

import os
from typing import List

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.battle_die import BattleDie, DiceResult


# DEBUG TRACE (configurable via environment)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class AttackDicePool:
    """
    Pool of attack dice.

    The pool stores DiceColor values and rolls them using BattleDie.
    The result of a roll is ALWAYS a list of DiceResult objects.
    """

    def __init__(self, dice: List[DiceColor]):
        self.dice: List[BattleDie] = [
            BattleDie(color) for color in dice
        ]

        _trace(
            "ATTACK_DICE_POOL_INIT",
            dice_count=len(self.dice),
            dice=[d.color.name for d in self.dice],
        )

    def roll(self) -> List[DiceResult]:
        """
        Roll all attack dice.

        Returns:
            List[DiceResult]
        """
        results: List[DiceResult] = []

        for die in self.dice:
            result = die.roll()
            results.append(result)

            _trace(
                "ATTACK_DIE_ROLL",
                color=result.color.name,
                faces=[f.name for f in result.faces],
            )

        return results