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


# =====================================================================
# VECTORIZED NUMPY / NUMBA HEX TOPOLOGY & PATHFINDER KERNELS (Roadmap 6.1)
# =====================================================================

import heapq
import numpy as np

try:
    from numba import njit as _numba_njit  # type: ignore

    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

    def _numba_njit(*args, **kwargs):
        def _decorator(fn):
            return fn

        if len(args) == 1 and callable(args[0]):
            return args[0]
        return _decorator


_EVEN_R_DELTAS_NP = np.array(
    [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [-1, 1]], dtype=np.int32
)
_ODD_R_DELTAS_NP = np.array(
    [[-1, 0], [1, 0], [0, -1], [0, 1], [1, -1], [1, 1]], dtype=np.int32
)
_PARITY_DELTAS_NP = np.stack([_EVEN_R_DELTAS_NP, _ODD_R_DELTAS_NP], axis=0)  # (2, 6, 2)


def hex_distance_batch(coords_a: np.ndarray, coords_b: np.ndarray) -> np.ndarray:
    """
    Vectorized pairwise hex distance matrix for odd-r offset coordinates.

    Parameters:
    - coords_a: (N, 2) integer array of (q, r)
    - coords_b: (M, 2) integer array of (q, r)

    Returns:
    - dist_matrix: (N, M) int16 array of exact hexagonal distances.
    """
    a = np.asarray(coords_a, dtype=np.int32)
    b = np.asarray(coords_b, dtype=np.int32)
    if a.ndim == 1:
        a = a[None, :]
    if b.ndim == 1:
        b = b[None, :]

    aq = a[:, 0] - ((a[:, 1] - (a[:, 1] & 1)) // 2)
    ar = a[:, 1]
    bq = b[:, 0] - ((b[:, 1] - (b[:, 1] & 1)) // 2)
    br = b[:, 1]

    dq = np.abs(aq[:, None] - bq[None, :])
    dr = np.abs(ar[:, None] - br[None, :])
    ds = np.abs((aq + ar)[:, None] - (bq + br)[None, :])
    return np.maximum(np.maximum(dq, dr), ds).astype(np.int16)


def precompute_adjacency_tensors(
    hex_coords: list[Tuple[int, int]],
) -> Tuple[np.ndarray, dict[Tuple[int, int], int], np.ndarray]:
    """
    Precompute static tensorial adjacency matrix and pairwise distance matrix
    for a list of map coordinates (q, r).

    Returns:
    - adj_indices: (N, 6) int32 tensor where adj_indices[i, d] is the index of
      the d-th neighbor of hex i, or -1 if off-map.
    - coord_to_idx: dict mapping (q, r) -> int index in [0, N).
    - dist_matrix: (N, N) int16 tensor of pairwise hex distances.
    """
    n = len(hex_coords)
    coord_to_idx = {c: idx for idx, c in enumerate(hex_coords)}
    if n == 0:
        return (
            np.empty((0, 6), dtype=np.int32),
            coord_to_idx,
            np.empty((0, 0), dtype=np.int16),
        )

    coords_np = np.asarray(hex_coords, dtype=np.int32)
    parities = coords_np[:, 1] & 1  # (N,)
    deltas = _PARITY_DELTAS_NP[parities]  # (N, 6, 2)
    neighbor_coords = coords_np[:, None, :] + deltas  # (N, 6, 2)

    adj_indices = np.full((n, 6), -1, dtype=np.int32)
    for i in range(n):
        for d in range(6):
            nq = int(neighbor_coords[i, d, 0])
            nr = int(neighbor_coords[i, d, 1])
            adj_indices[i, d] = coord_to_idx.get((nq, nr), -1)

    dist_matrix = hex_distance_batch(coords_np, coords_np)
    return adj_indices, coord_to_idx, dist_matrix


@_numba_njit(cache=True)
def vectorized_kinematic_dijkstra(
    adj_indices: np.ndarray,
    adj_enter_costs: np.ndarray,
    start_idx: int,
    max_mp: int,
    impassable_mask: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compiled / vectorized kinematic Dijkstra over precomputed integer adjacency tensors.

    Parameters:
    - adj_indices: (N, 6) int32 neighbor indices (-1 if off-map)
    - adj_enter_costs: (N, 6) int16 movement cost to enter neighbor (-1 if impassable)
    - start_idx: origin hex index
    - max_mp: movement allowance
    - impassable_mask: (N,) bool array (True if hex cannot be traversed, e.g. enemy/vehicle)

    Returns:
    - best_cost: (N,) int32 array (999999 if unreachable)
    - came_from: (N,) int32 parent index (-1 for root/unreachable)
    """
    n = adj_indices.shape[0]
    inf = 999999
    best_cost = np.full(n, inf, dtype=np.int32)
    came_from = np.full(n, -1, dtype=np.int32)
    if start_idx < 0 or start_idx >= n or max_mp <= 0:
        return best_cost, came_from

    best_cost[start_idx] = 0
    frontier = [(np.int64(0), np.int64(start_idx))]

    while frontier:
        cost, u = heapq.heappop(frontier)
        if cost > best_cost[u]:
            continue
        for d in range(6):
            v = np.int64(adj_indices[u, d])
            if v < 0:
                continue
            step_cost = int(adj_enter_costs[u, d])
            if step_cost < 0:
                continue
            new_cost = np.int64(cost + step_cost)
            if new_cost > max_mp:
                continue
            if impassable_mask[v]:
                continue
            if new_cost < best_cost[v]:
                best_cost[v] = new_cost
                came_from[v] = u
                heapq.heappush(frontier, (new_cost, v))

    return best_cost, came_from

