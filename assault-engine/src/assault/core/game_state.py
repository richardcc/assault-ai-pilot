from typing import Dict, Tuple

from assault.core.hex import Hex
from assault.core.unit import Unit


class GameState:
    """
    Central container holding the entire game state.

    This is the single authoritative source of truth
    for map layout, units, and turn progression.
    """

    def __init__(self) -> None:
        self.hexes: Dict[Tuple[int, int], Hex] = {}
        self.units: Dict[str, Unit] = {}
        self.turn: int = 1

    def add_hex(self, hex_: Hex) -> None:
        """
        Adds a hex to the game map.
        """
        self.hexes[(hex_.q, hex_.r)] = hex_

    def add_unit(self, unit: Unit) -> None:
        """
        Adds a unit to the game and places it on the map.
        """
        self.units[unit.unit_id] = unit
        q, r = unit.position
        self.hexes[(q, r)].occupant = unit.unit_id

    def get_unit(self, unit_id: str) -> Unit:
        """
        Retrieves a unit by its identifier.
        """
        return self.units[unit_id]