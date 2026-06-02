import math
from enum import Enum

from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_distance


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
_LOS_CACHE_VERSION = 8


def _make_key(a: HexCoord, b: HexCoord):
    return (_LOS_CACHE_VERSION, a.q, a.r, b.q, b.r)


def clear_los_cache():
    """Drop cached rays after LOS path logic changes."""
    _los_cache.clear()


# Same layout as assault_ai_ui hexGridRenderer.ts (odd-r, pointy-top)
_UI_HEX_SIZE = 30.0
_UI_HEX_WIDTH = _UI_HEX_SIZE * math.sqrt(3.0)
_UI_HEX_HEIGHT = _UI_HEX_SIZE * 1.5


def _hex_to_pixel_ui(q: int, r: int) -> tuple[float, float]:
    x = _UI_HEX_WIDTH * (q + 0.5 * (r % 2)) + _UI_HEX_WIDTH / 2.0
    y = _UI_HEX_HEIGHT * r + _UI_HEX_SIZE
    return x, y


def _pixel_to_hex_ui(x: float, y: float) -> HexCoord:
    y_centered = y - _UI_HEX_SIZE
    r = int(round(y_centered / _UI_HEX_HEIGHT))
    x_col = x - _UI_HEX_WIDTH / 2.0 - _UI_HEX_WIDTH * 0.5 * (r % 2)
    q = int(round(x_col / _UI_HEX_WIDTH))
    return HexCoord(q, r)


def _odd_r_neighbor_deltas(r: int) -> list[tuple[int, int]]:
    if r % 2 == 0:
        return [(-1, 0), (+1, 0), (0, -1), (0, +1), (-1, -1), (-1, +1)]
    return [(-1, 0), (+1, 0), (0, -1), (0, +1), (+1, -1), (+1, +1)]


def _hexes_at_pixel_ui(x: float, y: float) -> list[HexCoord]:
    """When the ray lies on the edge between two hexes, return both."""
    primary = _pixel_to_hex_ui(x, y)
    cx, cy = _hex_to_pixel_ui(primary.q, primary.r)
    d0 = (x - cx) ** 2 + (y - cy) ** 2
    edge_eps_sq = (_UI_HEX_WIDTH * 0.35) ** 2

    hexes = [primary]
    for dq, dr in _odd_r_neighbor_deltas(primary.r):
        nq, nr = primary.q + dq, primary.r + dr
        nx, ny = _hex_to_pixel_ui(nq, nr)
        d1 = (x - nx) ** 2 + (y - ny) ** 2
        if abs(d1 - d0) <= edge_eps_sq:
            neighbor = HexCoord(nq, nr)
            if neighbor != primary:
                hexes.append(neighbor)
    return hexes


def _append_hex_to_path(path: list[HexCoord], h: HexCoord) -> None:
    if not path or path[-1] != h:
        path.append(h)


def _ray_sample_segments(a: HexCoord, b: HexCoord) -> list[list[HexCoord]]:
    """One entry per sample along the ray; each entry has 1–2 hexes on an edge."""
    if a.q == b.q and a.r == b.r:
        return [[HexCoord(a.q, a.r)]]

    dist = hex_distance(a, b)
    if dist <= 1:
        return [[a], [b]]

    ax, ay = _hex_to_pixel_ui(a.q, a.r)
    bx, by = _hex_to_pixel_ui(b.q, b.r)
    samples = max(dist * 4, dist + 1)

    segments: list[list[HexCoord]] = []
    for i in range(samples + 1):
        t = i / samples
        px = ax + (bx - ax) * t
        py = ay + (by - ay) * t
        segments.append(_hexes_at_pixel_ui(px, py))
    return segments


def _flatten_ray_path(a: HexCoord, b: HexCoord, segments: list[list[HexCoord]]) -> list[HexCoord]:
    path = [a]
    for seg in segments:
        for h in seg:
            _append_hex_to_path(path, h)
    if path[-1] != b:
        path.append(HexCoord(b.q, b.r))
    return path


def _terrain_los_at(coord: HexCoord, game_map, terrain_config) -> str | None:
    hex_ = game_map.get_hex(coord.q, coord.r)
    if not hex_:
        return None
    terrain = hex_.get_terrain()
    config = terrain_config.get(terrain)
    return config.get("los", "CLEAR") if config else "CLEAR"


def _hex_path_ui_pixel(a: HexCoord, b: HexCoord) -> list[HexCoord]:
    """Straight ray; includes both hexes when the line runs along a shared edge."""
    segments = _ray_sample_segments(a, b)
    return _flatten_ray_path(a, b, segments)


def _primary_hex_path(a: HexCoord, b: HexCoord) -> list[HexCoord]:
    """Ray spine: one hex per sample (the hex the pixel lies in)."""
    segments = _ray_sample_segments(a, b)
    path = [a]
    for seg in segments:
        if seg:
            _append_hex_to_path(path, seg[0])
    if path[-1].q != b.q or path[-1].r != b.r:
        path.append(HexCoord(b.q, b.r))
    return path


def _inner_hexes_for_los(path: list[HexCoord], end: HexCoord) -> list[HexCoord]:
    """Intermediates on the ray only, each hex once, never the target."""
    inner: list[HexCoord] = []
    seen: set[tuple[int, int]] = set()
    for h in path[1:-1]:
        key = (h.q, h.r)
        if key == (end.q, end.r) or key in seen:
            continue
        seen.add(key)
        inner.append(h)
    return inner


def _hex_path_strict(a: HexCoord, b: HexCoord) -> list[HexCoord]:
    return _hex_path_ui_pixel(a, b)


# -------------------------------------------------
# LOS CORE
# -------------------------------------------------

def check_line_of_sight(attacker, target, game_map, terrain_config):
    start = getattr(attacker, "position", None)
    end = getattr(target, "position", None)

    if start is None or end is None:
        return LineOfSight.BLOCKED

    key = _make_key(start, end)

    if key in _los_cache:
        result, cached_debug = _los_cache[key]
        attacker._los_debug = cached_debug
        return result

    reverse_key = (_LOS_CACHE_VERSION, end.q, end.r, start.q, start.r)
    if reverse_key in _los_cache:
        result, cached_debug = _los_cache[reverse_key]
        attacker._los_debug = {
            "blocking": cached_debug["blocking"],
            "hindrance": cached_debug["hindrance"],
            "path": list(reversed(cached_debug["path"]))
        }
        return result

    path_full = _hex_path_strict(start, end)

    if not path_full:
        return LineOfSight.BLOCKED

    los_path = _primary_hex_path(start, end)
    inner_path = _inner_hexes_for_los(los_path, end)

    hindrance = 0
    blocking_hexes = []
    hindrance_hexes = []
    is_blocked = False

    for coord in inner_path:
        los_type = _terrain_los_at(coord, game_map, terrain_config)
        if los_type is None:
            continue

        if los_type == "BLOCKED":
            is_blocked = True
            blocking_hexes.append((coord.q, coord.r))

        elif los_type == "HINDERED":
            hindrance += 1
            hindrance_hexes.append((coord.q, coord.r))
            if hindrance >= 3:
                is_blocked = True

    if hindrance >= 3:
        for h_coord in hindrance_hexes:
            if h_coord not in blocking_hexes:
                blocking_hexes.append(h_coord)

    if is_blocked:
        result = LineOfSight.BLOCKED
    elif hindrance >= 1:
        result = LineOfSight.HINDERED
    else:
        result = LineOfSight.CLEAR

    # Datos limpios y ordenados secuencialmente para pintar las flechas en el Frontend
    debug_data = {
        "blocking": blocking_hexes,
        "hindrance": hindrance_hexes,
        "path": [(c.q, c.r) for c in path_full]
    }
    attacker._los_debug = debug_data

    _los_cache[key] = (result, debug_data)
    return result


# -------------------------------------------------
# PUBLIC API
# -------------------------------------------------

def has_line_of_sight(attacker, target, game_map, terrain_config):
    return check_line_of_sight(
        attacker,
        target,
        game_map,
        terrain_config
    ) != LineOfSight.BLOCKED