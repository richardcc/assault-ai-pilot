from typing import Tuple, Union
from assault_model.map.hex_coord import HexCoord


CoordLike = Union[Tuple[int, int], HexCoord]


def _as_qr(pos: CoordLike) -> Tuple[int, int]:
    """
    Normalize coordinate inputs to (q, r).
    """
    if isinstance(pos, HexCoord):
        return pos.q, pos.r
    return pos


# ✅ NUEVO: conversión offset (odd-r) → axial
def _offset_to_axial(q: int, r: int) -> Tuple[int, int]:
    """
    Convert odd-r offset coordinates to axial coordinates.

    Your movement rules use an odd-r layout, so we must
    convert to axial before computing distance.
    """
    axial_q = q - ((r - (r & 1)) // 2)
    axial_r = r
    return axial_q, axial_r


def _axial_to_offset(aq: int, ar: int) -> Tuple[int, int]:
    """Inverse of _offset_to_axial for odd-r storage (q=column, r=row)."""
    return aq + ((ar - (ar & 1)) // 2), ar


def hex_distance(a: CoordLike, b: CoordLike) -> int:
    """
    Compute hex distance for an odd-r offset grid.

    Internally:
    offset → axial → cube distance
    """

    aq, ar = _as_qr(a)
    bq, br = _as_qr(b)

    # ✅ CONVERSIÓN CLAVE
    aq, ar = _offset_to_axial(aq, ar)
    bq, br = _offset_to_axial(bq, br)

    return max(
        abs(aq - bq),
        abs(ar - br),
        abs((aq + ar) - (bq + br)),
    )

def safe_hex_distance(a, b):
    """
    Safe wrapper around hex_distance.

    Guarantees:
    - Never crashes
    - Returns large value if invalid input
    """

    # ✅ None check
    if a is None or b is None:
        return 999

    # ✅ type check
    if not hasattr(a, "q") or not hasattr(a, "r"):
        return 999

    if not hasattr(b, "q") or not hasattr(b, "r"):
        return 999

    return hex_distance(a, b)
