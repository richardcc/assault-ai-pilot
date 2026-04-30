# assault_model/map/hex_direction.py
from enum import Enum


class HexDirection(Enum):
    NE = (1, -1)
    E = (1, 0)
    SE = (0, 1)
    SW = (-1, 1)
    W = (-1, 0)
    NW = (0, -1)

    @property
    def dq(self) -> int:
        return self.value[0]

    @property
    def dr(self) -> int:
        return self.value[1]