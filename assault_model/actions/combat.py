# Combat actions

# assault_model/actions/combat.py
from assault_model.actions.action import Action
from assault_model.actions.action_type import ActionType


class RangedAttackAction(Action):
    def __init__(self, unit_id: str, target_id: str):
        super().__init__(
            unit_id,
            ActionType.RANGED_ATTACK,
            payload={"target_id": target_id},
        )


class CloseCombatAction(Action):
    def __init__(self, unit_id: str, target_id: str):
        super().__init__(
            unit_id,
            ActionType.CLOSE_COMBAT,
            payload={"target_id": target_id},
        )
