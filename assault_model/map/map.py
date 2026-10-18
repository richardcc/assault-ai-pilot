from typing import Dict, List, Tuple, Optional

from assault_model.map.hex import Hex
from assault_model.map.hex_edge_feature import HexEdgeFeature


class Map:
    """
    Canonical battlefield map.

    A Map is a collection of global hexes.
    It is immutable in terms of geometry during gameplay.

    The Map serves as a registry for hexes and static edge features.
    """

    def __init__(self, hexes: List[Hex]) -> None:
        self.hexes: List[Hex] = hexes

        # Fast lookup by axial coordinates
        self._hex_index: Dict[Tuple[int, int], Hex] = {
            (h.q, h.r): h for h in hexes
        }

        # Static edge features indexed by ordered coordinate pairs
        self.hex_edges: Dict[
            Tuple[Tuple[int, int], Tuple[int, int]],
            HexEdgeFeature,
        ] = {}
        # Optional per-hex fortifications (scenario-driven overlays).
        # Stored as metadata dict, e.g.:
        # {"type":"trench","vertex_start":1,"vertex_end":2}
        # Vertex convention: 1=N and clockwise.
        self.hex_fortifications: Dict[Tuple[int, int], Dict[str, object]] = {}

    # ---------------------------------------------------------
    # Hex retrieval
    # ---------------------------------------------------------

    def get_hex(self, q: int, r: int) -> Optional[Hex]:
        """
        Retrieve a hex by axial coordinate.
        """
        return self._hex_index.get((q, r))

    def get_hex_from_coord(self, coord) -> Optional[Hex]:
        """
        Convenience helper to retrieve a hex using a HexCoord-like object.
        """
        if coord is None:
            return None
        return self.get_hex(coord.q, coord.r)

    def all_hexes(self) -> List[Hex]:
        """
        Return all hexes in the map.
        """
        return self.hexes

    # ---------------------------------------------------------
    # Hex edge feature handling
    # ---------------------------------------------------------

    def add_hex_edge_feature(
        self,
        a: Tuple[int, int],
        b: Tuple[int, int],
        feature: HexEdgeFeature,
    ) -> None:
        """
        Register a feature located on the edge between two adjacent hexes.

        Edge features are stored bidirectionally for convenience.
        """
        self.hex_edges[(a, b)] = feature
        self.hex_edges[(b, a)] = feature

    def get_hex_edge_feature(
        self,
        a: Tuple[int, int],
        b: Tuple[int, int],
    ) -> Optional[HexEdgeFeature]:
        """
        Retrieve the feature located on the edge between two hexes, if any.
        """
        return self.hex_edges.get((a, b))

    # ---------------------------------------------------------
    # Hex fortification handling
    # ---------------------------------------------------------
    def add_hex_fortification(
        self,
        q: int,
        r: int,
        fort_type: str,
        vertex_start: int | None = None,
        vertex_end: int | None = None,
    ) -> None:
        self.hex_fortifications[(q, r)] = {
            "type": fort_type,
            "vertex_start": vertex_start,
            "vertex_end": vertex_end,
        }

    def get_hex_fortification(self, q: int, r: int) -> Optional[str]:
        data = self.hex_fortifications.get((q, r))
        if not data:
            return None
        return data.get("type")  # backward-compatible API

    def get_hex_fortification_data(self, q: int, r: int) -> Optional[Dict[str, object]]:
        return self.hex_fortifications.get((q, r))

    # ---------------------------------------------------------
    # Vectorized Topology & Static Movement Graph (Roadmap 6.1 & 6.2)
    # ---------------------------------------------------------
    def terrain_signature(self) -> int:
        """
        Lightweight structural hash of all hex terrains and fortifications.
        Ensures precomputed LOS/movement tensors automatically invalidate if
        procedural terrain mutation alters the map before a match.
        """
        h = 2166136261
        for hx in self.hexes:
            t_val = getattr(hx.terrain, "value", str(hx.terrain))
            h = ((h ^ hash((hx.q, hx.r, t_val))) * 16777619) & 0xFFFFFFFFFFFFFFFF
        if self.hex_fortifications:
            for k, v in self.hex_fortifications.items():
                h = ((h ^ hash((k, v.get("type")))) * 16777619) & 0xFFFFFFFFFFFFFFFF
        return h

    def get_topology_tensors(self):
        """
        Return cached (adj_indices, coord_to_idx, dist_matrix, coords_list)
        precomputed via vectorized NumPy/Numba helpers.
        """
        cached = getattr(self, "_topology_tensors_cache", None)
        if cached is not None and cached[0] == len(self.hexes):
            return cached[1]
        from assault_model.map.hex_utils import precompute_adjacency_tensors

        coords_list = [(h.q, h.r) for h in self.hexes]
        adj_indices, coord_to_idx, dist_matrix = precompute_adjacency_tensors(coords_list)
        payload = (adj_indices, coord_to_idx, dist_matrix, coords_list)
        self._topology_tensors_cache = (len(self.hexes), payload)
        return payload

    def get_static_movement_graph(self, move_type: str, terrain_cfg=None):
        """
        Precompute and cache for a given `move_type`:
        - `adj_tuples`: dict[(q, r), tuple[(nq, nr, enter_cost), ...]] for all
          enterable neighbors (excluding off-map, WATER, and impassable terrain/fortifications).
        - `adj_enter_costs`: (N, 6) int16 numpy tensor of entry costs (-1 if impassable).
        """
        if terrain_cfg is None:
            from assault_model.map.terrain_config import terrain_config as default_tc
            terrain_cfg = default_tc

        sig = (str(move_type), id(terrain_cfg), self.terrain_signature())
        cache = getattr(self, "_static_move_graph_cache", None)
        if cache is None:
            cache = {}
            self._static_move_graph_cache = cache
        if sig in cache:
            return cache[sig]

        import numpy as np
        from assault_model.map.hex_utils import neighbors as hex_neighbors
        from assault_model.map.terrain import Terrain
        from assault_model.rules.fortification_rules import FortificationRules

        adj_indices, coord_to_idx, _, coords_list = self.get_topology_tensors()
        n = len(coords_list)
        adj_enter_costs = np.full((n, 6), -1, dtype=np.int16)
        adj_tuples: Dict[Tuple[int, int], Tuple[Tuple[int, int, int], ...]] = {}

        # Precompute enter cost of every valid hex on the map for `move_type`
        hex_enter_cost: Dict[Tuple[int, int], Optional[int]] = {}
        for h in self.hexes:
            coord = (h.q, h.r)
            if h.terrain == Terrain.WATER:
                hex_enter_cost[coord] = None
                continue
            base_cost = terrain_cfg.get_move_cost(h.get_terrain(), move_type)
            fort_type = self.get_hex_fortification(h.q, h.r)
            cost = FortificationRules.movement_cost_for_fortification(
                fort_type, move_type, base_cost
            )
            hex_enter_cost[coord] = int(cost) if cost is not None else None

        for idx, coord in enumerate(coords_list):
            valid_neighbors = []
            for d, n_coord in enumerate(hex_neighbors(coord)):
                c = hex_enter_cost.get(n_coord)
                if c is not None:
                    valid_neighbors.append((n_coord[0], n_coord[1], c))
                    adj_enter_costs[idx, d] = c
            adj_tuples[coord] = tuple(valid_neighbors)

        result = (adj_tuples, adj_enter_costs, adj_indices, coord_to_idx, coords_list)
        cache[sig] = result
        return result

    def __deepcopy__(self, memo) -> "Map":
        """
        Map geometry and precomputed topology/LOS caches are shared as a read-only
        singleton across Copy-on-Write MCTS state clones (Roadmap 6.2).
        """
        return self

