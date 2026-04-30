# assault_model/combat/defense_die.py
from assault_model.combat.dice_color import DiceColor


class DefenseDie:
    def __init__(self, color: DiceColor):
        self.color = color