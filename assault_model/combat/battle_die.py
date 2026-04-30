import random
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace


class BattleDie:
    def __init__(self, color: DiceColor):
        self.color = color

    def roll(self) -> DiceFace:
        return random.choice(list(DiceFace))