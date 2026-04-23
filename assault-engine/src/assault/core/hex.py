from dataclasses import dataclass
from typing import Optional

from assault.core.terrain import Terrain


@dataclass
class Hex:
    """
    Represents a single hexagonal map cell using axial coordinates.

    The Hex class stores spatial and terrain information,
    but does not enforce movement or combat rules.

    Attributes:
        q: Axial q coordinate.
        r: Axial r coordinate.
        terrain: Terrain data assigned to this hex.
        elevation: Elevation level relative to base map.
        occupant: ID of the occupying unit, if any.
    """
    q: int
    r: int
    terrain: Terrain
    elevation: int = 0
    occupant: Optional[str] = None

    def is_occupied(self) -> bool:
        """
        Returns whether the hex is currently occupied by a unit.
        """
        return self.occupant is not None