from enum import Enum
import math

from assault_model.map.hex_coord import HexCoord


# -------------------------------------------------
# LOS RESULT
# -------------------------------------------------

class LineOfSight(Enum):
    CLEAR = 0
    HINDERED = 1
    BLOCKED = 2


# -------------------------------------------------
# CACHE GLOBAL
# -------------------------------------------------

_los_cache = {}


def _make_key(a: HexCoord, b: HexCoord):
    return (a.q, a.r, b.q, b.r)


# -------------------------------------------------
# HEX GEOMETRY
# -------------------------------------------------

def _hex_corners(hex_coord: HexCoord):
    """
    Coordenadas de los 6 vértices del hex.
    Aproximación axial en plano continuo.
    """
    cx = hex_coord.q
    cy = hex_coord.r

    size = 1.0
    corners = []

    for i in range(6):
        angle = math.pi / 3 * i
        x = cx + size * math.cos(angle)
        y = cy + size * math.sin(angle)
        corners.append((x, y))

    return corners


def _ccw(a, b, c):
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(p1, p2, p3, p4):
    return (_ccw(p1, p3, p4) != _ccw(p2, p3, p4) and
            _ccw(p1, p2, p3) != _ccw(p1, p2, p4))


def _segment_intersects_hex(start: HexCoord, end: HexCoord, hex_coord: HexCoord):
    """
    Devuelve True SOLO si el segmento atraviesa el hex realmente.
    """

    s = (start.q, start.r)
    e = (end.q, end.r)

    corners = _hex_corners(hex_coord)

    # comprobar contra cada lado del hex
    for i in range(6):
        c1 = corners[i]
        c2 = corners[(i + 1) % 6]

        if _segments_intersect(s, e, c1, c2):
            return True

    return False


# -------------------------------------------------
# RECORRIDO BASE (candidatos)
# -------------------------------------------------

def _supercover_line(a: HexCoord, b: HexCoord):
    """
    Genera candidatos de hex a comprobar (superset).
    """
    N = max(
        abs(a.q - b.q),
        abs(a.r - b.r),
        abs((a.q + a.r) - (b.q + b.r)),
    )

    results = []

    for i in range(N + 1):
        t = 0 if N == 0 else i / N
        q = a.q + (b.q - a.q) * t
        r = a.r + (b.r - a.r) * t

        rq = round(q)
        rr = round(r)

        coord = HexCoord(rq, rr)

        if not results or coord != results[-1]:
            results.append(coord)

    return results


# -------------------------------------------------
# LOS CORE REAL
# -------------------------------------------------

def check_line_of_sight(attacker, target, game_map, terrain_config):

    start = attacker.position
    end = target.position

    key = _make_key(start, end)

    if key in _los_cache:
        return _los_cache[key]

    # candidatos (superset)
    candidates = _supercover_line(start, end)

    # quitar origen/destino
    path = candidates[1:-1]

    hindrance = 0

    for coord in path:

        # ✅ FILTRO REAL (geométrico)
        if not _segment_intersects_hex(start, end, coord):
            continue

        hex_ = game_map.get_hex(coord.q, coord.r)
        if not hex_:
            continue

        terrain = hex_.get_terrain()

        config = terrain_config.get(terrain)

        if not config:
            los_type = "CLEAR"
        else:
            los_type = config.get("los", "CLEAR")

        # -------------------------------------------------
        # BLOCKED
        # -------------------------------------------------
        if los_type == "BLOCKED":
            result = LineOfSight.BLOCKED
            _los_cache[key] = result
            return result

        # -------------------------------------------------
        # HINDERED
        # -------------------------------------------------
        if los_type == "HINDERED":
            hindrance += 1

            if hindrance >= 3:
                result = LineOfSight.BLOCKED
                _los_cache[key] = result
                return result

    # -------------------------------------------------
    # RESULTADO FINAL
    # -------------------------------------------------
    if hindrance >= 1:
        result = LineOfSight.HINDERED
    else:
        result = LineOfSight.CLEAR

    _los_cache[key] = result
    return result


def has_line_of_sight(attacker, target, game_map, terrain_config):
    return check_line_of_sight(
        attacker,
        target,
        game_map,
        terrain_config
    ) != LineOfSight.BLOCKED