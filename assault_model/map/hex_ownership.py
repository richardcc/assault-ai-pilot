# assault_model/map/hex_ownership.py
from enum import Enum


class HexOwnership(Enum):
    NONE = "NONE"
    SIDE_A = "SIDE_A"
    SIDE_B = "SIDE_B"