# assault_model/map/map.py

from typing import Dict, List, Tuple, Optional

from assault_model.map.hex import Hex
from assault_model.map.hex_state import HexState
from assault_model.map.hex_edge_feature import HexEdgeFeature


class Map:
    """
    Canonical battlefield map.

    A Map is a collection of global hexes.
    It is immutable in terms of geometry during gameplay.

    The Map also serves as a registry for dynamic hex state
    and static edge features that are queried by game resolvers.
    """

    def __init__(self, hexes: List[Hex]) -> None:
        self.hexes: List[Hex] = hexes

        # Fast lookup by axial coordinates
        self._hex_index: Dict[Tuple[int, int], Hex] = {
            (h.q, h.r): h for h in hexes
        }

        # Dynamic per-hex state indexed by global coordinates
        self.hex_states: Dict[Tuple[int, int], HexState] = {}

        # Static edge features indexed by ordered coordinate pairs
        self.hex_edges: Dict[
            Tuple[Tuple[int, int], Tuple[int, int]],
            HexEdgeFeature,
        ] = {}

    def get_hex(self, q: int, r: int) -> Optional[Hex]:
        """
        Retrieve a hex by axial coordinate.
        """
        return self._hex_index.get((q, r))

    def all_hexes(self) -> List[Hex]:
        """
        Return all hexes in the map.
        """
        return self.hexes

    # ---------------------------------------------------------
    # Hex state handling
    # ---------------------------------------------------------

    def set_hex_state(self, q: int, r: int, state: HexState) -> None:
        """
        Associate a HexState with a global hex coordinate.

        This method does not apply any game rules.
        """
        self.hex_states[(q, r)] = state

    def get_hex_state(self, q: int, r: int) -> Optional[HexState]:
        """
        Retrieve the HexState associated with a hex, if any.
        """
        return self.hex_states.get((q, r))

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