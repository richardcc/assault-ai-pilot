from assault_model.combat.modifier import DiceModifier
from assault_model.combat.dice_color import DiceColor


class TerrainModifier(DiceModifier):
    def __init__(self, defense_bonus: list[DiceColor] | None = None):
        self.defense_bonus = defense_bonus or []

    @staticmethod
    def from_hex(hex_):
        bonuses = []

        state = getattr(hex_, "state", None)

        if state:
            if getattr(state, "building", False):
                bonuses += [DiceColor.GREEN, DiceColor.BLUE]

            if getattr(state, "woods", False):
                bonuses += [DiceColor.BLUE]

        return TerrainModifier(bonuses)

    def modify_attack(self, dice: list[DiceColor]) -> list[DiceColor]:
        return dice

    def modify_defense(self, dice: list[DiceColor]) -> list[DiceColor]:
        return dice + self.defense_bonus
