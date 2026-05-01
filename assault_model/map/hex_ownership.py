# assault_model/map/hex_ownership.py
#
# Hex ownership definition.
# Describes which side currently controls a map hex.
#
# NOTE:
# - This module defines ONLY the concept of ownership.
# - It does NOT decide how ownership is calculated.

from enum import Enum


class HexOwnership(Enum):
    """
    Ownership state of a hex.

    Used by:
    - GameState (control calculation)
    - VictoryPointTracker (scoring)
    - ConsoleObserver (rendering color)

    Values:
    - NONE  : Hex is uncontrolled or contested
    - SIDE_A: Controlled by one side (e.g. GE)
    - SIDE_B: Controlled by the other side (e.g. US)
    """

    NONE = "NONE"
    SIDE_A = "SIDE_A"
    SIDE_B = "SIDE_B"

    def is_controlled(self) -> bool:
        """
        Returns True if the hex is controlled by a side.
        """
        return self in (HexOwnership.SIDE_A, HexOwnership.SIDE_B)