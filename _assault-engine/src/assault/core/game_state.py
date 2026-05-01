from typing import Dict, Tuple, Optional
from copy import deepcopy

from assault.core.hex import Hex
from assault.core.unit import Unit


HexCoord = Tuple[int, int]


class GameState:
    """
    Central container holding the entire game state.

    This is the single authoritative source of truth
    for map layout, units, and turn-level state.
    """

    def __init__(self) -> None:
        # Map
        self.hexes: Dict[HexCoord, Hex] = {}

        # Units grouped by side:
        # side -> { unit_id -> Unit }
        self.units: Dict[str, Dict[str, Unit]] = {}

        # Turn / round counters (engine-level)
        self.turn: int = 1

        # Victory Points
        self.vp_hexes: set[HexCoord] = set()
        self.vp_owner: Dict[HexCoord, Optional[str]] = {}
        self.vp_value: int = 0

    # --------------------------------------------------
    # Hex helpers
    # --------------------------------------------------

    def add_hex(self, hex_: Hex) -> None:
        """Adds a hex to the game map."""
        self.hexes[(hex_.q, hex_.r)] = hex_

    # --------------------------------------------------
    # Unit helpers
    # --------------------------------------------------

    def add_unit(self, side: str, unit: Unit) -> None:
        """Adds a unit to the game and places it on the map."""
        self.units.setdefault(side, {})
        self.units[side][unit.unit_id] = unit

        q, r = unit.position
        self.hexes[(q, r)].occupant = unit.unit_id

    def get_unit(self, unit_id: str) -> Optional[Unit]:
        """Retrieves a unit by its identifier."""
        for units in self.units.values():
            if unit_id in units:
                return units[unit_id]
        return None

    def remove_unit(self, unit: Unit) -> None:
        """Removes a unit from the game state."""
        for side, units in self.units.items():
            if unit.unit_id in units:
                del units[unit.unit_id]
                break

        if unit.position in self.hexes:
            self.hexes[unit.position].occupant = None

    # --------------------------------------------------
    # Snapshotting
    # --------------------------------------------------

    def snapshot(self) -> "GameState":
        """Returns a deep snapshot of the current game state."""
        return deepcopy(self)

    # --------------------------------------------------
    # VP logic (NO debug, NO side effects)
    # --------------------------------------------------

    def setup_vps(self, hexes, value: int) -> None:
        """Initialize VP hexes from scenario data."""
        self.vp_hexes = set(hexes)
        self.vp_owner = {h: None for h in self.vp_hexes}
        self.vp_value = value

    def update_vp_control(self) -> None:
        """
        Update VP ownership at end of turn.

        A VP hex is controlled if:
        - A unit occupies the hex
        - The unit is NOT suppressed
        """
        for hex_coord in self.vp_hexes:
            hex_ = self.hexes.get(hex_coord)
            if not hex_ or not hex_.occupant:
                self.vp_owner[hex_coord] = None
                continue

            unit = self.get_unit(hex_.occupant)
            if unit is not None and not unit.is_suppressed:
                self.vp_owner[hex_coord] = unit.side
            else:
                self.vp_owner[hex_coord] = None

    def controls_any_vp(self, side: str) -> bool:
        """Returns True if the given side controls at least one VP hex."""
        return any(owner == side for owner in self.vp_owner.values())