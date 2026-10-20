from typing import List, Optional, Tuple
from dataclasses import dataclass
import os

from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.battle_die import BattleDie, DiceResult
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_comparison import compare_dice
from assault_model.map.terrain import Terrain
from assault_model.map.fortification_config import fortification_config
from assault_model.map.terrain_config import terrain_config

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


@dataclass
class ExplosiveChargeResolutionResult:
    """
    Result of detonating an explosive charge against a building,
    fortification, or obstacle (Rule 12.5 & Combat Engineers card).
    """
    attack_roll: List[DiceResult]
    defense_roll: List[DiceResult]
    outcome: str
    structure_collapsed: bool
    obstacle_destroyed: bool
    units_affected: List[str]
    remaining_criticals: int
    remaining_damage: int
    remaining_suppress: int


def _get_strongest_terrain_defense_die(
    game_map,
    q: int,
    r: int,
    target_feature: str,
) -> DiceColor:
    """
    Determine the strongest terrain defense die of the target hex/feature.
    According to Rule 12.5 and unit card:
    'by rolling a red attack die against the strongest terrain defense die
    or one green die if no terrain defense die is available.'
    """
    available_dice: List[DiceColor] = []

    # 1. Fortification bonus (if target or present in hex)
    fort_type = game_map.get_hex_fortification(q, r) if game_map else None
    if fort_type:
        for sec in (AttackSector.FRONT, AttackSector.FLANK_LEFT, AttackSector.REAR):
            fort_dice = fortification_config.get_defense_bonus(fort_type, "INFANTRY", sec)
            available_dice.extend(fort_dice)


    # 2. Hex terrain defense (e.g. building_single, building_multi)
    hex_tile = game_map.get_hex(q, r) if game_map else None
    if hex_tile:
        t_type = hex_tile.get_terrain()
        t_name = getattr(t_type, "value", str(t_type))
        # get defense dice from terrain config
        t_dice_names = terrain_config.get_defense_dice(t_name, "INFANTRY")
        for dn in t_dice_names:
            try:
                available_dice.append(DiceColor[dn])
            except Exception:
                pass


    if available_dice:
        # Return the strongest die (highest numeric value in DiceColor)
        strongest = max(available_dice, key=lambda c: c.value)
        _trace("EXPLOSIVE_CHARGE_DEFENSE_DIE", target=(q, r), die=strongest.name)
        return strongest

    # Default if no terrain defense die is available: 1 GREEN die
    _trace("EXPLOSIVE_CHARGE_DEFAULT_DEFENSE_DIE", target=(q, r), die="GREEN")
    return DiceColor.GREEN


def resolve_explosive_charge(
    action,
    attacker,
    game_map,
    game_state,
    context=None,
    injected_attack_roll: Optional[List[DiceResult]] = None,
    injected_defense_roll: Optional[List[DiceResult]] = None,
) -> ExplosiveChargeResolutionResult:
    """
    Resolve Rule 12.5 Explosive Charge detonation.

    Procedure:
    1. Attacker rolls 1 RED attack die.
    2. Defender rolls strongest terrain defense die, or 1 GREEN die if none available.
    3. Compare dice using Rule 10.7.2.
    4. Apply destruction, collapse, or morale effects based on Rule 12.5 table.
    """
    tq, tr = action.target_hex
    target_feature = getattr(action, "target_feature", "structure")

    _trace(
        "RESOLVE_EXPLOSIVE_CHARGE_START",
        attacker=attacker.unit_id,
        target=(tq, tr),
        feature=target_feature,
    )

    # 1. Attack roll: check for unit-specific custom dice in attack tables, defaulting to canonical 1 RED die
    if injected_attack_roll is not None:
        attack_results = list(injected_attack_roll)
    else:
        custom_dice = None
        if hasattr(attacker, "unit_type") and attacker.unit_type:
            raw_attack = getattr(attacker.unit_type, "_attack_raw", {}) or {}
            exp_entry = raw_attack.get("EXPLOSIVE_CHARGE")
            if isinstance(exp_entry, dict) and "dice" in exp_entry:
                custom_dice = [DiceColor[d] for d in exp_entry["dice"] if d in DiceColor.__members__]
            elif isinstance(exp_entry, list):
                custom_dice = [DiceColor[d] for d in exp_entry if d in DiceColor.__members__]
            elif hasattr(attacker.unit_type, "explosive_charge_dice"):
                custom_dice = attacker.unit_type.explosive_charge_dice

        if custom_dice:
            attack_results = [BattleDie(c).roll() for c in custom_dice]
        else:
            # Canonical Rule 12.5 default: 1 RED die
            attack_results = [BattleDie(DiceColor.RED).roll()]


    # 2. Defense roll (strongest terrain die or GREEN)
    defense_color = _get_strongest_terrain_defense_die(game_map, tq, tr, target_feature)
    if injected_defense_roll is not None:
        defense_results = list(injected_defense_roll)
    else:
        defense_results = [BattleDie(defense_color).roll()]

    # 3. Dice comparison
    comparison = compare_dice(
        attacker_dice=attack_results,
        defender_dice=defense_results,
    )
    rem_crit = comparison.get("remaining_criticals", 0)
    rem_dmg = comparison.get("remaining_damage", 0)
    rem_sup = comparison.get("remaining_suppress", 0)

    _trace(
        "EXPLOSIVE_CHARGE_DICE_RESULT",
        attacker=attacker.unit_id,
        crits=rem_crit,
        damage=rem_dmg,
        suppress=rem_sup,
    )

    # 4. Target evaluation and resolution
    fort_type = game_map.get_hex_fortification(tq, tr) if game_map else None
    hex_tile = game_map.get_hex(tq, tr) if game_map else None
    is_building = False
    if hex_tile:
        t_val = getattr(hex_tile.terrain, "value", str(hex_tile.terrain)).lower()
        is_building = "building" in t_val

    is_obstacle = fort_type in ("barbed_wire", "minefield", "tank_barricade")
    is_hard_fort = fort_type in ("bunker", "casemate", "pillbox", "gun_emplacement")
    is_soft_fort = fort_type in ("trench", "sandbag")

    structure_collapsed = False
    obstacle_destroyed = False
    units_affected: List[str] = []

    # Identify units inside target hex
    units_in_hex = [
        u for u in game_state.units
        if getattr(u, "alive", True)
        and getattr(u, "position", None) is not None
        and u.position.q == tq
        and u.position.r == tr
    ]

    # Evaluate Rule 12.5 outcome
    if rem_crit > 0 and rem_dmg > 0:
        outcome = "COLLAPSED_ELIMINATED"
        structure_collapsed = True
        obstacle_destroyed = True
        for u in units_in_hex:
            u.apply_damage(getattr(u, "hp", 1))
            units_affected.append(u.unit_id)

    elif rem_crit > 0:
        outcome = "COLLAPSED_HALF_STRENGTH"
        structure_collapsed = True
        obstacle_destroyed = True
        for u in units_in_hex:
            # Flipped to half strength (takes half max strength, min 1 dmg)
            half_dmg = max(1, getattr(u, "max_strength", 2) // 2)
            u.apply_damage(half_dmg)
            units_affected.append(u.unit_id)

    elif rem_dmg >= 2:
        outcome = "COLLAPSED_ONE_DAMAGE"
        structure_collapsed = True
        obstacle_destroyed = True
        for u in units_in_hex:
            u.apply_damage(1)
            units_affected.append(u.unit_id)

    elif rem_dmg == 1:
        if is_obstacle:
            # Obstacles like barbed wire and minefields are destroyed on 1 damage/hit
            outcome = "OBSTACLE_DESTROYED"
            obstacle_destroyed = True
        else:
            outcome = "NOT_COLLAPSED_FALLBACK"
            for u in units_in_hex:
                u.fallback = True
                units_affected.append(u.unit_id)

    elif rem_sup > 0:
        outcome = "NOT_COLLAPSED_SUPPRESSED"
        for u in units_in_hex:
            u.suppressed = True
            units_affected.append(u.unit_id)

    else:
        outcome = "NO_EFFECT"

    # Apply physical state changes to map
    if structure_collapsed or obstacle_destroyed:
        if is_obstacle or is_soft_fort:
            if game_map:
                game_map.remove_hex_fortification(tq, tr)
        elif is_hard_fort:
            # Bunker / gun position collapses to trench side (Rule 12.5)
            if game_map:
                game_map.set_hex_fortification_type(tq, tr, "trench")
        elif is_building:
            # Building collapses into ruins
            if hex_tile:
                hex_tile.terrain = Terrain.RUINS

    # Mark attacker action
    attacker.has_fast_action_this_turn = True
    attacker.has_fired_this_turn = True

    res = ExplosiveChargeResolutionResult(
        attack_roll=attack_results,
        defense_roll=defense_results,
        outcome=outcome,
        structure_collapsed=structure_collapsed,
        obstacle_destroyed=obstacle_destroyed,
        units_affected=units_affected,
        remaining_criticals=rem_crit,
        remaining_damage=rem_dmg,
        remaining_suppress=rem_sup,
    )

    _trace(
        "RESOLVE_EXPLOSIVE_CHARGE_COMPLETE",
        attacker=attacker.unit_id,
        outcome=outcome,
        collapsed=structure_collapsed,
        destroyed=obstacle_destroyed,
        affected=units_affected,
    )

    return res
