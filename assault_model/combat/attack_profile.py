from assault_model.combat.dice_color import DiceColor
from assault_model.combat.attack_sector import AttackSector


class AttackProfile:
    def __init__(self, ranged_attack: dict, close_combat: dict):
        """
        ranged_attack:
            target_type -> distance_range -> [DiceColor]
        close_combat:
            target_type -> [DiceColor]
        """
        self.ranged_attack = ranged_attack
        self.close_combat = close_combat

    def get_close_combat_dice(self, target_type: str):
        """
        Returns DiceColor list for close combat (distance 0).
        """
        return self.close_combat.get(target_type, [])

    def get_ranged_dice(self, target_type: str, distance: int):
        for distance_range, dice in self.ranged_attack.get(target_type, {}).items():
            if "-" in distance_range:
                lo, hi = map(int, distance_range.split("-"))
                if lo <= distance <= hi:
                    return dice
            else:
                if int(distance_range) == distance:
                    return dice
        return []