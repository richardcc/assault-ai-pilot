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
    *,
    attacker_id: str | None = None,
    defender_id: str | None = None,
    event_bus=None,
) -> CombatResolutionResult:
    """
    Resolve ranged combat (used by ranged fire and reaction fire).

    Emits ACTION_EFFECT if event_bus is provided,
    using the same pattern as MoveAction.
    """

    attack_pool = AttackDicePool(attack_profile.dice_for_range(band))
    defense_pool = DefenseDicePool(defense_profile.dice_pool())

    attack_results = attack_pool.roll()
    defense_results = defense_pool.roll()

    result = CombatResolutionResult(
        attack_pool=attack_pool,
        defense_pool=defense_pool,
        attack_results=attack_results,
        defense_results=defense_results,
    )

    # -------------------------------------------------
    # ✅ EMIT COMBAT AS ACTION_EFFECT (FLAT, OBSERVABLE)
    # -------------------------------------------------
    if event_bus and attacker_id and defender_id:
        event_bus.emit(
            {
                "type": "ACTION_EFFECT",
                "payload": {
                    "action": "RangedFire",
                    "attacker": attacker_id,
                    "defender": defender_id,
                    "range_band": band.name,
                    "attack_dice": [d.name for d in attack_results],
                    "defense_dice": [d.name for d in defense_results],
                },
            }
        )

    return result