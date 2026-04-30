from typing import List
from assault_model.combat.battle_die import BattleDie
from assault_model.combat.dice_face import DiceFace


class DicePool:
    def __init__(self, dice: List[BattleDie]):
        self.dice = dice

    def roll(self) -> List[DiceFace]:
        return [d.roll() for d in self.dice]