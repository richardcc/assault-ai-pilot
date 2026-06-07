from assault_model.combat.modifiers.terrain_modifier import TerrainModifier
from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace
from assault_model.map.combat_geometry import determine_attack_sector
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.dice_comparison import compare_dice
from assault_model.map.terrain_config import terrain_config
from assault_model.rules.fortification_rules import FortificationRules

from assault_model.actions.combat_mode import CombatMode

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


class CombatResolutionResult:
    def __init__(self, attack_roll, defense_roll, criticals):
        self.attack_roll = attack_roll
        self.defense_roll = defense_roll
        self.criticals = criticals


def resolve_critical(face: DiceFace, target_class: UnitClass):
    return {
        "face": face.name,
        "target_class": target_class.name,
    }


def resolve_ranged_combat(
    *,
    action,
    attacker,
    target,
    distance: int,
    context: ExecutionContext | None = None,
) -> CombatResolutionResult:

    game_map = context.game_map if context and context.game_map else None
    terrain_cfg = context.terrain_config if context and hasattr(context, "terrain_config") else terrain_config

    # =================================================
    # FIRE MODE (consistent with ActionCatalog)
    # =================================================
    attack_mode = attacker.unit_type._resolve_attack_mode(distance)
    is_indirect = attack_mode == "INDIRECT_FIRE"

    # =================================================
    # LOS
    # =================================================
    los = LineOfSight.CLEAR

    if game_map:
        los = check_line_of_sight(
            attacker,
            target,
            game_map,
            terrain_cfg
        )

    _trace(
        "LOS_CHECK",
        attacker=attacker.unit_id,
        defender=target.unit_id,
        los=los.name,
        indirect=is_indirect,
    )

    # Direct fire requires LOS; indirect fire (mortar/artillery) ignores it.
    if not is_indirect and los == LineOfSight.BLOCKED:
        _trace(
            "RANGED_BLOCKED",
            attacker=attacker.unit_id,
            defender=target.unit_id,
        )
        return CombatResolutionResult([], [], [])

    # =================================================
    # INDIRECT RESTRICTIONS
    # A unit standing in no_indirect_from terrain (e.g. inside a building,
    # heavy forest) cannot lob indirect fire from there.
    # =================================================
    if game_map and is_indirect:
        attacker_hex = game_map.get_hex(
            attacker.position.q, attacker.position.r
        )

        if attacker_hex is not None:
            terrain_name = attacker_hex.get_terrain()
            # TerrainConfig.get accepts only the terrain name.
            # Keep compatibility in case a raw dict is passed.
            terrain_entry = {}
            if isinstance(terrain_cfg, dict):
                terrain_entry = terrain_cfg.get(terrain_name, {}) or {}
            else:
                terrain_entry = terrain_cfg.get(terrain_name) or {}
            if terrain_entry.get("no_indirect_from", False):
                _trace("INDIRECT_BLOCKED_FROM_TERRAIN", terrain=terrain_name)
                return CombatResolutionResult([], [], [])

    # ---------------- ATTACK ----------------
    attack_colors = list(
        attacker.unit_type.get_attack_dice(
            distance=distance,
            target_category=target.unit_type.category,
        )
    )

    if getattr(attacker, "suppressed", False) and attack_colors:
        # Rulebook 10.8.1: a suppressed attacker loses its WEAKEST attack die.
        weakest = min(attack_colors, key=lambda c: int(c))
        attack_colors.remove(weakest)

    attack_results = AttackDicePool(attack_colors).roll()

    # ---------------- SECTOR ----------------
    sector = determine_attack_sector(
        attacker_pos=attacker.position,
        defender_pos=target.position,
        defender_facing=getattr(target, "facing", "N"),
    )

    # ---------------- DEFENSE ----------------
    defense_base = list(
        target.unit_type.get_defense_dice(sector=sector)
    )
    defense_colors = list(defense_base)
    terrain_bonus = []

    if game_map:
        hex_ = game_map.get_hex(target.position.q, target.position.r)
        if hex_:
            # Indirect fire has no LOS line → no HINDERED defense die,
            # but terrain cover dice still apply.
            terrain_mod = TerrainModifier.from_hex(
                hex_,
                target,
                los=(None if is_indirect else los)
            )
            defense_colors = terrain_mod.modify_defense(defense_colors)
            terrain_bonus = defense_colors[len(defense_base):]
            fort_type = game_map.get_hex_fortification(target.position.q, target.position.r)
            fort_bonus = FortificationRules.defense_bonus(
                fort_type=fort_type,
                unit_category=target.unit_type.category.name,
                sector=sector,
            )
            defense_colors += fort_bonus
            _trace(
                "FORTIFICATION_DEFENSE",
                fort_type=fort_type,
                sector=sector.name,
                target=target.unit_id,
                terrain=[d.name for d in terrain_bonus],
                bonus=[d.name for d in fort_bonus],
            )
        else:
            fort_type = None
            fort_bonus = []
    else:
        fort_type = None
        fort_bonus = []

    defense_results = DefenseDicePool(defense_colors).roll()

    # ---------------- RESOLUTION ----------------
    comparison = compare_dice(
        attacker_dice=attack_results,
        defender_dice=defense_results,
    )

    dmg = comparison["remaining_damage"]
    crits = comparison["remaining_criticals"]
    suppress = comparison["remaining_suppress"]

    criticals = [
        resolve_critical(
            DiceFace.CRITICAL,
            UnitClass[target.unit_type.category.value],
        )
        for _ in range(crits)
    ]

    total_damage = dmg + crits

    hp_before = target.hp
    if total_damage > 0:
        target.apply_damage(total_damage)
    hp_after = target.hp

    killed = hp_before > 0 and hp_after == 0

    # ---------------- SUPPRESSION ----------------
    if suppress > 0 and target.alive:
        apply_suppression_hits(target, suppress)
        resolve_fallback(target)

    result = CombatResolutionResult(
        attack_roll=attack_results,
        defense_roll=defense_results,
        criticals=criticals,
    )

    if context and context.event_bus:
        context.event_bus.emit(
            {
                "type": "ACTION_EFFECT",
                "payload": {
                    "action": "RangedCombat",
                    "attacker": attacker.unit_id,
                    "defender": target.unit_id,
                    "distance": distance,
                    "attack_sector": sector.name,
                    "los": los.name,
                    "attack_mode": getattr(action, "attack_mode", "DIRECT_FIRE"),
                    "fortification": {
                        "type": fort_type,
                        "bonus_dice": [d.name for d in fort_bonus],
                    },
                    "defense_breakdown": {
                        "sector": sector.name,
                        "base_dice": [d.name for d in defense_base],
                        "terrain_bonus_dice": [d.name for d in terrain_bonus],
                        "fortification_bonus_dice": [d.name for d in fort_bonus],
                    },

                    "attacker_attack_dice": [
                        {"color": d.color.name, "faces": [f.name for f in d.faces]}
                        for d in attack_results
                    ],
                    "defender_defense_dice": [
                        {"color": d.color.name, "faces": [f.name for f in d.faces]}
                        for d in defense_results
                    ],

                    "attacker_effects": {
                        "damage": total_damage,
                        "criticals": criticals,
                        "suppress": suppress,
                        "suppression_state_after": target.is_suppressed(),
                    },

                    "defender_hp_before": hp_before,
                    "defender_hp_after": hp_after,
                    "defender_killed": killed,
                    "resolution": comparison,
                },
            }
        )

    return result
