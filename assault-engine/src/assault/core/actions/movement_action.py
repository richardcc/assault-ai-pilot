# assault/core/actions/movement_action.py

from dataclasses import dataclass
from typing import Tuple

from assault.core.unit import Unit
from assault.core.game_state import GameState


HexCoord = Tuple[int, int]


@dataclass
class MovementAction:
    """
    Represents a basic movement action to an adjacent hex.
    """
    unit: Unit
    target_hex: HexCoord

    def can_execute(self, state: GameState) -> bool:
        """
        Checks whether the movement is allowed.
        """
        # Hex must exist
        if self.target_hex not in state.hexes:
            return False

        hex_ = state.hexes[self.target_hex]

        # Must not be occupied
        if hex_.occupant is not None:
            return False

        # Terrain must be passable
        if hex_.terrain.movement_cost >= 99:
            return False

        return True