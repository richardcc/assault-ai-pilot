# assault_model/combat/close_combat_resolver.py
#
# Close combat resolver.
#
# RESPONSIBILITY:
# - Compute close combat rounds
# - Roll dice
# - Apply effects (damage + suppression)
# - Determine winner
#
# IMPORTANT:
# - PURE combat computation
# - NO formatting
# - Emits ACTION_EFFECT

from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.defense_dice_pool import DefenseDicePool
from assault_model.combat.dice_face import DiceFace
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.dice_comparison import compare_dice
from assault_model.runtime.execution_context import ExecutionContext

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

        # NEW – resolution detail (non-breaking)
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

    while ctx.attacker.alive and ctx.defender.alive:
        rr = CloseCombatRoundResult(ctx.round_number)

        rr.attacker_hp_before = ctx.attacker.hp
        rr.defender_hp_before = ctx.defender.hp

        # ---------------- DICE POOLS ----------------
        dice_pools = {
            "attacker_attack": AttackDicePool(
                ctx.attacker.unit_type.get_close_combat_attack_dice(
                    ctx.defender.unit_type.category
                )
            ),
            "attacker_defense": DefenseDicePool(
                ctx.attacker.unit_type.get_defense_dice(
                    ctx.attack_sector
                )
            ),
            "defender_attack": AttackDicePool(
                ctx.defender.unit_type.get_close_combat_attack_dice(
                    ctx.attacker.unit_type.category
                )
            ),
            "defender_defense": DefenseDicePool(
                ctx.defender.unit_type.get_defense_dice(
                    ctx.attack_sector
                )
            ),
        }

        dice_results = {k: v.roll() for k, v in dice_pools.items()}

        rr.attacker_attack_dice = dice_results["attacker_attack"]
        rr.attacker_defense_dice = dice_results["attacker_defense"]
        rr.defender_attack_dice = dice_results["defender_attack"]
        rr.defender_defense_dice = dice_results["defender_defense"]

        # =================================================
        # ATTACKER → DEFENDER (10.7.2)
        # =================================================
        atk_vs_def = compare_dice_10_7_2(
            attacker_dice=rr.attacker_attack_dice,
            defender_dice=rr.defender_defense_dice,
        )

        attacker_damage = (
            atk_vs_def["remaining_damage"]
            + atk_vs_def["remaining_criticals"]
        )
        attacker_suppress = atk_vs_def["remaining_suppress"]

        # =================================================
        # DEFENDER → ATTACKER (10.7.2)
        # =================================================
        def_vs_atk = compare_dice_10_7_2(
            attacker_dice=rr.defender_attack_dice,
            defender_dice=rr.attacker_defense_dice,
        )

        defender_damage = (
            def_vs_atk["remaining_damage"]
            + def_vs_atk["remaining_criticals"]
        )
        defender_suppress = def_vs_atk["remaining_suppress"]

        # ---------------- EFFECTS (unchanged semantics) ----------------
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

        # ---------------- RESOLUTION DETAIL (NEW, NON-BREAKING) --------
        rr.attacker_resolution = atk_vs_def
        rr.defender_resolution = def_vs_atk

        # =================================================
        # APPLY DAMAGE (10.7.3)
        # =================================================
        if attacker_damage:
            ctx.defender.apply_damage(attacker_damage)
        if defender_damage:
            ctx.attacker.apply_damage(defender_damage)

        # =================================================
        # APPLY SUPPRESSION (10.7.3)
        # =================================================
        if attacker_suppress > 0 and ctx.defender.alive:
            ctx.defender.apply_suppression()

        if defender_suppress > 0 and ctx.attacker.alive:
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
    # Emit ALL rounds as ACTION_EFFECT
    # =================================================
    event_bus = context.event_bus if context else None
    if event_bus and result.rounds:
        event_bus.emit(
            {
                "type": "ACTION_EFFECT",
                "payload": {
                    # ---------- EXISTING FIELDS (UNCHANGED) ----------
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

                            # ---------- NEW (NON-BREAKING) ----------
                            "resolution": {
                                "attacker": r.attacker_resolution,
                                "defender": r.defender_resolution,
                            },
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