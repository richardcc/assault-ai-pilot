# assault_model/combat/ranged_combat_resolver.py

from assault_model.combat.modifiers.terrain_modifier import TerrainModifier
from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.dice_face import DiceFace
from assault_model.map.combat_geometry import determine_attack_sector
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.dice_comparison import compare_dice

# ✅ NUEVO (SIN ROMPER NADA)
from assault_model.combat.line_of_sight import (
    check_line_of_sight,
    LineOfSight,
)

from assault_model.combat.morale import (
    apply_suppression_hits,
    resolve_fallback,
)

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

    # =================================================
    # CONTEXT
    # =================================================
    game_map = context.game_map if context and context.game_map else None

    # =================================================
    # LINE OF SIGHT
    # =================================================
    los = LineOfSight.CLEAR

    if game_map:
        los = check_line_of_sight(attacker, target, game_map)

    _trace(
        "LOS_CHECK",
        attacker=attacker.unit_id,
        defender=target.unit_id,
        los=los.name,
    )

    if los == LineOfSight.BLOCKED:
        _trace(
            "RANGED_BLOCKED",
            attacker=attacker.unit_id,
            defender=target.unit_id,
        )
        return CombatResolutionResult([], [], [])

    # ---------------- ATTACK DICE ----------------
    attack_colors = list(
        attacker.unit_type.get_attack_dice(
            distance=distance,
            target_category=target.unit_type.category,
        )
    )

    # ---------------- SUPPRESSION (ATTACKER PENALTY) ----------------
    if getattr(attacker, "suppressed", False):
        if attack_colors:
            attack_colors = attack_colors[:-1]
            _trace(
                "SUPPRESSION_ATTACK_PENALTY",
                attacker=attacker.unit_id,
                remaining_dice=len(attack_colors),
            )

    # ---------------- PARTIAL LOS PENALTY ----------------
    if los == LineOfSight.PARTIAL and attack_colors:
        attack_colors = attack_colors[:-1]

    attack_pool = AttackDicePool(attack_colors)
    attack_results: list[DiceResult] = attack_pool.roll()

    # ---------------- ATTACK SECTOR ----------------
    attack_sector = determine_attack_sector(
        attacker_pos=attacker.position,
        defender_pos=target.position,
        defender_facing=getattr(target, "facing", "N"),
    )

    # ---------------- DEFENSE DICE ----------------
    defense_colors = list(
        target.unit_type.get_defense_dice(sector=attack_sector)
    )

    if game_map:
        hex_ = game_map.get_hex(target.position)
        if hex_ is not None:
            terrain_mod = TerrainModifier.from_hex(hex_)
            defense_colors = terrain_mod.modify_defense(defense_colors)

            _trace(
                "TERRAIN_APPLIED",
                defender=target.unit_id,
                hex=target.position,
                defense_dice=len(defense_colors),
            )

    defense_pool = DefenseDicePool(defense_colors)
    defense_results: list[DiceResult] = defense_pool.roll()

    # ---------------- DICE COMPARISON ----------------
    comparison = compare_dice(
        attacker_dice=attack_results,
        defender_dice=defense_results,
    )

    remaining_damage = comparison["remaining_damage"]
    remaining_criticals = comparison["remaining_criticals"]
    remaining_suppress = comparison["remaining_suppress"]

    # ---------------- CRITICALS ----------------
    criticals = [
        resolve_critical(
            DiceFace.CRITICAL,
            UnitClass[target.unit_type.category.value],
        )
        for _ in range(remaining_criticals)
    ]

    # ---------------- DAMAGE ----------------
    damage = remaining_damage + remaining_criticals

    hp_before = target.hp
    if damage > 0:
        target.apply_damage(damage)
    hp_after = target.hp

    defender_killed = hp_before > 0 and hp_after == 0

    # ---------------- SUPPRESSION (CORRECTO) ----------------
    if remaining_suppress > 0 and target.alive:

        suppressed_before = target.is_suppressed()
        fallback_before = target.is_in_fallback()

        apply_suppression_hits(target, remaining_suppress)
        resolve_fallback(target)

        _trace(
            "SUPPRESSION_RESOLVED",
            unit=target.unit_id,
            hits=remaining_suppress,
            suppressed_before=suppressed_before,
            fallback_before=fallback_before,
            suppressed_after=target.is_suppressed(),
            fallback_after=target.is_in_fallback(),
        )

    # ---------------- RESULT ----------------
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
                    "los": los.name,

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

                    # ============================
                    # EFFECTS (CORREGIDO)
                    # ============================
                    "attacker_effects": {
                        "damage": damage,
                        "criticals": criticals,

                        # legacy
                        "suppress": remaining_suppress,

                        # nuevos
                        "suppress_attempts": remaining_suppress,
                        "suppression_applied": remaining_suppress > 0,
                        "suppression_state_after": target.is_suppressed(),
                        "fallback_triggered": target.is_in_fallback(),
                    },

                    "suppression": {
                        "attempts": remaining_suppress,
                        "applied": remaining_suppress > 0,
                        "state": target.is_suppressed(),
                        "fallback": target.is_in_fallback(),
                    },

                    "defender_hp_before": hp_before,
                    "defender_hp_after": hp_after,
                    "defender_killed": defender_killed,

                    "defender_suppressed": target.is_suppressed(),
                    "defender_fallback": target.is_in_fallback(),

                    # ✅ CLAVE PARA REPLAY
                    "defender_position_after": target.position,

                    "resolution": comparison,
                    "outcome": "resolved",
                    "winner": None,
                },
            }
        )

    return result