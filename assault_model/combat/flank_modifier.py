# assault_model/combat/modifiers/flank_modifier.py
from assault_model.combat.modifier import DiceModifier
from assault_model.combat.flank import Flank
from assault_model.combat.dice_color import DiceColor


class FlankModifier(DiceModifier):
    def __init__(self, flank: Flank):
        self.flank = flank

    def modify_attack(self, dice: list[DiceColor]) -> list[DiceColor]:
        if self.flank == Flank.REAR:
            return dice + [DiceColor.BLUE]
        if self.flank == Flank.SIDE:
            return dice
        return dice

    def modify_defense(self, dice: list[DiceColor]) -> list[DiceColor]:
        if self.flank == Flank.REAR and dice:
            return dice[:-1]
        return dice