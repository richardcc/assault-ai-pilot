from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode


class RangedIndirectAttack(CombatAction):
    """
    Declares an indirect ranged attack (mortar, artillery, etc.)

    Design:
    - ActionType represents the decision (RANGED_INDIRECT)
    - Engine resolver uses unit stats from unit_type
    """

    def __init__(self, unit_id: str, target_hex: tuple[int, int]):

        # ✅ acción separada (clave para RL)
        super().__init__(unit_id, ActionType.RANGED_INDIRECT)

        # ✅ target es HEX (no unidad)
        self.target_hex = target_hex

        # ✅ metadata para resolver
        self.combat_mode = CombatMode.RANGED_INDIRECT

    def __repr__(self) -> str:
        return (
            f"RangedIndirectAttack("
            f"unit_id={self.unit_id}, "
            f"target_hex={self.target_hex}"
            f")"
        )
