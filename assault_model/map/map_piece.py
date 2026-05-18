from typing import Dict, List, Tuple, Optional

from assault_model.map.hex import Hex
from assault_model.map.hex_edge_feature import HexEdgeFeature


class MapPieceDefinition:
    """
    Canonical map piece definition.

    A MapPieceDefinition describes a reusable fragment of the battlefield.

    Characteristics:
    - static
    - immutable
    - reusable across scenarios
    - defines a shape + terrain exceptions

    A map piece contains NO units and NO execution logic.

    MapPieceDefinition includes:
    - shape: (width, height)
    - hexes: full generated hex list (after loader expands sparse data)
    - hex_edges: edge features (walls, hedges, etc.)
    """

    def __init__(
        self,
        piece_id: str,
        description: str,
        shape: Tuple[int, int],   # ✅ NEW
        hexes: List[Hex],
        hex_edges: Optional[
            Dict[Tuple[Tuple[int, int], Tuple[int, int]], HexEdgeFeature]
        ] = None,
    ) -> None:
        self.piece_id = piece_id
        self.description = description

        # ✅ shape explicitly stored
        self.shape = shape

        # ✅ already expanded grid
        self.hexes = hexes

        # ✅ edge features
        self.hex_edges: Dict[
            Tuple[Tuple[int, int], Tuple[int, int]], HexEdgeFeature
        ] = hex_edges or {}
