from assault_model.combat.modifier import DiceModifier
from assault_model.combat.dice_color import DiceColor


class TerrainModifier(DiceModifier):
    def __init__(self, defense_bonus: DiceColor | None = None):
        self.defense_bonus = defense_bonus

    def modify_attack(self, dice: list[DiceColor]) -> list[DiceColor]:
        return dice

    def modify_defense(self, dice: list[DiceColor]) -> list[DiceColor]:
        if self.defense_bonus:
            return dice + [self.defense_bonus]
        return dice