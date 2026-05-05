# assault_model/map/hex_coord.py

from assault_model.map.hex_direction import HexDirection


class HexCoord:
    """
    Immutable axial hex coordinate (q, r).

    This is the canonical coordinate type used by the domain.
    It represents a position on the hex grid using axial coordinates.

    Responsibilities:
    - Store axial coordinates (q, r)
    - Support equality and hashing by value
    - Be safely usable as a key in dictionaries and sets

    Design note:
    - This class is intentionally minimal.
    - Movement, distance, and geometry are handled by utilities.
    """

    def __init__(self, q: int, r: int):
        self.q = q
        self.r = r

    def __eq__(self, other):
        return (
            isinstance(other, HexCoord)
            and self.q == other.q
            and self.r == other.r
        )

    def __hash__(self):
        return hash((self.q, self.r))