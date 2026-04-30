# assault_model/map/map_piece.py

from typing import Dict, List, Tuple, Optional

from assault_model.map.hex import Hex
from assault_model.map.hex_state import HexState
from assault_model.map.hex_edge_feature import HexEdgeFeature


class MapPieceDefinition:
    """
    Canonical map piece definition.

    A MapPieceDefinition describes a reusable fragment of the battlefield.

    Characteristics:
    - static
    - immutable
    - reusable across scenarios
    - contains local hex coordinates and base terrain

    A map piece contains NO units and NO execution logic.

    MapPieceDefinition may optionally include:
    - hex_states: dynamic hex overlays (buildings, woods, etc.)
    - hex_edges: edge features between adjacent hexes (walls, hedges, etc.)
    """

    def __init__(
        self,
        piece_id: str,
        description: str,
        hexes: List[Hex],
        hex_states: Optional[Dict[Tuple[int, int], HexState]] = None,
        hex_edges: Optional[
            Dict[Tuple[Tuple[int, int], Tuple[int, int]], HexEdgeFeature]
        ] = None,
    ) -> None:
        self.piece_id = piece_id
        self.description = description
        self.hexes = hexes

        # Optional per-hex dynamic state (indexed by local coordinates)
        self.hex_states: Dict[Tuple[int, int], HexState] = hex_states or {}

        # Optional edge features between pairs of local coordinates
        self.hex_edges: Dict[
            Tuple[Tuple[int, int], Tuple[int, int]], HexEdgeFeature
        ] = hex_edges or {}