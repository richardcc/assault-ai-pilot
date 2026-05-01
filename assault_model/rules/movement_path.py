from dataclasses import dataclass
from typing import List, Optional

from assault_model.map.hex_coord import HexCoord
from assault_model.rules.movement_outcome import MovementOutcome


@dataclass(frozen=True)
class MovementPath:
    """
    A complete and meaningful movement.

    - path: hexes traversed (at least one)
    - outcome: how the movement ends
    - target_unit_id: enemy or vehicle if relevant
    """
    path: List[HexCoord]
    outcome: MovementOutcome
    target_unit_id: Optional[str] = None