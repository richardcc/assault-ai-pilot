from assault_model.combat.battle_die import BattleDie
from assault_model.combat.dice_pool import DicePool
from assault_model.combat.combat_action_context import CombatActionContext
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.dice_face import DiceFace


class CombatResolutionResult:
    def __init__(
        self,
        attack_roll: list[DiceFace],
        defense_roll: list[DiceFace],
        criticals: list,
    ):
        self.attack_roll = attack_roll
        self.defense_roll = defense_roll
        self.criticals = criticals


def resolve_critical(face: DiceFace, target_class: UnitClass):
    """
    Resolve a single critical hit against a target class.
    (Lógica existente / placeholder)
    """
    # Aquí va tu lógica real de críticos
    return {
        "face": face,
        "target_class": target_class,
    }


def resolve_combat(
    ctx: CombatActionContext,
    target_class: UnitClass,
) -> CombatResolutionResult:
    attack_pool = DicePool([BattleDie(c) for c in ctx.attack.get_dice(ctx.band)])
    defense_pool = DicePool([BattleDie(c) for c in ctx.defense.dice])

    attack_results = attack_pool.roll()
    defense_results = defense_pool.roll()

    criticals = [
        resolve_critical(face, target_class)
        for face in attack_results
        if face == DiceFace.CRITICAL
    ]

    return CombatResolutionResult(
        attack_roll=attack_results,
        defense_roll=defense_results,
        criticals=criticals,
    )