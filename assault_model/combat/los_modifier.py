# assault_model/combat/modifiers/los_modifier.py
from assault_model.combat.modifier import DiceModifier
from assault_model.combat.line_of_sight import LineOfSight
from assault_model.combat.dice_color import DiceColor


class LineOfSightModifier(DiceModifier):
    def __init__(self, los: LineOfSight):
        self.los = los

    def modify_attack(self, dice: list[DiceColor]) -> list[DiceColor]:
        if self.los == LineOfSight.BLOCKED:
            return []
        if self.los == LineOfSight.PARTIAL and dice:
            return dice[:-1]
        return dice

    def modify_defense(self, dice: list[DiceColor]) -> list[DiceColor]:
        return dice