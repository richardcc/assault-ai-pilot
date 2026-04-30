# assault_model/map/hex_coord.py
from assault_model.map.hex_direction import HexDirection


class HexCoord:
    def __init__(self, q: int, r: int):
        self.q = q
        self.r = r

    def neighbor(self, direction: HexDirection) -> "HexCoord":
        return HexCoord(
            self.q + direction.dq,
            self.r + direction.dr,
        )

    def neighbors(self) -> list["HexCoord"]:
        return [self.neighbor(d) for d in HexDirection]