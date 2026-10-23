from assault_model.combat.modifiers.terrain_modifier import TerrainModifier
from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.critical_table import CRITICAL_TABLE
from assault_model.combat.critical_effect import CriticalEffect
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace
from assault_model.combat.attack_sector import AttackSector
from assault_model.map.combat_geometry import determine_attack_sector, calculate_facing_towards, is_in_arc_of_fire
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.combat.battle_die import DiceResult, BattleDie
from assault_model.combat.dice_comparison import compare_dice
from assault_model.map.terrain_config import terrain_config
from assault_model.rules.fortification_rules import FortificationRules

from assault_model.actions.combat_mode import CombatMode

from assault_model.combat.line_of_sight import (
    check_line_of_sight,
    LineOfSight,
)
from assault_model.combat.spotting import can_spot

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


def _has_trait(unit, trait_name: str) -> bool:
    if hasattr(unit, "has_trait"):
        return unit.has_trait(trait_name)
    traits = getattr(getattr(unit, "unit_type", None), "traits", []) or []
    target = str(trait_name).strip().upper()
    if target in ("SLOW", "SLOW_UNIT"):
        return any(str(t).strip().upper() in ("SLOW", "SLOW_UNIT") for t in traits)
    return target in {str(t).strip().upper() for t in traits}


def _remove_weakest_die(dice: list):
    if not dice:
        return None
    weakest = min(dice, key=lambda c: int(c))
    dice.remove(weakest)
    return weakest


def _remove_strongest_die(dice: list):
    if not dice:
        return None
    strongest = max(dice, key=lambda c: int(c))
    dice.remove(strongest)
    return strongest


class CombatResolutionResult:
    def __init__(self, attack_roll, defense_roll, criticals):
        self.attack_roll = attack_roll
        self.defense_roll = defense_roll
        self.criticals = criticals


def resolve_critical(face: DiceFace, target_class: UnitClass):
    effect = CRITICAL_TABLE.get(target_class, CriticalEffect.NO_EFFECT)
    return {
        "face": face.name,
        "target_class": target_class.name,
        "effect": effect.value,
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
    terrain_cfg = (
        context.terrain_config
        if context and hasattr(context, "terrain_config") and context.terrain_config is not None
        else (getattr(game_map, "terrain_config", None) or terrain_config)
    )

    # =================================================
    # FIRE MODE (consistent with ActionCatalog)
    # =================================================
    action_mode = getattr(action, "combat_mode", None)
    if action_mode == CombatMode.RANGED_INDIRECT or getattr(action, "attack_mode", None) == "INDIRECT_FIRE":
        attack_mode = "INDIRECT_FIRE"
    elif action_mode == CombatMode.RANGED_DIRECT or getattr(action, "attack_mode", None) == "DIRECT_FIRE":
        attack_mode = "DIRECT_FIRE"
    else:
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
    # SPOTTING GATE (RF-005)
    # =================================================
    if not is_indirect and game_map:
        if not can_spot(attacker, target, los, game_map, terrain_cfg):
            _trace(
                "RANGED_BLOCKED_SPOTTING",
                attacker=attacker.unit_id,
                defender=target.unit_id,
                los=los.name,
            )
            return CombatResolutionResult([], [], [])

    # Arc of fire gate for LIMITED_PIVOT (240° to flanks and rear; forward arc blocked)
    if not is_indirect:
        has_pivot = _has_trait(attacker, "PIVOT")
        has_lim_pivot = _has_trait(attacker, "LIMITED_PIVOT") or _has_trait(attacker, "LIMITED_PIVOT_240")
        if has_lim_pivot and not has_pivot:
            if not is_in_arc_of_fire(
                attacker.position,
                getattr(attacker, "facing", "N"),
                target.position,
                has_limited_pivot=True,
            ):
                _trace("RANGED_BLOCKED_LIMITED_PIVOT_ARC", attacker=attacker.unit_id, defender=target.unit_id)
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

    # ---------------- AUTOMATIC SHIELD ORIENTATION (Rule S43) ----------------
    if _has_trait(attacker, "SHIELD"):
        attacker_pos = getattr(attacker, "position", None)
        target_pos = getattr(target, "position", None)
        if attacker_pos is not None and target_pos is not None:
            new_facing = calculate_facing_towards(
                attacker_pos,
                target_pos,
                default_facing=getattr(attacker, "facing", "N"),
            )
            attacker.facing = new_facing
            _trace("SHIELD_ORIENTATED", attacker=getattr(attacker, "unit_id", "UNKNOWN"), facing=new_facing, target=getattr(target, "unit_id", "UNKNOWN"))

    # ---------------- ATTACK ----------------
    try:
        attack_colors = list(
            attacker.unit_type.get_attack_dice(
                distance=distance,
                target_category=target.unit_type.category,
                mode=attack_mode,
            )
        )
    except TypeError:
        # Backward-compatibility fallback for mock lambdas in older tests
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

    target_cat = getattr(getattr(target, "unit_type", None), "category", None)
    target_cat_val = str(getattr(target_cat, "value", target_cat)).upper()
    is_vehicle = target_cat_val == "VEHICLE"

    # Rule 7.1.2: Indirect Fire on Vehicles
    if is_indirect and is_vehicle:
        preliminary_results = AttackDicePool(attack_colors).roll()
        # Blank or suppressed results are put to one side. Keep only dice with damage or critical hit symbols.
        remaining_dice_colors = []
        for die in preliminary_results:
            has_dmg = any(
                "CRITICAL" in getattr(f, "name", str(f)).upper()
                or "HIT" in getattr(f, "name", str(f)).upper()
                or "DAMAGE" in getattr(f, "name", str(f)).upper()
                for f in getattr(die, "faces", [])
            )
            if has_dmg:
                remaining_dice_colors.append(die.color)

        if not remaining_dice_colors:
            _trace("INDIRECT_VEHICLE_INEFFECTIVE", attacker=attacker.unit_id, defender=target.unit_id)
            return CombatResolutionResult([], [], [])

        # The actual attack roll now takes place with any remaining dice
        attack_results = AttackDicePool(remaining_dice_colors).roll()
    else:
        attack_results = AttackDicePool(attack_colors).roll()

    # Rule Rifle Grenades / Indirect Reroll / Rapid Fire ("Attacker may re-roll one of their attack die. Re-rolled result must be used.")
    indirect_profile = getattr(attacker.unit_type, "indirect_fire_profile", {}) or {}
    can_reroll = (
        (is_indirect and indirect_profile.get("reroll", False))
        or _has_trait(attacker, "ATTACK_DIE_REROLL")
        or _has_trait(attacker, "RAPID_FIRE")
    )
    if can_reroll and attack_results:
        def _die_score(die):
            score = 0
            for f in getattr(die, "faces", []):
                fn = getattr(f, "name", str(f)).upper()
                if "CRITICAL" in fn:
                    score += 3
                elif "HIT" in fn or "DAMAGE" in fn:
                    score += 2
                elif "SUPPRESS" in fn:
                    score += 1
            return score

        weakest_idx = min(range(len(attack_results)), key=lambda i: _die_score(attack_results[i]))
        if _die_score(attack_results[weakest_idx]) < 2:
            rerolled_die = BattleDie(attack_results[weakest_idx].color).roll()
            _trace(
                "ATTACK_DIE_REROLL",
                attacker=attacker.unit_id,
                old_faces=[f.name for f in attack_results[weakest_idx].faces],
                new_faces=[f.name for f in rerolled_die.faces],
            )
            attack_results[weakest_idx] = rerolled_die

    # ---------------- SECTOR ----------------
    if is_indirect and is_vehicle:
        # Rule 7.1.2: A vehicle will normally use its flank defense dice (10.9.3)
        # when calculating which dice it receives from indirect fire.
        # If at least one of the remaining attack dice shows a critical hit result,
        # it is assumed to be a direct hit on that vehicle and the vehicle will instead use its above defense dice.
        has_crit = any(
            any("CRITICAL" in getattr(f, "name", str(f)).upper() for f in getattr(d, "faces", []))
            for d in attack_results
        )
        sector = AttackSector.ABOVE if has_crit else AttackSector.FLANK_LEFT
    else:
        sector = determine_attack_sector(
            attacker_pos=attacker.position,
            defender_pos=target.position,
            defender_facing=getattr(target, "facing", "N"),
        )

    # ---------------- DEFENSE ----------------
    defense_base = list(
        target.unit_type.get_defense_dice(sector=sector)
    )
    # Rule 7.1.2: In any case the vehicle receives one additional green die for its defense roll.
    if is_indirect and is_vehicle:
        defense_base.append(DiceColor.GREEN)

    # Rule 9.3 (MVP): defender gains extra defense when attacker uses
    # move&fire / fire&move composite actions.
    if bool(getattr(action, "move_fire_defense_bonus", False)):
        defense_base.append(DiceColor.GREEN)
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
                los=(None if is_indirect else los),
                terrain_cfg=terrain_cfg,
            )
            defense_colors = terrain_mod.modify_defense(defense_colors)
            terrain_bonus = defense_colors[len(defense_base):]

            def_loss = indirect_profile.get("defense_loss", "NONE") if is_indirect else "NONE"
            if (
                is_indirect
                and (def_loss == "WEAKEST_TERRAIN" or _has_trait(attacker, "REMOVE_WEAKEST_TERRAIN_DEFENSE"))
                and terrain_bonus
            ):
                removed = _remove_weakest_die(terrain_bonus)
                # Keep effective defense pool consistent with updated terrain bonus.
                defense_colors = list(defense_base) + list(terrain_bonus)
                _trace(
                    "TRAIT_REMOVE_WEAKEST_TERRAIN_DEFENSE",
                    attacker=attacker.unit_id,
                    defender=target.unit_id,
                    removed=getattr(removed, "name", str(removed)),
                )
            target_cat = getattr(getattr(target, "unit_type", None), "category", None)
            target_cat_value = str(getattr(target_cat, "value", target_cat)).upper()
            if (
                (def_loss == "STRONGEST_TERRAIN" or _has_trait(attacker, "REMOVE_STRONGEST_TERRAIN_DEFENSE") or _has_trait(attacker, "SNIPER"))
                and target_cat_value != "VEHICLE"
                and terrain_bonus
            ):
                removed = _remove_strongest_die(terrain_bonus)
                defense_colors = list(defense_base) + list(terrain_bonus)
                _trace(
                    "TRAIT_REMOVE_STRONGEST_TERRAIN_DEFENSE",
                    attacker=attacker.unit_id,
                    defender=target.unit_id,
                    removed=getattr(removed, "name", str(removed)),
                )
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

    # Flamethrower strips defender's strongest defense die (Card L3/35 Flame)
    if _has_trait(attacker, "FLAMETHROWER") and defense_colors:
        strongest_def = max(defense_colors, key=lambda c: int(c))
        defense_colors.remove(strongest_def)
        _trace("FLAMETHROWER_REMOVED_STRONGEST_DEFENSE", attacker=attacker.unit_id, defender=target.unit_id, removed=strongest_def.name)

    # Back Blast degrades Yellow defense die to Green when target has fired this turn (Cards S43 / Pr43)
    if _has_trait(target, "BACK_BLAST") and bool(getattr(target, "has_fired_this_turn", False)):
        if DiceColor.YELLOW in defense_colors:
            y_idx = defense_colors.index(DiceColor.YELLOW)
            defense_colors[y_idx] = DiceColor.GREEN
            _trace("BACK_BLAST_DEGRADED_YELLOW_TO_GREEN", defender=target.unit_id)

    defense_results = DefenseDicePool(defense_colors).roll()

    # ---------------- RESOLUTION ----------------
    comparison = compare_dice(
        attacker_dice=attack_results,
        defender_dice=defense_results,
    )

    dmg = comparison["remaining_damage"]
    crits = comparison["remaining_criticals"]
    suppress = comparison["remaining_suppress"]

    # Rule: Flamethrower causes 1 suppression ('X') automatically
    if _has_trait(attacker, "FLAMETHROWER") and target.alive:
        suppress += 1
        _trace("FLAMETHROWER_AUTO_SUPPRESSION", attacker=attacker.unit_id, defender=target.unit_id)

    # Rule: Rear Echelon Troops (without adjacent friendly unit, attacker receives automatic 'X' hit)
    if _has_trait(target, "REAR_ECHELON"):
        gs = getattr(context, "game_state", None) if context else None
        has_adj_friendly = False
        if gs and hasattr(gs, "units"):
            for u in gs.units:
                if u.unit_id != target.unit_id and u.side == target.side and getattr(u, "alive", True):
                    if safe_hex_distance(u.position, target.position) <= 1:
                        has_adj_friendly = True
                        break
        if not has_adj_friendly:
            suppress += 1
            _trace("REAR_ECHELON_AUTO_HIT", attacker=attacker.unit_id, defender=target.unit_id)

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
        gs = getattr(context, "game_state", None) if context else None
        resolve_fallback(target, game_state=gs, attacker=attacker)

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
