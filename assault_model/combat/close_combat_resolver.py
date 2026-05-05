# assault_model/combat/close_combat_resolver.py
#
# Close combat resolver.
#
# RESPONSIBILITY:
# - Compute close combat rounds
# - Roll dice
# - Apply effects
# - Determine winner
#
# IMPORTANT:
# - PURE combat computation
# - NO formatting
# - Emits ACTION_EFFECT (same pattern as movement)

from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.dice_face import DiceFace
from assault_model.units.unit_type import UnitCategory
from assault_model.runtime.execution_context import ExecutionContext

import random
import os

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


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


# =================================================
# Resolver
# =================================================

def resolve_close_combat(
    ctx,
    context: ExecutionContext | None = None,   # ✅ ÚNICA ADICIÓN
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
    any_damage = False

    while ctx.attacker.alive and ctx.defender.alive:
        rr = CloseCombatRoundResult(ctx.round_number)

        _trace(
            "CLOSE_COMBAT_ROUND",
            round=ctx.round_number,
            attacker_hp=ctx.attacker.hp,
            defender_hp=ctx.defender.hp,
        )

        rr.attacker_hp_before = ctx.attacker.hp
        rr.defender_hp_before = ctx.defender.hp

        dice_pools = {
            "attacker_attack": AttackDicePool(
                ctx.attacker.unit_type.get_close_combat_attack_dice(
                    ctx.defender.unit_type.category
                )
            ),
            "attacker_defense": DefenseDicePool(
                ctx.attacker.unit_type.get_close_combat_defense_dice(ctx.attack_sector)
            ),
            "defender_attack": AttackDicePool(
                ctx.defender.unit_type.get_close_combat_attack_dice(
                    ctx.attacker.unit_type.category
                )
            ),
            "defender_defense": DefenseDicePool(
                ctx.defender.unit_type.get_close_combat_defense_dice(ctx.attack_sector)
            ),
        }

        dice_results = {k: v.roll() for k, v in dice_pools.items()}

        rr.attacker_attack_dice = dice_results["attacker_attack"]
        rr.attacker_defense_dice = dice_results["attacker_defense"]
        rr.defender_attack_dice = dice_results["defender_attack"]
        rr.defender_defense_dice = dice_results["defender_defense"]

        attacker_effects = {
            "damage": sum(1 for d in rr.attacker_attack_dice if d == DiceFace.DAMAGE),
        }
        defender_effects = {
            "damage": sum(1 for d in rr.defender_attack_dice if d == DiceFace.DAMAGE),
        }

        if attacker_effects["damage"] or defender_effects["damage"]:
            any_damage = True

        if attacker_effects["damage"]:
            ctx.defender.apply_damage(attacker_effects["damage"])
        if defender_effects["damage"]:
            ctx.attacker.apply_damage(defender_effects["damage"])

        rr.attacker_hp_after = ctx.attacker.hp
        rr.defender_hp_after = ctx.defender.hp

        rr.attacker_effects = attacker_effects
        rr.defender_effects = defender_effects

        result.rounds.append(rr)

        ctx.round_number += 1
        if ctx.round_number > MAX_ROUNDS:
            break

    result.finished = True

    if not ctx.defender.alive:
        result.winner = ctx.attacker.unit_id
        result.outcome = "defender_eliminated"
    elif not ctx.attacker.alive:
        result.winner = ctx.defender.unit_id
        result.outcome = "attacker_eliminated"
    else:
        result.winner = None
        result.outcome = "no_decision" if any_damage else "all_hits_cancelled"

    # -------------------------------------------------
    # ✅ EMIT COMBAT AS ACTION_EFFECT (FLAT PAYLOAD)
    # -------------------------------------------------
    event_bus = context.event_bus if context else None   # ✅ ÚNICO CAMBIO REAL
    if event_bus and result.rounds:
        last = result.rounds[-1]

        event_bus.emit(
            {
                "type": "ACTION_EFFECT",
                "payload": {
                    "action": "CloseCombat",
                    "attacker": ctx.attacker.unit_id,
                    "defender": ctx.defender.unit_id,
                    "sector": ctx.attack_sector.name,
                    "attacker_attack_dice": [d.name for d in last.attacker_attack_dice],
                    "attacker_defense_dice": [d.name for d in last.attacker_defense_dice],
                    "defender_attack_dice": [d.name for d in last.defender_attack_dice],
                    "defender_defense_dice": [d.name for d in last.defender_defense_dice],
                    "attacker_hp_before": last.attacker_hp_before,
                    "attacker_hp_after": last.attacker_hp_after,
                    "defender_hp_before": last.defender_hp_before,
                    "defender_hp_after": last.defender_hp_after,
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