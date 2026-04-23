"""
Direct Ranged Fire execution on the map.
"""

from assault.core.game_state import GameState
from assault.core.unit import Unit
from assault.core.actions.ranged_fire_action import RangedFireAction
from assault.core.combat.ranged_fire import RangedFireResolver
from assault.core.unit import UnitStatus


class RangedFireExecutor:
    """
    Executes ranged fire and applies effects to the GameState.
    """

    def __init__(
        self,
        state: GameState,
        resolver: RangedFireResolver,
    ) -> None:
        self.state = state
        self.resolver = resolver

    def execute(self, action: RangedFireAction) -> None:
        report = self.resolver.resolve(action.attacker)

        # Apply damage
        if report.hits > 0:
            action.defender.apply_damage(report.hits)

        # Apply suppression
        if report.suppressions > 0 and action.defender.is_alive():
            action.defender.statuses.add(UnitStatus.SUPPRESSED)