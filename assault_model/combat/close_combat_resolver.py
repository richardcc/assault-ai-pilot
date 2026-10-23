# assault_model/combat/close_combat_resolver.py

from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.dice_face import DiceFace
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.battle_die import BattleDie
from assault_model.combat.dice_comparison import compare_dice
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.attack_sector import AttackSector
from assault_model.runtime.execution_context import ExecutionContext

import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


def _has_trait(unit, trait_name: str) -> bool:
    traits = getattr(getattr(unit, "unit_type", None), "traits", []) or []
    return str(trait_name).upper() in {str(t).upper() for t in traits}


# =================================================
# Result containers
# =================================================

class CloseCombatRoundResult:
    def __init__(self, round_number: int):
        self.round_number = round_number

        self.attacker_attack_dice = []
        self.attacker_defense_dice = []
        self.defender_attack_dice = []
        self.defender_defense_dice = []

        self.attacker_effects = {}
        self.defender_effects = {}

        self.attacker_resolution = {}
        self.defender_resolution = {}

        self.attacker_hp_before = None
        self.attacker_hp_after = None
        self.defender_hp_before = None
        self.defender_hp_after = None


class CloseCombatResult:
    def __init__(self):
        self.rounds = []
        self.finished = False
        self.winner = None
        self.outcome = None



def _apply_cc006_unsuppressed_solo_frontal_penalty(attack_colors):
    if not attack_colors:
        return attack_colors
    # CC-006 (Task 2.4): Charging an alert, unsuppressed defender frontally without supporting attackers
    # loses the weakest attack die due to unsuppressed defensive fire.
    weakest = min(attack_colors, key=lambda c: int(c))
    attack_colors.remove(weakest)
    _trace(
        "CC006_UNSUPPRESSED_SOLO_FRONTAL_PENALTY",
        removed=getattr(weakest, "name", str(weakest)),
    )
    return attack_colors


# =================================================
# Resolver
# =================================================

def resolve_close_combat(
    ctx,
    context: ExecutionContext | None = None,
) -> CloseCombatResult:

    _trace(
        "CLOSE_COMBAT_START",
        attacker=ctx.attacker.unit_id,
        defender=ctx.defender.unit_id,
        sector=getattr(ctx.attack_sector, "name", ctx.attack_sector),
    )

    result = CloseCombatResult()
    ctx.round_number = 1
    MAX_ROUNDS = 10

    game_map = (
        context.game_map
        if context and getattr(context, "game_map", None)
        else None
    )

    # Rulebook 11.1.3: the close-combat ("target") hex is the DEFENDER's hex.
    # Both units use the terrain bonus of THAT hex, but only the STRONGEST
    # single terrain die. Vehicles get no terrain defense bonus in close combat.
    # Close combat is melee → no LOS hindrance is ever applied.
    def _strongest_terrain_die(unit):
        if unit.unit_type.category.name == "VEHICLE":
            return None
        if not game_map or ctx.defender.position is None:
            return None
        hex_ = game_map.get_hex(ctx.defender.position.q, ctx.defender.position.r)
        if not hex_:
            return None
        names = game_map.terrain_config.get_defense_dice(
            hex_.get_terrain(),
            unit.unit_type.category.name,
        )
        colors = [DiceColor[n] for n in names if n in DiceColor.__members__]
        if not colors:
            return None
        return max(colors, key=lambda c: int(c))

    def _defender_defense_colors():
        colors = list(ctx.defender.unit_type.get_defense_dice(ctx.attack_sector))
        strongest = _strongest_terrain_die(ctx.defender)
        if strongest is not None:
            colors.append(strongest)
        return colors

    def _attacker_defense_colors():
        colors = list(ctx.attacker.unit_type.get_defense_dice(ctx.attack_sector))
        if ctx.round_number == 1:
            # Initial round (11.1.3.2): the assaulting unit gets NO terrain
            # bonus, but instead one blue defense die.
            colors.append(DiceColor.BLUE)
        else:
            strongest = _strongest_terrain_die(ctx.attacker)
            if strongest is not None:
                colors.append(strongest)
        return colors

    def _apply_cc001_obstacle_crossing_penalty(attack_colors):
        if not attack_colors:
            return attack_colors
        # CC-001: in round 1, obstacle-crossing assault removes weakest attack die.
        weakest = min(attack_colors, key=lambda c: int(c))
        attack_colors.remove(weakest)
        _trace(
            "CC001_OBSTACLE_CROSSING_PENALTY",
            removed=getattr(weakest, "name", str(weakest)),
        )
        return attack_colors

    def _apply_cc003_activated_penalty(attack_colors):
        if not attack_colors:
            return attack_colors
        weakest = min(attack_colors, key=lambda c: int(c))
        attack_colors.remove(weakest)
        _trace(
            "CC003_ACTIVATED_PENALTY",
            removed=getattr(weakest, "name", str(weakest)),
        )
        return attack_colors

    def _apply_cc004_suppression_penalty(attack_colors, unit_label: str):
        if not attack_colors:
            return attack_colors
        weakest = min(attack_colors, key=lambda c: int(c))
        attack_colors.remove(weakest)
        _trace(
            "CC004_SUPPRESSION_PENALTY",
            unit=unit_label,
            removed=getattr(weakest, "name", str(weakest)),
        )
        return attack_colors

    def _apply_cc005_ambush_bonus(attack_colors):
        # Current behavior: ambush grants +1 GREEN attack die in round 1.
        attack_colors.append(DiceColor.GREEN)
        _trace("CC005_AMBUSH_BONUS", added="GREEN")
        return attack_colors

    def _dice_result_score(result: DiceResult) -> int:
        # Prefer more symbols; critical gets extra weight.
        score = len(result.faces)
        if any(f == DiceFace.CRITICAL for f in result.faces):
            score += 2
        return score

    def _apply_cc002_outflank_reroll(results):
        if not results:
            return results
        # Reroll the weakest current die once; keep best of old/new.
        weakest_idx = min(range(len(results)), key=lambda i: _dice_result_score(results[i]))
        weakest_result = results[weakest_idx]
        rerolled = BattleDie(weakest_result.color).roll()
        if _dice_result_score(rerolled) >= _dice_result_score(weakest_result):
            results[weakest_idx] = rerolled
            chosen = "rerolled"
        else:
            chosen = "kept"
        _trace(
            "CC002_OUTFLANK_REROLL",
            color=weakest_result.color.name,
            prior=[f.name for f in weakest_result.faces],
            rerolled=[f.name for f in rerolled.faces],
            decision=chosen,
        )
        return results

    while ctx.attacker.alive and ctx.defender.alive:
        rr = CloseCombatRoundResult(ctx.round_number)

        rr.attacker_hp_before = ctx.attacker.hp
        rr.defender_hp_before = ctx.defender.hp

        # ---------------- DICE POOLS ----------------
        attacker_attack_colors = list(
            ctx.attacker.unit_type.get_close_combat_attack_dice(
                ctx.defender.unit_type.category
            )
        )
        defender_attack_colors = list(
            ctx.defender.unit_type.get_close_combat_attack_dice(
                ctx.attacker.unit_type.category
            )
        )
        if ctx.round_number == 1 and bool(getattr(ctx, "crossed_obstacle", False)):
            attacker_attack_colors = _apply_cc001_obstacle_crossing_penalty(attacker_attack_colors)
        if ctx.round_number == 1 and bool(getattr(ctx.attacker, "activated", False)):
            attacker_attack_colors = _apply_cc003_activated_penalty(attacker_attack_colors)
        if bool(getattr(ctx.attacker, "suppressed", False)):
            attacker_attack_colors = _apply_cc004_suppression_penalty(attacker_attack_colors, "attacker")
        if bool(getattr(ctx.defender, "suppressed", False)):
            defender_attack_colors = _apply_cc004_suppression_penalty(defender_attack_colors, "defender")
        if ctx.round_number == 1 and bool(getattr(ctx.attacker, "ambush", False)):
            attacker_attack_colors = _apply_cc005_ambush_bonus(attacker_attack_colors)
        if ctx.round_number == 1 and bool(getattr(ctx, "unsuppressed_solo_frontal_penalty_enabled", False)):
            is_frontal = getattr(ctx, "attack_sector", AttackSector.FRONT) == AttackSector.FRONT
            is_unsuppressed_def = not bool(getattr(ctx.defender, "suppressed", False))
            has_no_supporters = len(list(getattr(ctx, "supporting_attackers", []) or [])) == 0
            if is_frontal and is_unsuppressed_def and has_no_supporters and not bool(getattr(ctx.attacker, "ambush", False)):
                attacker_attack_colors = _apply_cc006_unsuppressed_solo_frontal_penalty(attacker_attack_colors)

        # Palma et al. 2025 (Sec. 3.3, Fig. 3): Multi-unit combined assault coordination
        # Each adjacent committed supporting attacker squad adds +1 supporting attack die (WHITE, or RED if heavy support)
        if ctx.round_number == 1:
            for sup_unit in list(getattr(ctx, "supporting_attackers", []) or []):
                if bool(getattr(sup_unit, "alive", True)) and not bool(getattr(sup_unit, "suppressed", False)):
                    sup_code = str(getattr(getattr(sup_unit, "unit_type", None), "code", "")).upper()
                    added_color = DiceColor.RED if ("MMG" in sup_code or "HMG" in sup_code or "MORTAR" in sup_code) else DiceColor.GREEN
                    attacker_attack_colors.append(added_color)
                    _trace("CC_COMBINED_ASSAULT_BONUS", side="attacker", supporter=getattr(sup_unit, "unit_id", None), die=added_color.name)

            for sup_def in list(getattr(ctx, "supporting_defenders", []) or []):
                if bool(getattr(sup_def, "alive", True)) and not bool(getattr(sup_def, "suppressed", False)):
                    sup_code = str(getattr(getattr(sup_def, "unit_type", None), "code", "")).upper()
                    added_color = DiceColor.RED if ("MMG" in sup_code or "HMG" in sup_code or "MORTAR" in sup_code) else DiceColor.GREEN
                    defender_attack_colors.append(added_color)
                    _trace("CC_COMBINED_ASSAULT_BONUS", side="defender", supporter=getattr(sup_def, "unit_id", None), die=added_color.name)

        dice_pools = {
            "attacker_attack": AttackDicePool(
                attacker_attack_colors
            ),
            "attacker_defense": DefenseDicePool(
                _attacker_defense_colors()
            ),
            "defender_attack": AttackDicePool(
                defender_attack_colors
            ),
            "defender_defense": DefenseDicePool(
                _defender_defense_colors()
            ),
        }

        dice_results = {k: v.roll() for k, v in dice_pools.items()}

        rr.attacker_attack_dice = dice_results["attacker_attack"]
        if (
            (
                ctx.round_number == 1
                and getattr(ctx.attack_sector, "name", None) in {AttackSector.FLANK_LEFT.name, AttackSector.FLANK_RIGHT.name, AttackSector.REAR.name}
            )
            or _has_trait(ctx.attacker, "RAPID_FIRE")
        ):
            rr.attacker_attack_dice = _apply_cc002_outflank_reroll(rr.attacker_attack_dice)
        rr.attacker_defense_dice = dice_results["attacker_defense"]
        rr.defender_attack_dice = dice_results["defender_attack"]
        if _has_trait(ctx.defender, "RAPID_FIRE"):
            rr.defender_attack_dice = _apply_cc002_outflank_reroll(rr.defender_attack_dice)
        rr.defender_defense_dice = dice_results["defender_defense"]

        # =================================================
        # ATTACKER → DEFENDER
        # =================================================
        atk_vs_def = compare_dice(
            attacker_dice=rr.attacker_attack_dice,
            defender_dice=rr.defender_defense_dice,
        )

        attacker_damage = (
            atk_vs_def["remaining_damage"]
            + atk_vs_def["remaining_criticals"]
        )
        if ctx.round_number == 1 and _has_trait(ctx.defender, "TOUGH") and attacker_damage > 0:
            attacker_damage = max(0, attacker_damage - 1)
            _trace("TOUGH_TRAIT_DEFENDER_REDUCED_DAMAGE", unit=ctx.defender.unit_id)

        attacker_suppress = atk_vs_def["remaining_suppress"]
        if _has_trait(ctx.attacker, "FLAMETHROWER"):
            attacker_suppress += 1
        if _has_trait(ctx.defender, "REAR_ECHELON"):
            attacker_suppress += 1

        # =================================================
        # DEFENDER → ATTACKER
        # =================================================
        def_vs_atk = compare_dice(
            attacker_dice=rr.defender_attack_dice,
            defender_dice=rr.attacker_defense_dice,
        )

        defender_damage = (
            def_vs_atk["remaining_damage"]
            + def_vs_atk["remaining_criticals"]
        )
        if ctx.round_number == 1 and _has_trait(ctx.attacker, "TOUGH") and defender_damage > 0:
            defender_damage = max(0, defender_damage - 1)
            _trace("TOUGH_TRAIT_ATTACKER_REDUCED_DAMAGE", unit=ctx.attacker.unit_id)

        defender_suppress = def_vs_atk["remaining_suppress"]
        if _has_trait(ctx.defender, "FLAMETHROWER"):
            defender_suppress += 1
        if _has_trait(ctx.attacker, "REAR_ECHELON"):
            defender_suppress += 1

        # ---------------- EFFECTS ----------------
        rr.attacker_effects = {
            "damage": attacker_damage,
            "suppress": attacker_suppress,
            "remaining_criticals": atk_vs_def["remaining_criticals"],
        }

        rr.defender_effects = {
            "damage": defender_damage,
            "suppress": defender_suppress,
            "remaining_criticals": def_vs_atk["remaining_criticals"],
        }

        rr.attacker_resolution = atk_vs_def
        rr.defender_resolution = def_vs_atk

        # =================================================
        # APPLY DAMAGE
        # =================================================
        if attacker_damage:
            ctx.defender.apply_damage(attacker_damage)

        if defender_damage:
            ctx.attacker.apply_damage(defender_damage)

        # =================================================
        # APPLY SUPPRESSION (SAFE — NO FALLBACK CHAIN)
        # =================================================
        if attacker_suppress > 0 and ctx.defender.alive:
            if not ctx.defender.is_suppressed():
                ctx.defender.apply_suppression()

        if defender_suppress > 0 and ctx.attacker.alive:
            if not ctx.attacker.is_suppressed():
                ctx.attacker.apply_suppression()

        rr.attacker_hp_after = ctx.attacker.hp
        rr.defender_hp_after = ctx.defender.hp

        result.rounds.append(rr)

        ctx.round_number += 1
        if ctx.round_number > MAX_ROUNDS:
            break

    result.finished = True

    attacker_dead = not ctx.attacker.alive
    defender_dead = not ctx.defender.alive

    if attacker_dead and defender_dead:
        result.winner = None
        result.outcome = "both_eliminated"
    elif defender_dead:
        result.winner = ctx.attacker.unit_id
        result.outcome = "defender_eliminated"
    elif attacker_dead:
        result.winner = ctx.defender.unit_id
        result.outcome = "attacker_eliminated"
    else:
        any_hp_lost = any(
            r.attacker_hp_after < r.attacker_hp_before
            or r.defender_hp_after < r.defender_hp_before
            for r in result.rounds
        )
        result.winner = None
        result.outcome = "no_decision" if any_hp_lost else "all_hits_cancelled"

    # =================================================
    # EVENT EMISSION
    # =================================================
    event_bus = context.event_bus if context else None

    if event_bus and result.rounds:
        event_bus.emit(
            {
                "type": "ACTION_EFFECT",
                "payload": {
                    "action": "CloseCombat",
                    "attacker": ctx.attacker.unit_id,
                    "defender": ctx.defender.unit_id,
                    "sector": ctx.attack_sector.name,

                    "rounds": [
                        {
                            "round": r.round_number,

                            "attacker_attack_dice": [
                                {
                                    "color": d.color.name,
                                    "faces": [f.name for f in d.faces],
                                }
                                for d in r.attacker_attack_dice
                            ],

                            "attacker_defense_dice": [
                                {
                                    "color": d.color.name,
                                    "faces": [f.name for f in d.faces],
                                }
                                for d in r.attacker_defense_dice
                            ],

                            "defender_attack_dice": [
                                {
                                    "color": d.color.name,
                                    "faces": [f.name for f in d.faces],
                                }
                                for d in r.defender_attack_dice
                            ],

                            "defender_defense_dice": [
                                {
                                    "color": d.color.name,
                                    "faces": [f.name for f in d.faces],
                                }
                                for d in r.defender_defense_dice
                            ],

                            "attacker_hp_before": r.attacker_hp_before,
                            "attacker_hp_after": r.attacker_hp_after,
                            "defender_hp_before": r.defender_hp_before,
                            "defender_hp_after": r.defender_hp_after,

                            "attacker_effects": r.attacker_effects,
                            "defender_effects": r.defender_effects,

                            "resolution": {
                                "attacker": r.attacker_resolution,
                                "defender": r.defender_resolution,
                            },

                            # ✅ NEW: FINAL STATE (NO BREAKING)
                            "attacker_suppressed": ctx.attacker.is_suppressed(),
                            "defender_suppressed": ctx.defender.is_suppressed(),
                            "attacker_fallback": ctx.attacker.is_in_fallback(),
                            "defender_fallback": ctx.defender.is_in_fallback(),
                        }
                        for r in result.rounds
                    ],

                    "outcome": result.outcome,
                    "winner": result.winner,
                },
            }
        )

    _trace(
        "CLOSE_COMBAT_END",
        rounds=len(result.rounds),
        winner=result.winner,
        outcome=result.outcome,
    )

    return result