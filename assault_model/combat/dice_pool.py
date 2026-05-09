from typing import List

from assault_model.combat.battle_die import BattleDie, DiceResult


class DicePool:
    """
    DicePool

    Represents a collection of battle dice rolled together as part of
    a combat step (attack roll or defense roll).

    Responsibilities:
    - Hold a list of BattleDie instances
    - Roll all dice in the pool
    - Return the raw DiceResult objects

    DicePool does NOT:
    - Interpret symbols
    - Compare dice
    - Apply combat rules
    - Calculate damage or effects
    """

    def __init__(self, dice: List[BattleDie]):
        self.dice = dice

    def roll(self) -> List[DiceResult]:
        """
        Roll all dice in the pool and return their raw results.
        """
        return [die.roll() for die in self.dice]