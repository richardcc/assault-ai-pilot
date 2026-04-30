from assault_model.map.terrain import Terrain
from assault_model.map.hex_direction import HexDirection


class Hex:
    """
    Atomic spatial element using axial hex coordinates (q, r).

    Supports movement in 6 directions.
    """

    def __init__(self, q: int, r: int, terrain: Terrain) -> None:
        self.q = q
        self.r = r
        self.terrain = terrain

    def neighbor(self, direction: HexDirection) -> "Hex":
        return Hex(
            self.q + direction.dq,
            self.r + direction.dr,
            self.terrain,
        )

    def neighbors(self) -> list["Hex"]:
        return [self.neighbor(d) for d in HexDirection]