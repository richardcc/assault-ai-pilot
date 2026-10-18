# assault_model/map/hex_coord.py

from assault_model.map.hex_direction import HexDirection


class HexCoord:
    """
    Immutable axial hex coordinate (q, r).

    This is the canonical coordinate type used by the domain.
    It represents a position on the hex grid using axial coordinates.

    Responsibilities:
    - Store axial coordinates (q, r)
    - Support equality and hashing by value (including tuple compatibility)
    - Be safely usable as a key in dictionaries and sets
    - Support sequence unpacking: `q, r = coord`
    """
    __slots__ = ("q", "r")

    def __init__(self, q: int, r: int):
        self.q = int(q)
        self.r = int(r)

    def __iter__(self):
        yield self.q
        yield self.r

    def __getitem__(self, idx: int) -> int:
        if idx == 0:
            return self.q
        elif idx == 1:
            return self.r
        raise IndexError("HexCoord index out of range (0 or 1)")

    def __len__(self) -> int:
        return 2

    def __eq__(self, other):
        if isinstance(other, HexCoord):
            return self.q == other.q and self.r == other.r
        if isinstance(other, (tuple, list)) and len(other) == 2:
            return self.q == other[0] and self.r == other[1]
        return False

    def __hash__(self):
        return hash((self.q, self.r))

    def __repr__(self) -> str:
        return f"HexCoord({self.q}, {self.r})"