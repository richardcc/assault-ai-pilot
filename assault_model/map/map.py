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
