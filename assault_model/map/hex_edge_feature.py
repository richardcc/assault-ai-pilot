# assault_model/map/hex_edge_feature.py

from enum import Enum


class HexEdgeFeature(Enum):
    """
    Feature located on the edge between two adjacent hexes.

    HexEdgeFeature represents static, physical elements that exist
    between hexes rather than inside a hex itself.

    These features do NOT implement any game rules.
    Their effects are interpreted by movement or combat resolvers
    depending on the context.
    """

    WALL = "wall"