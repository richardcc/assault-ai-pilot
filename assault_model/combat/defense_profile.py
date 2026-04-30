from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.dice_color import DiceColor


class DefenseProfile:
    def __init__(self, base_defense: dict):
        """
        base_defense:
            AttackSector -> [DiceColor]
        """
        self.base_defense = base_defense

    def get_close_combat_defense(self, sector: AttackSector):
        return self.base_defense.get(sector, [])
