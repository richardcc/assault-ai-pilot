# assault_model/map/hex_utils.py

from typing import Tuple, Union
from assault_model.map.hex_coord import HexCoord


CoordLike = Union[Tuple[int, int], HexCoord]


def _as_qr(pos: CoordLike) -> Tuple[int, int]:
    """
    Normalize coordinate inputs to axial (q, r).

    Accepts:
    - Legacy (q, r) tuples
    - HexCoord objects (new architecture)

    Returns:
    - (q, r) tuple

    This helper exists to allow legacy utilities to coexist
    with the new HexCoord-based domain model.
    """
    if isinstance(pos, HexCoord):
        return pos.q, pos.r
    return pos


def hex_distance(a: CoordLike, b: CoordLike) -> int:
    """
    Compute axial hex distance between two hex coordinates.

    Distance formula (cube projection):
        distance = max(
            |dq|,
            |dr|,
            |dq + dr|
        )

    Parameters:
    - a, b:
      * Either (q, r) tuples (legacy code)
      * Or HexCoord objects (new architecture)

    Returns:
    - Integer distance in hexes

    Design note:
    - This function is intentionally permissive about input types
      to avoid forcing domain code to downgrade to tuples.
    """

    aq, ar = _as_qr(a)
    bq, br = _as_qr(b)

    return max(
        abs(aq - bq),
        abs(ar - br),
        abs((aq + ar) - (bq + br)),
    )