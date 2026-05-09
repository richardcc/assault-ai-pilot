# assault_model/combat/ranged_combat_resolver.py
#
# Ranged combat resolver.
#
# RESPONSIBILITY:
# - Resolve direct ranged combat
# - Roll dice
# - Apply damage and suppression (Rulebook 10.7.2 / 10.7.3)
# - Emit ACTION_EFFECT
#
# IMPORTANT:
# - Mutates unit HP via target.apply_damage(...)
# - Mutates unit morale via target.apply_suppression(...)
# - RuntimeGameState must NOT apply damage

from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.dice_face import DiceFace
from assault_model.map.combat_geometry import determine_attack_sector
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.dice_comparison import compare_dice

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# =================================================
# Result container (internal)
# =================================================
class CombatResolutionResult:
    def __init__(self, attack_roll, defense_roll, criticals):
        self.attack_roll = attack_roll
        self.defense_roll = defense_roll
        self.criticals = criticals


# =================================================
# Primary critical registration (10.7.3)
# =================================================
def resolve_critical(face: DiceFace, target_class: UnitClass):
    """
    Primary critical registration only.
    Secondary effects (10.7.5 / 10.7.6) handled later.
    """
    return {
        "face": face.name,
        "target_class": target_class.name,
    }


# =================================================
# Resolver
# =================================================
def resolve_ranged_combat(
    *,
    attacker,
    target,
    distance: int,
    context: ExecutionContext | None = None,
) -> CombatResolutionResult:
    """
    Ranged combat resolver.

    Implements:
    - 10.7.2 Dice comparison
    - 10.7.3 Assigning damage & suppression

    ASSUMES:
    - Dice pools return DiceResult only
    """

    # ---------------- ATTACK DICE ----------------
    attack_colors = attacker.unit_type.get_attack_dice(
        distance=distance,
        target_category=target.unit_type.category,
    )

    attack_pool = AttackDicePool(attack_colors)
    attack_results: list[DiceResult] = attack_pool.roll()

    # ---------------- ATTACK SECTOR ----------------
    attack_sector = determine_attack_sector(
        attacker_pos=attacker.position,
        defender_pos=target.position,
        defender_facing=getattr(target, "facing", "N"),
    )

    # ---------------- DEFENSE DICE ----------------
    defense_colors = target.unit_type.get_defense_dice(
        sector=attack_sector
    )

    defense_pool = DefenseDicePool(defense_colors)
    defense_results: list[DiceResult] = defense_pool.roll()

    # ---------------- DICE COMPARISON (10.7.2) ----------------
    comparison = compare_dice(
        attacker_dice=attack_results,
        defender_dice=defense_results,
    )

    remaining_damage = comparison["remaining_damage"]
    remaining_criticals = comparison["remaining_criticals"]
    remaining_suppress = comparison["remaining_suppress"]

    # ---------------- PRIMARY CRITICAL REGISTRATION ----------------
    criticals = [
        resolve_critical(
            DiceFace.CRITICAL,
            UnitClass[target.unit_type.category.value],
        )
        for _ in range(remaining_criticals)
    ]

    # ---------------- DAMAGE APPLICATION (10.7.3) ----------------
    damage = remaining_damage + remaining_criticals

    hp_before = target.hp
    if damage > 0:
        target.apply_damage(damage)
    hp_after = target.hp

    defender_killed = hp_before > 0 and hp_after == 0

    # ---------------- SUPPRESSION (10.7.3) ----------------
    suppressed = False
    if remaining_suppress > 0 and target.alive:
        target.apply_suppression()
        suppressed = True

    _trace(
        "RANGED_RESOLUTION",
        attacker=attacker.unit_id,
        defender=target.unit_id,
        damage=damage,
        remaining_damage=remaining_damage,
        remaining_criticals=remaining_criticals,
        remaining_suppress=remaining_suppress,
        hp_before=hp_before,
        hp_after=hp_after,
        defender_killed=defender_killed,
        suppressed=suppressed,
    )

    result = CombatResolutionResult(
        attack_roll=attack_results,
        defense_roll=defense_results,
        criticals=criticals,
    )

    # ---------------- EMIT ACTION_EFFECT ----------------
    if context and context.event_bus:
        context.event_bus.emit(
            {
                "type": "ACTION_EFFECT",
                "payload": {
                    "action": "RangedCombat",
                    "attacker": attacker.unit_id,
                    "defender": target.unit_id,
                    "distance": distance,
                    "attack_sector": attack_sector.name,

                    "attacker_attack_dice": [
                        {
                            "color": d.color.name,
                            "faces": [f.name for f in d.faces],
                        }
                        for d in attack_results
                    ],
                    "defender_defense_dice": [
                        {
                            "color": d.color.name,
                            "faces": [f.name for f in d.faces],
                        }
                        for d in defense_results
                    ],

                    "attacker_effects": {
                        "damage": damage,
                        "criticals": criticals,
                        "suppress": remaining_suppress,
                    },

                    "defender_hp_before": hp_before,
                    "defender_hp_after": hp_after,
                    "defender_killed": defender_killed,
                    "defender_suppressed": suppressed,

                    # Extra traceability (non-breaking)
                    "resolution": comparison,

                    "outcome": "resolved",
                    "winner": None,
                },
            }
        )

    return result