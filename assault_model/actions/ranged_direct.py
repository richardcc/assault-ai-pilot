from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class RangedDirectAttack(CombatAction):
    """
    Declares a direct ranged attack action.
    """

    def __init__(
        self,
        unit_id: str,
        target_id: str,
    ):
        super().__init__(unit_id, ActionType.RANGED_DIRECT)

        self.target_id = target_id
        self.combat_mode = CombatMode.RANGED_DIRECT

        self.action_id = f"RANGED_DIRECT:{unit_id}:{target_id}"

    def __repr__(self) -> str:
        return (
            f"RangedDirectAttack("
            f"unit_id={self.unit_id}, "
            f"target_id={self.target_id}"
            f")"
        )
