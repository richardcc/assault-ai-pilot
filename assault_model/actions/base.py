from abc import ABC
from assault_model.actions.action import Action
from assault_model.combat.range_attack_profile import RangeAttackProfile
from assault_model.combat.defense_profile import DefenseProfile


class MovementAction(Action, ABC):
    pass


class CombatAction(Action, ABC):
    attack_profile: RangeAttackProfile
    defense_profile: DefenseProfile