from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.dice_face import DiceFace
from assault_model.units.unit_type import UnitCategory

import random
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if DEBUG_TRACE:
        payload = " ".join(f"{k}={v}" for k, v in data.items())
        print(f"[TRACE][{tag}] {payload}")


# =================================================
# Result containers
# =================================================

class CloseCombatRoundResult:
    def __init__(self, round_number: int):
        self.round_number = round_number

        # Dice (observability)
        self.attacker_attack_dice = []
        self.attacker_defense_dice = []
        self.defender_attack_dice = []
        self.defender_defense_dice = []

        # Effects
        self.attacker_effects = {}
        self.defender_effects = {}

        # HP snapshots
        self.attacker_hp_before = None
        self.attacker_hp_after = None
        self.defender_hp_before = None
        self.defender_hp_after = None

        self.notes: list[str] = []


class CloseCombatResult:
    def __init__(self):
        self.rounds: list[CloseCombatRoundResult] = []
        self.finished: bool = False
        self.winner: str | None = None
        self.outcome: str | None = None


# =================================================
# OUTFLANKED
# =================================================

def is_outflanked(ctx) -> bool:
    if ctx.defender.unit_type.category == UnitCategory.INFANTRY:
        return False
    return ctx.attack_sector == AttackSector.REAR


def apply_outflanked_reroll(attack_results):
    if not attack_results:
        return attack_results
    idx = random.randrange(len(attack_results))
    attack_results[idx] = DiceFace.roll()
    return attack_results


# =================================================
# Dice pool construction
# =================================================

def build_close_combat_dice_pools(ctx):
    attacker = ctx.attacker
    defender = ctx.defender

    return {
        "attacker_attack": AttackDicePool(
            attacker.unit_type.get_close_combat_attack_dice(
                defender.unit_type.category
            )
        ),
        "attacker_defense": DefenseDicePool(
            attacker.unit_type.get_close_combat_defense_dice(ctx.attack_sector)
        ),
        "defender_attack": AttackDicePool(
            defender.unit_type.get_close_combat_attack_dice(
                attacker.unit_type.category
            )
        ),
        "defender_defense": DefenseDicePool(
            defender.unit_type.get_close_combat_defense_dice(ctx.attack_sector)
        ),
    }


# =================================================
# Dice rolling
# =================================================

def roll_close_combat_dice(dice_pools):
    return {k: v.roll() for k, v in dice_pools.items()}


# =================================================
# Symbol cancellation
# =================================================

def cancel_combat_symbols(attack_results, defense_results):
    remaining_attack = attack_results.copy()
    remaining_defense = defense_results.copy()

    def cancel(priority_attack, defense_symbol):
        for symbol in priority_attack:
            if symbol in remaining_attack:
                remaining_attack.remove(symbol)
                remaining_defense.remove(defense_symbol)
                return True
        return False

    for defense_symbol in defense_results:
        if defense_symbol == DiceFace.CRITICAL:
            cancel(
                [DiceFace.CRITICAL, DiceFace.DAMAGE, DiceFace.SUPPRESS],
                defense_symbol,
            )
        elif defense_symbol == DiceFace.DAMAGE:
            cancel([DiceFace.DAMAGE, DiceFace.SUPPRESS], defense_symbol)
        elif defense_symbol == DiceFace.SUPPRESS:
            cancel([DiceFace.SUPPRESS], defense_symbol)

    return remaining_attack, remaining_defense


# =================================================
# Effect classification
# =================================================

def classify_combat_symbols(symbols):
    return {
        "damage": sum(1 for s in symbols if s == DiceFace.DAMAGE),
        "suppression": any(s == DiceFace.SUPPRESS for s in symbols),
        "critical": sum(1 for s in symbols if s == DiceFace.CRITICAL),
    }


# =================================================
# Apply effects
# =================================================

def apply_effects_to_unit(unit, effects):
    if effects["damage"] > 0:
        unit.apply_damage(effects["damage"])
    if effects["suppression"]:
        unit.apply_suppression()


def apply_close_combat_critical(unit, critical_count):
    if critical_count <= 0:
        return

    half_strength = unit.max_strength // 2

    if unit.strength <= half_strength:
        unit.apply_damage(unit.strength)
        return

    if critical_count >= 2:
        unit.apply_damage(unit.strength)
        return

    unit.apply_damage(unit.strength - half_strength)


# =================================================
# Main resolver (MULTI-ROUND)
# =================================================

def resolve_close_combat(ctx) -> CloseCombatResult:
    result = CloseCombatResult()
    ctx.round_number = 1
    MAX_ROUNDS = 10

    any_damage = False

    while ctx.attacker.alive and ctx.defender.alive:
        rr = CloseCombatRoundResult(round_number=ctx.round_number)

        rr.attacker_hp_before = ctx.attacker.hp
        rr.defender_hp_before = ctx.defender.hp

        dice_pools = build_close_combat_dice_pools(ctx)
        dice_results = roll_close_combat_dice(dice_pools)

        rr.attacker_attack_dice = dice_results["attacker_attack"]
        rr.attacker_defense_dice = dice_results["attacker_defense"]
        rr.defender_attack_dice = dice_results["defender_attack"]
        rr.defender_defense_dice = dice_results["defender_defense"]

        if ctx.round_number == 1 and is_outflanked(ctx):
            rr.attacker_attack_dice = apply_outflanked_reroll(
                rr.attacker_attack_dice
            )

        atk_remain, _ = cancel_combat_symbols(
            rr.attacker_attack_dice,
            rr.defender_defense_dice,
        )
        def_remain, _ = cancel_combat_symbols(
            rr.defender_attack_dice,
            rr.attacker_defense_dice,
        )

        attacker_effects = classify_combat_symbols(atk_remain)
        defender_effects = classify_combat_symbols(def_remain)

        if attacker_effects["damage"] or defender_effects["damage"]:
            any_damage = True

        apply_effects_to_unit(ctx.defender, attacker_effects)
        apply_effects_to_unit(ctx.attacker, defender_effects)

        apply_close_combat_critical(ctx.defender, attacker_effects["critical"])
        apply_close_combat_critical(ctx.attacker, defender_effects["critical"])

        rr.attacker_hp_after = ctx.attacker.hp
        rr.defender_hp_after = ctx.defender.hp

        rr.attacker_effects = attacker_effects
        rr.defender_effects = defender_effects

        result.rounds.append(rr)

        ctx.round_number += 1
        if ctx.round_number > MAX_ROUNDS:
            result.outcome = "max_rounds_reached"
            break

    result.finished = True

    attacker_dead = not ctx.attacker.alive
    defender_dead = not ctx.defender.alive

    if attacker_dead and defender_dead:
        result.winner = None
        result.outcome = "MUTUAL_DESTRUCTION"

    elif defender_dead:
        result.winner = ctx.attacker.unit_id
        result.outcome = "defender_eliminated"

    elif attacker_dead:
        result.winner = ctx.defender.unit_id
        result.outcome = "attacker_eliminated"

    else:
        result.winner = None
        result.outcome = "no_decision" if any_damage else "all_hits_cancelled"

    return result