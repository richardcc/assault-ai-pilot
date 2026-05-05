# assault_model/map/hex_state.py

from assault_model.map.hex import Hex
from assault_model.map.hex_ownership import HexOwnership


class HexState:
    """
    Dynamic state associated with a single hex.

    This object stores gameplay-related state that is not intrinsic
    to the hex geometry itself.

    Typical responsibilities:
    - Track ownership / control
    - Track contested status
    - Store terrain overlays or features (extended elsewhere)

    Design rule:
    - Hex stores WHAT the tile is.
    - HexState stores WHAT IS HAPPENING on that tile.
    """

    def __init__(self, hex_: Hex):
        self.hex = hex_
        self.ownership = HexOwnership.NONE
        self.contested = False