"""
Direct Ranged Fire action.
"""

from dataclasses import dataclass
from typing import Optional

from assault.core.unit import Unit
from assault.core.game_state import GameState
from assault.core.visibility import VisibilityService
from assault.core.combat.ranged_fire import (
    RangedFireResolver,
    RangedFireReport,
)


@dataclass
class RangedFireAction:
    """
    Defines a ranged fire action.
    """
    attacker: Unit
    defender: Unit
    max_range: int = 3

    def can_execute(
        self,
        state: GameState,
        visibility: VisibilityService,
    ) -> bool:
        """
        Checks if the ranged attack is allowed.
        """
        if not visibility.can_see(self.attacker, self.defender, state):
            return False

        aq, ar = self.attacker.position
        dq, dr = self.defender.position

        distance = max(abs(aq - dq), abs(ar - dr))
        return distance <= self.max_range