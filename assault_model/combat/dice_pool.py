import os
from typing import List, Sequence, Union

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.battle_die import BattleDie, DiceResult

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class DicePool:
    """
    DicePool

    Represents a collection of battle dice rolled together as part of
    a combat step. Accepts either DiceColor enums or BattleDie instances.
    """

    def __init__(self, dice: Sequence[Union[DiceColor, BattleDie]]):
        self.dice: List[BattleDie] = [
            d if isinstance(d, BattleDie) else BattleDie(d) for d in dice
        ]

    def roll(self) -> List[DiceResult]:
        """Roll all dice in the pool and return their raw results."""
        return [die.roll() for die in self.dice]


class AttackDicePool(DicePool):
    """Pool of attack dice."""

    def __init__(self, dice: Sequence[Union[DiceColor, BattleDie]]):
        super().__init__(dice)
        _trace(
            "ATTACK_DICE_POOL_INIT",
            dice_count=len(self.dice),
            dice=[d.color.name for d in self.dice],
        )

    def roll(self) -> List[DiceResult]:
        results = super().roll()
        for r in results:
            _trace(
                "ATTACK_DIE_ROLL",
                color=r.color.name,
                faces=[f.name for f in r.faces],
            )
        return results


class DefenseDicePool(DicePool):
    """Pool of defense dice."""

    def __init__(self, dice: Sequence[Union[DiceColor, BattleDie]]):
        super().__init__(dice)
        _trace(
            "DEFENSE_DICE_POOL_INIT",
            dice_count=len(self.dice),
            dice=[d.color.name for d in self.dice],
        )

    def roll(self) -> List[DiceResult]:
        results = super().roll()
        for r in results:
            _trace(
                "DEFENSE_DIE_ROLL",
                color=r.color.name,
                faces=[f.name for f in r.faces],
            )
        return results
