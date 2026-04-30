from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.range_attack_profile import RangeAttackProfile
from assault_model.combat.defense_profile import DefenseProfile
from assault_model.combat.range_band import RangeBand
from assault_model.combat.dice_face import DiceFace


class CombatResolutionResult:
    def __init__(
        self,
        attack_pool: AttackDicePool,
        defense_pool: DefenseDicePool,
        attack_results: list[DiceFace],
        defense_results: list[DiceFace],
    ):
        self.attack_pool = attack_pool
        self.defense_pool = defense_pool
        self.attack_results = attack_results
        self.defense_results = defense_results


def resolve_combat(
    attack_profile: RangeAttackProfile,
    defense_profile: DefenseProfile,
    band: RangeBand,
) -> CombatResolutionResult:

    attack_pool = AttackDicePool(attack_profile.dice_for_range(band))
    defense_pool = DefenseDicePool(defense_profile.dice_pool())

    attack_results = attack_pool.roll()
    defense_results = defense_pool.roll()

    return CombatResolutionResult(
        attack_pool=attack_pool,
        defense_pool=defense_pool,
        attack_results=attack_results,
        defense_results=defense_results,
    )
