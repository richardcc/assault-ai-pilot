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
    - Support mapping protocol: `dict(coord) -> {"q": q, "r": r}`, `coord["q"]`
    - Provide factory `from_any` to normalize diverse input formats at the boundary
    """
    __slots__ = ("q", "r")

    def __init__(self, q: int, r: int):
        self.q = int(q)
        self.r = int(r)

    def __iter__(self):
        yield self.q
        yield self.r

    def keys(self) -> tuple[str, str]:
        return ("q", "r")

    def __getitem__(self, idx_or_key: int | str) -> int:
        if idx_or_key == 0 or idx_or_key == "q":
            return self.q
        elif idx_or_key == 1 or idx_or_key == "r":
            return self.r
        if isinstance(idx_or_key, int):
            raise IndexError("HexCoord index out of range (0 or 1)")
        raise KeyError(idx_or_key)

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

    def to_dict(self) -> dict[str, int]:
        return {"q": self.q, "r": self.r}

    def to_tuple(self) -> tuple[int, int]:
        return (self.q, self.r)

    def to_list(self) -> list[int]:
        return [self.q, self.r]

    @classmethod
    def from_any(cls, value: object) -> "HexCoord":
        """
        Normalize any coordinate representation into a canonical HexCoord.
        Accepts: HexCoord, [q, r], (q, r), {"q": q, "r": r},
        or dicts containing "position", "origin", "coords", "hex", "target_hex".
        """
        if isinstance(value, HexCoord):
            return value
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return cls(int(value[0]), int(value[1]))
        if isinstance(value, dict):
            if "q" in value and "r" in value and value["q"] is not None and value["r"] is not None:
                return cls(int(value["q"]), int(value["r"]))
            if "col" in value and "row" in value:
                return cls(int(value["col"]), int(value["row"]))
            for key in ("position", "origin", "coords", "hex", "target_hex"):
                nested = value.get(key)
                if nested is not None:
                    return cls.from_any(nested)
        if hasattr(value, "q") and hasattr(value, "r"):
            return cls(int(getattr(value, "q")), int(getattr(value, "r")))
        raise ValueError(f"Cannot convert {value!r} to HexCoord")