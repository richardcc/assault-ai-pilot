from typing import Tuple, Union
from assault_model.map.hex_coord import HexCoord


CoordLike = Union[Tuple[int, int], HexCoord]


def _as_qr(pos: CoordLike) -> Tuple[int, int]:
    """
    Fast normalize coordinate inputs to (q, r).
    """
    try:
        return pos.q, pos.r
    except AttributeError:
        return int(pos[0]), int(pos[1])


# ✅ Conversión offset (odd-r) → axial
def _offset_to_axial(q: int, r: int) -> Tuple[int, int]:
    """
    Convert odd-r offset coordinates to axial coordinates.

    Your movement rules use an odd-r layout, so we must
    convert to axial before computing distance.
    """
    return q - ((r - (r & 1)) // 2), r


def _axial_to_offset(aq: int, ar: int) -> Tuple[int, int]:
    """Inverse of _offset_to_axial for odd-r storage (q=column, r=row)."""
    return aq + ((ar - (ar & 1)) // 2), ar


def neighbors(pos: CoordLike) -> list:
    """
    Devuelve los 6 vecinos de un hex como tuplas (q, r).

    Usa el MISMO modelo de coordenadas odd-r que hex_distance(), de modo
    que cada vecino devuelto cumple hex_distance(pos, vecino) == 1.
    """
    q, r = _as_qr(pos)

    if r % 2 == 0:
        deltas = [(-1, 0), (+1, 0), (0, -1), (0, +1), (-1, -1), (-1, +1)]
    else:
        deltas = [(-1, 0), (+1, 0), (0, -1), (0, +1), (+1, -1), (+1, +1)]

    return [(q + dq, r + dr) for dq, dr in deltas]


def hex_distance(a: CoordLike, b: CoordLike) -> int:
    """
    Compute hex distance for an odd-r offset grid.

    Internally:
    offset → axial → cube distance
    """
    aq, ar = _as_qr(a)
    bq, br = _as_qr(b)

    axial_aq, axial_ar = _offset_to_axial(aq, ar)
    axial_bq, axial_br = _offset_to_axial(bq, br)

    return max(
        abs(axial_aq - axial_bq),
        abs(axial_ar - axial_br),
        abs((axial_aq + axial_ar) - (axial_bq + axial_br)),
    )


def safe_hex_distance(a, b) -> int:
    """
    Safe, high-performance wrapper around hex_distance.

    Guarantees:
    - Never crashes
    - Returns 999 if invalid input
    """
    if a is None or b is None:
        return 999

    try:
        aq = a.q if hasattr(a, "q") else a[0]
        ar = a.r if hasattr(a, "r") else a[1]
        bq = b.q if hasattr(b, "q") else b[0]
        br = b.r if hasattr(b, "r") else b[1]

        axial_aq = aq - ((ar - (ar & 1)) // 2)
        axial_bq = bq - ((br - (br & 1)) // 2)

        return max(
            abs(axial_aq - axial_bq),
            abs(ar - br),
            abs((axial_aq + ar) - (axial_bq + br)),
        )
    except Exception:
        return 999


def hex_range(center: CoordLike, radius: int) -> list[Tuple[int, int]]:
    """
    Return all hexes within hex_distance <= radius from center,
    in odd-r offset coordinates (q, r) in O(R^2) closed-form arithmetic.
    """
    if radius < 0:
        return []
    q0, r0 = _as_qr(center)
    if radius == 0:
        return [(q0, r0)]

    aq0, ar0 = _offset_to_axial(q0, r0)
    results: list[Tuple[int, int]] = []
    for dq in range(-radius, radius + 1):
        dr_min = max(-radius, -dq - radius)
        dr_max = min(radius, -dq + radius)
        for dr in range(dr_min, dr_max + 1):
            results.append(_axial_to_offset(aq0 + dq, ar0 + dr))
    return results
