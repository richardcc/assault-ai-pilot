"""
Reaction / Opportunity Fire system.

This module triggers Direct Ranged Fire (DRF) as a reaction
to enemy actions such as movement, retreat, or advance.

Reaction fire is NOT a standalone attack type.
It reuses Direct Ranged Fire mechanics and execution.
"""

from assault.core.game_state import GameState
from assault.core.unit import Unit
from assault.core.visibility import VisibilityService
from assault.core.actions.ranged_fire_action import RangedFireAction
from assault.core.actions.ranged_fire_executor import RangedFireExecutor
from assault.core.combat.ranged_fire import RangedFireResolver
from assault.core.spatial.zone_of_control import ZoneOfControlService


class ReactionFireTrigger:
    """
    Handles reaction (opportunity) fire caused by enemy actions.

    Reaction fire is triggered only when the triggering unit
    is inside an enemy Zone of Control (ZOC).
    """

    def __init__(
        self,
        state: GameState,
        visibility: VisibilityService,
        resolver: RangedFireResolver,
    ) -> None:
        self.state = state
        self.visibility = visibility
        self.executor = RangedFireExecutor(state, resolver)
        self.zoc = ZoneOfControlService(state)

    def find_reacting_units(self, triggering_unit: Unit):
        """
        Returns units that may react to the triggering unit.
        """
        return [
            unit
            for unit in self.state.units.values()
            if unit.is_alive()
            and unit.unit_id != triggering_unit.unit_id
        ]

    def trigger_reaction_fire(self, triggering_unit: Unit) -> None:
        """
        Triggers reaction fire against the given unit.

        Reaction fire only occurs if the unit is inside
        an enemy Zone of Control.
        """

        # ✅ ZOC GATE: no ZOC, no reaction fire
        if not self.zoc.is_hex_in_enemy_zoc(
            triggering_unit,
            triggering_unit.position,
        ):
            return

        for reacting_unit in self.find_reacting_units(triggering_unit):

            action = RangedFireAction(
                attacker=reacting_unit,
                defender=triggering_unit,
                max_range=3,
            )

            if action.can_execute(self.state, self.visibility):
                self.executor.execute(action)