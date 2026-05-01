from dataclasses import dataclass
from typing import Tuple

HexCoord = Tuple[int, int]


@dataclass(frozen=True)
class MovementAction:
    """
    Pure movement intention.

    This class:
    - does NOT know the unit
    - does NOT know the map
    - does NOT validate legality
    """
    target_hex: HexCoord
