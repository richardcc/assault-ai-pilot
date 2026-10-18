import math
from enum import Enum
import numpy as np

from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_distance, _numba_njit, _PARITY_DELTAS_NP


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
_ray_geometry_cache = {}
_LOS_CACHE_VERSION = 8


def _make_key(a: HexCoord, b: HexCoord, terrain_sig: int = 0):
    return (_LOS_CACHE_VERSION, terrain_sig, a.q, a.r, b.q, b.r)


def clear_los_cache():
    """Drop cached rays after LOS path logic changes."""
    _los_cache.clear()
    _ray_geometry_cache.clear()


# Same layout as assault_ai_ui hexGridRenderer.ts (odd-r, pointy-top)
_UI_HEX_SIZE = 30.0
_UI_HEX_WIDTH = _UI_HEX_SIZE * math.sqrt(3.0)
_UI_HEX_HEIGHT = _UI_HEX_SIZE * 1.5
_EDGE_EPS_SQ = (_UI_HEX_WIDTH * 0.35) ** 2


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

    hexes = [primary]
    for dq, dr in _odd_r_neighbor_deltas(primary.r):
        nq, nr = primary.q + dq, primary.r + dr
        nx, ny = _hex_to_pixel_ui(nq, nr)
        d1 = (x - nx) ** 2 + (y - ny) ** 2
        if abs(d1 - d0) <= _EDGE_EPS_SQ:
            neighbor = HexCoord(nq, nr)
            if neighbor != primary:
                hexes.append(neighbor)
    return hexes


@_numba_njit(cache=True)
def _vectorized_fractional_ray_samples(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    samples: int,
    hex_size: float,
    hex_width: float,
    hex_height: float,
    edge_eps_sq: float,
    parity_deltas: np.ndarray,
):
    """
    Vectorized / Numba-compiled fractional linear ray interpolation in UI pixel/axial space.
    Evaluates all (samples + 1) fractional points and 6 neighbor edge-proximities simultaneously.
    """
    t = np.arange(samples + 1, dtype=np.float64) / float(samples)
    px = ax + (bx - ax) * t
    py = ay + (by - ay) * t

    r_arr = np.rint((py - hex_size) / hex_height).astype(np.int32)
    r_par = r_arr & 1
    x_col = px - (hex_width * 0.5) - (hex_width * 0.5 * r_par)
    q_arr = np.rint(x_col / hex_width).astype(np.int32)

    cx = hex_width * (q_arr + 0.5 * r_par) + hex_width * 0.5
    cy = hex_height * r_arr + hex_size
    d0 = (px - cx) ** 2 + (py - cy) ** 2

    deltas = parity_deltas[r_par]  # (S+1, 6, 2)
    nq = q_arr[:, None] + deltas[:, :, 0]  # (S+1, 6)
    nr = r_arr[:, None] + deltas[:, :, 1]  # (S+1, 6)
    nr_par = nr & 1
    nx = hex_width * (nq + 0.5 * nr_par) + hex_width * 0.5
    ny = hex_height * nr + hex_size
    d1 = (px[:, None] - nx) ** 2 + (py[:, None] - ny) ** 2
    edge_hit = np.abs(d1 - d0[:, None]) <= edge_eps_sq  # (S+1, 6)

    return q_arr, r_arr, nq, nr, edge_hit


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

    q_arr, r_arr, nq, nr, edge_hit = _vectorized_fractional_ray_samples(
        ax,
        ay,
        bx,
        by,
        samples,
        _UI_HEX_SIZE,
        _UI_HEX_WIDTH,
        _UI_HEX_HEIGHT,
        _EDGE_EPS_SQ,
        _PARITY_DELTAS_NP,
    )

    segments: list[list[HexCoord]] = []
    for i in range(samples + 1):
        pq = int(q_arr[i])
        pr = int(r_arr[i])
        seg = [HexCoord(pq, pr)]
        for d in range(6):
            if edge_hit[i, d]:
                hq = int(nq[i, d])
                hr = int(nr[i, d])
                if hq != pq or hr != pr:
                    seg.append(HexCoord(hq, hr))
        segments.append(seg)
    return segments


def _trace_ray_geometry_tuples(
    a: HexCoord, b: HexCoord
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    """
    Single-pass vectorized computation of both:
    - `path_full_tuples`: full ray path (including shared edges) as `(q, r)` tuples
    - `inner_tuples`: intermediate spine hexes for LOS evaluation as `(q, r)` tuples
    Cached globally by `(a.q, a.r, b.q, b.r)`.
    """
    geom_key = (a.q, a.r, b.q, b.r)
    cached = _ray_geometry_cache.get(geom_key)
    if cached is not None:
        return cached

    if a.q == b.q and a.r == b.r:
        res = (((a.q, a.r),), ())
        _ray_geometry_cache[geom_key] = res
        return res

    dist = hex_distance(a, b)
    if dist <= 1:
        res = (((a.q, a.r), (b.q, b.r)), ())
        _ray_geometry_cache[geom_key] = res
        return res

    ax, ay = _hex_to_pixel_ui(a.q, a.r)
    bx, by = _hex_to_pixel_ui(b.q, b.r)
    samples = max(dist * 4, dist + 1)

    q_arr, r_arr, nq, nr, edge_hit = _vectorized_fractional_ray_samples(
        ax,
        ay,
        bx,
        by,
        samples,
        _UI_HEX_SIZE,
        _UI_HEX_WIDTH,
        _UI_HEX_HEIGHT,
        _EDGE_EPS_SQ,
        _PARITY_DELTAS_NP,
    )

    start_t = (a.q, a.r)
    end_t = (b.q, b.r)
    path_full: list[tuple[int, int]] = [start_t]
    primary_spine: list[tuple[int, int]] = [start_t]

    for i in range(samples + 1):
        pq = int(q_arr[i])
        pr = int(r_arr[i])
        pt = (pq, pr)
        if primary_spine[-1] != pt:
            primary_spine.append(pt)
        if path_full[-1] != pt:
            path_full.append(pt)
        for d in range(6):
            if edge_hit[i, d]:
                ht = (int(nq[i, d]), int(nr[i, d]))
                if ht != pt and path_full[-1] != ht:
                    path_full.append(ht)

    if path_full[-1] != end_t:
        path_full.append(end_t)
    if primary_spine[-1] != end_t:
        primary_spine.append(end_t)

    inner: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for pt in primary_spine[1:-1]:
        if pt == end_t or pt in seen:
            continue
        seen.add(pt)
        inner.append(pt)

    res = (tuple(path_full), tuple(inner))
    _ray_geometry_cache[geom_key] = res
    return res


def _flatten_ray_path(a: HexCoord, b: HexCoord, segments: list[list[HexCoord]]) -> list[HexCoord]:
    path = [a]
    for seg in segments:
        for h in seg:
            _append_hex_to_path(path, h)
    if path[-1] != b:
        path.append(HexCoord(b.q, b.r))
    return path


def _terrain_los_at(coord: HexCoord | tuple[int, int], game_map, terrain_config) -> str | None:
    q, r = (coord.q, coord.r) if hasattr(coord, "q") else (coord[0], coord[1])
    hex_ = game_map.get_hex(q, r)
    if not hex_:
        return None
    terrain = hex_.get_terrain()
    config = terrain_config.get(terrain)
    return config.get("los", "CLEAR") if config else "CLEAR"


def _get_map_los_lookup(game_map, terrain_config) -> tuple[dict[tuple[int, int], str], int]:
    """
    Precompute and cache a fast (q, r) -> LOS string map for `game_map` + `terrain_config`.
    """
    if game_map is None or not hasattr(game_map, "hexes"):
        return {}, 0
    terrain_sig = (
        game_map.terrain_signature()
        if hasattr(game_map, "terrain_signature")
        else len(game_map.hexes)
    )
    cache_key = (id(terrain_config), terrain_sig)
    cached = getattr(game_map, "_los_terrain_lookup_cache", None)
    if cached is not None and cached[0] == cache_key:
        return cached[1], terrain_sig

    lookup: dict[tuple[int, int], str] = {}
    for h in game_map.hexes:
        terrain = h.get_terrain()
        cfg = terrain_config.get(terrain) if terrain_config else None
        lookup[(h.q, h.r)] = cfg.get("los", "CLEAR") if cfg else "CLEAR"

    game_map._los_terrain_lookup_cache = (cache_key, lookup)
    return lookup, terrain_sig


def _hex_path_ui_pixel(a: HexCoord, b: HexCoord) -> list[HexCoord]:
    """Straight ray; includes both hexes when the line runs along a shared edge."""
    path_full_tuples, _ = _trace_ray_geometry_tuples(a, b)
    return [HexCoord(q, r) for q, r in path_full_tuples]


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
# LOS CORE & PRECOMPUTED VISIBILITY TENSOR (Roadmap 6.1)
# -------------------------------------------------

def precompute_visibility_matrix(game_map, terrain_config) -> tuple[np.ndarray, dict[tuple[int, int], int]]:
    """
    Precompute the static (N, N) uint8 visibility tensor for `game_map`:
      0 = LineOfSight.CLEAR
      1 = LineOfSight.HINDERED
      2 = LineOfSight.BLOCKED
    Cached on `game_map` and invalidated automatically if terrain changes.
    """
    los_lookup, terrain_sig = _get_map_los_lookup(game_map, terrain_config)
    cache_key = (_LOS_CACHE_VERSION, id(terrain_config), terrain_sig)
    cached = getattr(game_map, "_visibility_matrix_cache", None)
    if cached is not None and cached[0] == cache_key:
        return cached[1], cached[2]

    coords_list = [(h.q, h.r) for h in game_map.hexes]
    n = len(coords_list)
    coord_to_idx = {c: idx for idx, c in enumerate(coords_list)}
    vis_matrix = np.zeros((n, n), dtype=np.uint8)

    hex_objs = [HexCoord(q, r) for q, r in coords_list]
    for i in range(n):
        a = hex_objs[i]
        for j in range(i + 1, n):
            b = hex_objs[j]
            _, inner_tuples = _trace_ray_geometry_tuples(a, b)
            hindrance = 0
            blocked = False
            for pt in inner_tuples:
                los_type = los_lookup.get(pt)
                if los_type == "BLOCKED":
                    blocked = True
                    break
                elif los_type == "HINDERED":
                    hindrance += 1
                    if hindrance >= 3:
                        blocked = True
                        break
            code = 2 if blocked else (1 if hindrance >= 1 else 0)
            vis_matrix[i, j] = code
            vis_matrix[j, i] = code

    game_map._visibility_matrix_cache = (cache_key, vis_matrix, coord_to_idx)
    return vis_matrix, coord_to_idx


def check_line_of_sight(attacker, target, game_map, terrain_config):
    start = getattr(attacker, "position", None)
    end = getattr(target, "position", None)

    if start is None or end is None:
        return LineOfSight.BLOCKED

    # Map-bound cache to isolate scenarios and prevent cross-scenario contamination
    los_lookup = None
    terrain_sig = 0
    if game_map is not None:
        cache = getattr(game_map, "_los_cache", None)
        if cache is None:
            cache = {}
            game_map._los_cache = cache
        if hasattr(game_map, "hexes"):
            los_lookup, terrain_sig = _get_map_los_lookup(game_map, terrain_config)
    else:
        cache = _los_cache

    key = _make_key(start, end, terrain_sig)

    if key in cache:
        result, cached_debug = cache[key]
        attacker._los_debug = cached_debug
        return result

    reverse_key = (_LOS_CACHE_VERSION, terrain_sig, end.q, end.r, start.q, start.r)
    if reverse_key in cache:
        result, cached_debug = cache[reverse_key]
        attacker._los_debug = {
            "blocking": cached_debug["blocking"],
            "hindrance": cached_debug["hindrance"],
            "path": list(reversed(cached_debug["path"]))
        }
        return result

    path_full_tuples, inner_tuples = _trace_ray_geometry_tuples(start, end)

    if not path_full_tuples:
        return LineOfSight.BLOCKED

    hindrance = 0
    blocking_hexes = []
    hindrance_hexes = []
    is_blocked = False

    for coord_t in inner_tuples:
        if los_lookup is not None:
            los_type = los_lookup.get(coord_t)
        else:
            los_type = _terrain_los_at(coord_t, game_map, terrain_config)
        if los_type is None:
            continue

        if los_type == "BLOCKED":
            is_blocked = True
            blocking_hexes.append(coord_t)

        elif los_type == "HINDERED":
            hindrance += 1
            hindrance_hexes.append(coord_t)
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
        "path": list(path_full_tuples)
    }
    attacker._los_debug = debug_data

    cache[key] = (result, debug_data)
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