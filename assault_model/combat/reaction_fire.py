# assault_model/actions/reaction_fire.py
from assault_model.actions.base import CombatAction
from assault_model.actions.action_type import ActionType
from assault_model.combat.range_attack_profile import RangeAttackProfile
from assault_model.combat.defense_profile import DefenseProfile
from assault_model.combat.combat_mode import CombatMode
from assault_model.combat.reaction_condition import ReactionCondition


class ReactionFireAction(CombatAction):
    def __init__(
        self,
        unit_id: str,
        target_id: str,
        attack_profile: RangeAttackProfile,
        defense_profile: DefenseProfile,
        condition: ReactionCondition,
    ):
        super().__init__(unit_id, ActionType.RANGED_ATTACK)
        self.target_id = target_id
        self.attack_profile = attack_profile
        self.defense_profile = defense_profile
        self.condition = condition
        self.combat_mode = CombatMode.RANGED_DIRECT