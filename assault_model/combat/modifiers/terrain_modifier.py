from assault_model.combat.modifier import DiceModifier
from assault_model.combat.dice_color import DiceColor
from assault_model.map.terrain_config import terrain_config
from assault_model.combat.line_of_sight import LineOfSight


class TerrainModifier(DiceModifier):
    """
    Applies terrain-based defense modifiers using terrain_config.
    Also integrates LOS effects (HINDERED → extra defense).
    """

    def __init__(self, defense_bonus=None, los=None):
        self.defense_bonus = defense_bonus or []
        self.los = los  # ✅ NEW


    @staticmethod
    def from_hex(hex_, unit, los=None):
        """
        Build a TerrainModifier using:
        - terrain (from hex)
        - unit class
        - LOS condition (optional)
        """

        terrain_name = hex_.get_terrain()

        # ✅ base defense from terrain
        dice_names = terrain_config.get_defense_dice(
            terrain_name,
            unit.unit_class.name
        )

        dice = []
        for name in dice_names:
            try:
                dice.append(DiceColor[name])
            except KeyError:
                raise ValueError(f"Invalid dice color '{name}' in terrain_config")

        return TerrainModifier(defense_bonus=dice, los=los)


    def modify_attack(self, dice):
        return dice


    def modify_defense(self, dice):

        result = dice + self.defense_bonus

        # -------------------------------------------------
        # ✅ LOS EFFECT (RULEBOOK 10.9.2)
        # -------------------------------------------------
        if self.los == LineOfSight.HINDERED:

            # ✅ simple, consistent with system:
            # reuse weakest defensive die
            result.append(DiceColor.GREEN)

        return result
