from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.range_attack_profile import RangeAttackProfile
from assault_model.combat.defense_profile import DefenseProfile


class RangedIndirectAttack(CombatAction):
    def __init__(
        self,
        unit_id: str,
        target_hex: tuple[int, int],
        attack_profile: RangeAttackProfile,
        defense_profile: DefenseProfile,
    ):
        super().__init__(unit_id, ActionType.RANGED_ATTACK)
        self.target_hex = target_hex
        self.attack_profile = attack_profile
        self.defense_profile = defense_profile
        self.combat_mode = CombatMode.RANGED_INDIRECT