from assault_model.map.terrain import Terrain
from assault_model.units.unit_type import UnitCategory


class MovementTerrainRules:
    """
    Determines whether a unit may legally enter a destination hex
    based on the final destination state.

    Rules: TM-R02, TM-R03, TM-R09
    """

    @staticmethod
    def can_enter_hex(unit, hex_tile) -> bool:
        """
        Returns True if the given unit is allowed to enter the destination hex.

        Evaluates only final destination legality. No pathfinding or intent
        evaluation is performed.

        Rules: TM-R02, TM-R03
        """

        # Defensive guard
        if hex_tile is None or not unit.alive:
            return False

        terrain = hex_tile.terrain
        category = unit.unit_type.category

        # -------------------------
        # WATER terrain restriction
        # -------------------------
        # Infantry and vehicles may not enter WATER hexes
        # unless explicitly allowed by movement capability.
        # Rules: TM-R02
        if terrain == Terrain.WATER:
            return False

        # -------------------------
        # Default: allowed
        # -------------------------
        return True
