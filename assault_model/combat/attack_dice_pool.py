# assault_model/combat/attack_dice_pool.py

import random
import os
from typing import List

from assault_model.combat.attack_die import AttackDie
from assault_model.combat.dice_face import DiceFace


# DEBUG TRACE (configurable por entorno)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class AttackDicePool:
    """
    Pool of attack dice.
    """

    def __init__(self, dice: List[AttackDie]):
        self.dice = dice

        _trace(
            "ATTACK_DICE_POOL_INIT",
            dice_count=len(dice),
            dice=dice,
        )

    def roll(self) -> List[DiceFace]:
        """
        Roll all attack dice and return their faces.
        """
        results = [random.choice(list(DiceFace)) for _ in self.dice]

        _trace(
            "ATTACK_DICE_POOL_ROLL",
            dice_count=len(self.dice),
            results=[r.name for r in results],
        )

        return results
