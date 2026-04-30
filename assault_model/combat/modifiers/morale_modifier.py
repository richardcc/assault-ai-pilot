from assault_model.combat.modifier import DiceModifier
from assault_model.combat.dice_color import DiceColor


class MoraleModifier(DiceModifier):
    def __init__(self, lose_weakest: bool = False):
        self.lose_weakest = lose_weakest

    def modify_attack(self, dice: list[DiceColor]) -> list[DiceColor]:
        if self.lose_weakest and dice:
            return sorted(dice)[1:]
        return dice

    def modify_defense(self, dice: list[DiceColor]) -> list[DiceColor]:
        if self.lose_weakest and dice:
            return sorted(dice)[1:]
        return dice