# assault_model/map/hex_state.py

from assault_model.map.hex import Hex
from assault_model.map.hex_ownership import HexOwnership


class HexState:
    """
    Dynamic state associated with a single hex.

    HexState represents mutable, scenario-dependent information that cannot
    be encoded as base terrain. This includes ownership, contest status,
    and terrain overlays that affect movement or combat resolution.

    HexState does NOT contain game rules or logic.
    It only stores factual state queried by resolvers.
    """

    def __init__(self, hex_: Hex):
        """
        Create a dynamic state container for a hex.

        Args:
            hex_ (Hex): The hex this state belongs to.
        """
        self.hex = hex_

        # Current ownership status of the hex (if applicable)
        self.ownership: HexOwnership = HexOwnership.NONE

        # Indicates whether the hex is currently contested by multiple sides
        self.contested: bool = False

        # --- Terrain overlay flags (optional, scenario-defined) ---
        # These are intentionally simple boolean markers.
        # Their interpretation is handled by game resolvers.

        # True if the hex contains a building suitable for defensive bonus
        self.building: bool = False

        # True if the hex contains woods or dense vegetation affecting combat
        self.woods: bool = False