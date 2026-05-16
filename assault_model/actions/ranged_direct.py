from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class RangedDirectAttack(CombatAction):
    """
    Declares a ranged attack action.

    Combat resolution (dice, range bands, traits, etc.)
    is handled later by the combat resolver.

    Design:
    - Action type stays the same (RANGED_ATTACK).
    - combat_mode indicates the general category (direct ranged).
    - attack_mode indicates how the attack is executed
      (DIRECT_FIRE vs INDIRECT_FIRE).
    """

    def __init__(
        self,
        unit_id: str,
        target_id: str,
        attack_mode: str = "DIRECT_FIRE",
    ):
        # ✅ Base action type (do not change)
        super().__init__(unit_id, ActionType.RANGED_ATTACK)

        # ✅ Target unit
        self.target_id = target_id

        # ✅ Existing system (kept for compatibility)
        self.combat_mode = CombatMode.RANGED_DIRECT

        # ✅ NEW: execution mode (used by resolver + renderer)
        self.attack_mode = attack_mode

    def __repr__(self) -> str:
        return (
            f"RangedDirectAttack("
            f"unit_id={self.unit_id}, "
            f"target_id={self.target_id}, "
            f"attack_mode={self.attack_mode}"
            f")"
        )