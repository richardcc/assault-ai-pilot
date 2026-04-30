# assault_model/combat/attack_die.py
from assault_model.combat.dice_color import DiceColor


class AttackDie:
    def __init__(self, color: DiceColor):
        self.color = color