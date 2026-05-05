# assault_model/combat/defense_dice_pool.py

import random
import os
from typing import List, Tuple

from assault_model.combat.dice_face import DiceFace
from assault_model.combat.dice_color import DiceColor


# DEBUG TRACE (configurable por entorno)
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class DefenseDicePool:
    """
    Pool of defense dice.

    The pool contains DiceColor values directly.
    Rolling preserves (color, face).
    """

    def __init__(self, dice: List[DiceColor]):
        self.dice = dice

        _trace(
            "DEFENSE_DICE_POOL_INIT",
            dice_count=len(dice),
            dice=[d.name for d in dice],  # ✅ CORRECTO
        )

    def roll(self) -> List[Tuple[DiceColor, DiceFace]]:
        """
        Roll all defense dice and return (color, face) tuples.
        """
        results = []

        for color in self.dice:
            face = random.choice(list(DiceFace))
            results.append((color, face))

            _trace(
                "DEFENSE_DIE_ROLL",
                color=color.name,
                face=face.name,
            )

        return results