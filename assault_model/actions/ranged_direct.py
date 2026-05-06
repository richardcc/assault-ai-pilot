from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class RangedDirectAttack(CombatAction):
    """
    Declares a direct ranged attack.

    All combat details (dice, range bands, defense, traits)
    are resolved later by the ranged combat resolver
    using the unit cards and game state.
    """

    def __init__(self, unit_id: str, target_id: str):
        super().__init__(unit_id, ActionType.RANGED_ATTACK)
        self.target_id = target_id
        self.combat_mode = CombatMode.RANGED_DIRECT