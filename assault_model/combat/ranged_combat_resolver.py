# assault_model/combat/ranged_combat_resolver.py
#
# Ranged combat resolver.
#
# RESPONSIBILITY:
# - Resolve direct ranged combat
# - Roll dice
# - Apply damage (same pattern as close combat)
# - Emit ACTION_EFFECT
#
# IMPORTANT:
# - Mutates unit HP via target.apply_damage(...)
# - RuntimeGameState must NOT apply damage

from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.dice_face import DiceFace
from assault_model.combat.attack_sector import AttackSector
from assault_model.map.combat_geometry import determine_attack_sector
from assault_model.runtime.execution_context import ExecutionContext

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
# Critical resolution
# =================================================
def resolve_critical(face: DiceFace, target_class: UnitClass):
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

    SAME mutation and dice contract as close combat.
    Damage is applied HERE via target.apply_damage(...).
    """

    # ---------------- ATTACK DICE ----------------
    attack_colors = attacker.unit_type.get_attack_dice(
        distance=distance,
        target_category=target.unit_type.category,
    )

    attack_pool = AttackDicePool(attack_colors)
    attack_results = attack_pool.roll()      # [(color, face)]

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
    defense_results = defense_pool.roll()    # [(color, face)]

    # ---------------- CRITICALS ----------------
    criticals = [
        resolve_critical(face, UnitClass[target.unit_type.category.value])
        for _, face in attack_results
        if face == DiceFace.CRITICAL
    ]

    # ---------------- DAMAGE ----------------
    hits = sum(
        1 for _, face in attack_results
        if face in (DiceFace.DAMAGE, DiceFace.CRITICAL)
    )

    blocks = sum(
        1 for _, face in defense_results
        if face == DiceFace.DAMAGE
    )

    damage = max(0, hits - blocks)

    hp_before = target.hp
    if damage > 0:
        target.apply_damage(damage)
    hp_after = target.hp

    defender_killed = hp_before > 0 and hp_after == 0

    _trace(
        "RANGED_DAMAGE",
        attacker=attacker.unit_id,
        defender=target.unit_id,
        hits=hits,
        blocks=blocks,
        damage=damage,
        hp_before=hp_before,
        hp_after=hp_after,
        defender_killed=defender_killed,
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
                        (color.name, face.name)
                        for color, face in attack_results
                    ],
                    "defender_defense_dice": [
                        (color.name, face.name)
                        for color, face in defense_results
                    ],

                    "attacker_effects": {
                        "criticals": criticals,
                        "damage": damage,
                    },

                    "defender_hp_before": hp_before,
                    "defender_hp_after": hp_after,
                    "defender_killed": defender_killed,

                    "outcome": "resolved",
                    "winner": None,
                },
            }
        )

    return result