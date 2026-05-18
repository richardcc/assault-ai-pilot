from assault_model.combat.modifier import DiceModifier
from assault_model.combat.dice_color import DiceColor
from assault_model.config.terrain_config import terrain_config


class TerrainModifier(DiceModifier):
    """
    Applies terrain-based defense modifiers using terrain_config.
    """

    def __init__(self, defense_bonus=None):
        self.defense_bonus = defense_bonus or []

    @staticmethod
    def from_hex(hex_, unit):
        """
        Build a TerrainModifier using:
        - effective terrain (from hex)
        - unit type (infantry, vehicle...)
        """

        # ✅ single source of truth (world decides terrain)
        terrain_name = hex_.get_terrain()

        # ✅ retrieve rules from config (rules engine)
        dice_names = terrain_config.get_defense_dice(
            terrain_name,
            unit.unit_class.name
        )

        # ✅ safe conversion (avoids crash if config has typo)
        dice = []
        for name in dice_names:
            try:
                dice.append(DiceColor[name])
            except KeyError:
                raise ValueError(f"Invalid dice color '{name}' in terrain_config")

        return TerrainModifier(dice)

    def modify_attack(self, dice):
        return dice

    def modify_defense(self, dice):
        return dice + self.defense_bonus