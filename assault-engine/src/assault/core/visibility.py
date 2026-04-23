"""
Minimal visibility service.

This module provides a minimal Line Of Sight (LOS) interface.
The actual LOS logic can be replaced later without touching
combat or action logic.
"""

from assault.core.unit import Unit
from assault.core.game_state import GameState


class VisibilityService:
    """
    Minimal visibility service.
    """

    def can_see(
        self,
        attacker: Unit,
        defender: Unit,
        state: GameState,
    ) -> bool:
        """
        Returns True if attacker can see defender.

        Minimal implementation:
        - Always returns True
        """
        return True