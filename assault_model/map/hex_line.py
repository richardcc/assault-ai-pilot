from assault_model.map.hex_coord import HexCoord


# -------------------------------------------------
# Helpers cube coords
# -------------------------------------------------

def _cube_from_axial(h: HexCoord):
    x = h.q
    z = h.r
    y = -x - z
    return (x, y, z)


def _cube_to_axial(x: int, y: int, z: int):
    return HexCoord(x, z)


def _cube_lerp(a, b, t):
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _cube_round(x, y, z):
    rx = round(x)
    ry = round(y)
    rz = round(z)

    dx = abs(rx - x)
    dy = abs(ry - y)
    dz = abs(rz - z)

    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry

    return rx, ry, rz


# -------------------------------------------------
# Public API
# -------------------------------------------------

def hex_distance(a: HexCoord, b: HexCoord) -> int:
    return (abs(a.q - b.q) + abs(a.q + a.r - b.q - b.r) + abs(a.r - b.r)) // 2


def hex_line(a: HexCoord, b: HexCoord):
    """
    Returns list of hex coords forming a straight line from a to b.
    Uses cube coords internally for correctness.
    """

    a_cube = _cube_from_axial(a)
    b_cube = _cube_from_axial(b)

    N = hex_distance(a, b)

    results = []

    if N == 0:
        return [a]

    for i in range(N + 1):
        t = i / N
        lerp = _cube_lerp(a_cube, b_cube, t)
        rounded = _cube_round(*lerp)
        results.append(_cube_to_axial(*rounded))

    return results
