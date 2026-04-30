from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class AssaultAction(CombatAction):
    """
    Declare a close-combat (assault) action.
    Combat profiles are resolved later by combat_resolution.
    """

    def __init__(self, unit_id: str, target_id: str):
        super().__init__(unit_id, ActionType.CLOSE_COMBAT)
        self.target_id = target_id
        self.combat_mode = CombatMode.ASSAULT