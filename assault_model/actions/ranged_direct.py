from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class RangedDirectAttack(CombatAction):
    """
    Declares a direct ranged attack action.

    Design:
    - ActionType defines the decision (RANGED_DIRECT).
    - combat_mode is used internally by the engine.
    - No attack_mode: decision belongs to RL, not inside the action.
    """

    def __init__(
        self,
        unit_id: str,
        target_id: str,
    ):
        # ✅ CLAVE: acción diferenciada
        super().__init__(unit_id, ActionType.RANGED_DIRECT)

        # ✅ Target unit
        self.target_id = target_id

        # ✅ Engine semantic
        self.combat_mode = CombatMode.RANGED_DIRECT

    def __repr__(self) -> str:
        return (
            f"RangedDirectAttack("
            f"unit_id={self.unit_id}, "
            f"target_id={self.target_id}"
            f")"
        )