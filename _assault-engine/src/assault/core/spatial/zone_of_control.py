from typing import Set, Tuple

from assault.core.game_state import GameState
from assault.core.unit import Unit


HexCoord = Tuple[int, int]


class ZoneOfControlService:
    """
    Provides Zone of Control (ZOC) queries.

    According to the manual:
    - A unit controls all adjacent hexes while alive
    """

    def __init__(self, state: GameState) -> None:
        self.state = state

    def get_adjacent_hexes(self, q: int, r: int) -> Set[HexCoord]:
        """
        Returns axial coordinates of hexes adjacent to (q, r).
        """
        directions = [
            (+1, 0), (-1, 0),
            (0, +1), (0, -1),
            (+1, -1), (-1, +1),
        ]
        return {
            (q + dq, r + dr)
            for dq, dr in directions
            if (q + dq, r + dr) in self.state.hexes
        }

    def get_unit_zoc(self, unit: Unit) -> Set[HexCoord]:
        """
        Returns the set of hexes controlled by the unit.
        """
        if not unit.is_alive():
            return set()

        q, r = unit.position
        return self.get_adjacent_hexes(q, r)

    def is_hex_in_enemy_zoc(self, unit: Unit, hex_coord: HexCoord) -> bool:
        """
        Returns True if the given hex is in the ZOC of any enemy unit.
        """
        unit_side = unit.unit_id[:2]

        for side, units in self.state.units.items():
            if side == unit_side:
                continue

            for other in units.values():
                if not other.is_alive():
                    continue

                if hex_coord in self.get_unit_zoc(other):
                    return True

        return False