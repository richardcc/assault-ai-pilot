# assault_model/combat/smoke_resolver.py
"""
Smoke Ordnance Resolver (Rule 7.2 Firing Smoke & Rule 10.3 Smoke and LOS).

Official Rules (ASSAULT System):
- Units with smoke capability can fire smoke into a target hex and up to two
  nominated adjacent hexes.
- All three hexes must be in LOS (firer or adjacent friendly spotter).
- Firing smoke does NOT cause any damage or suppression to a unit inside a target hex.
- The targeted unit is NOT allowed any defense die roll against smoke.
- Active player makes an indirect smoke attack roll using the unit's smoke dice.
- Every damage symbol rolled (critical or normal hit) yields a smoke marker
  (up to a maximum of 4 per hex) in the target hex.
- Any dice that didn't roll a damage symbol (misses: blanks, suppressions) are put to one side.
- If misses exist and the player nominated an adjacent hex, those missed dice
  are rolled for that 1st adjacent hex (placing up to 4 markers).
- If misses still exist from that roll and a 2nd adjacent hex was nominated,
  the remaining missed dice are rolled for that 2nd adjacent hex.
"""

from typing import Dict, List, Optional, Tuple
import os

from assault_model.combat.attack_dice_pool import AttackDicePool
from assault_model.combat.battle_die import BattleDie
from assault_model.combat.dice_face import DiceFace
from assault_model.map.hex_utils import hex_distance
from assault_model.runtime.execution_context import ExecutionContext

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


def _count_damage_symbols(die: BattleDie) -> int:
    """
    Count damage symbols on a rolled die (both normal HIT and CRITICAL_HIT).
    """
    count = 0
    for face in getattr(die, "faces", []):
        fn = getattr(face, "name", str(face)).upper()
        if "CRITICAL" in fn or "HIT" in fn or "DAMAGE" in fn:
            count += 1
    return count


class SmokeResolutionResult:
    """
    Structured outcome of Rule 7.2 Firing Smoke.
    """

    def __init__(
        self,
        firer_id: str,
        target_hex: Tuple[int, int],
        adjacent_hexes: List[Tuple[int, int]],
        smoke_placed: Dict[Tuple[int, int], int],
        rolls_by_hex: Dict[Tuple[int, int], List[BattleDie]],
    ):
        self.firer_id = firer_id
        self.target_hex = target_hex
        self.adjacent_hexes = adjacent_hexes
        self.smoke_placed = smoke_placed
        self.rolls_by_hex = rolls_by_hex

    def __repr__(self) -> str:
        return (
            f"SmokeResolutionResult(firer={self.firer_id}, "
            f"target={self.target_hex}, placed={self.smoke_placed})"
        )


def resolve_smoke_fire(
    action,
    attacker,
    game_map,
    context: Optional[ExecutionContext] = None,
) -> SmokeResolutionResult:
    """
    Resolve a FireSmokeAction according to Rule 7.2.
    """
    target_hex = (int(action.target_hex[0]), int(action.target_hex[1]))
    adj_hexes = [
        (int(h[0]), int(h[1]))
        for h in getattr(action, "adjacent_hexes", []) or []
    ][:2]

    # Validate that nominated hexes are adjacent to target hex
    valid_adj = []
    for h in adj_hexes:
        if hex_distance(target_hex, h) == 1:
            valid_adj.append(h)
        else:
            _trace("SMOKE_ADJ_INVALID_DISTANCE", target=target_hex, rejected=h)

    # Smoke dice pool from unit type
    smoke_dice_colors = list(attacker.unit_type.get_smoke_dice())
    if not smoke_dice_colors:
        _trace("SMOKE_NO_DICE", unit=attacker.unit_id)
        return SmokeResolutionResult(
            firer_id=attacker.unit_id,
            target_hex=target_hex,
            adjacent_hexes=valid_adj,
            smoke_placed={},
            rolls_by_hex={},
        )

    smoke_placed: Dict[Tuple[int, int], int] = {}
    rolls_by_hex: Dict[Tuple[int, int], List[BattleDie]] = {}

    # -------------------------------------------------------------
    # STAGE 1: Target Hex
    # -------------------------------------------------------------
    rolled_stage_1 = AttackDicePool(smoke_dice_colors).roll()
    rolls_by_hex[target_hex] = rolled_stage_1

    stage_1_damage_symbols = sum(_count_damage_symbols(d) for d in rolled_stage_1)
    missed_dice_1 = [d for d in rolled_stage_1 if _count_damage_symbols(d) == 0]

    if game_map is not None:
        added_1 = game_map.add_smoke_markers(target_hex, stage_1_damage_symbols, max_per_hex=4)
        smoke_placed[target_hex] = added_1
    else:
        smoke_placed[target_hex] = min(4, stage_1_damage_symbols)

    _trace(
        "SMOKE_STAGE_1",
        hex=target_hex,
        symbols=stage_1_damage_symbols,
        placed=smoke_placed[target_hex],
        misses=len(missed_dice_1),
    )

    # -------------------------------------------------------------
    # STAGE 2: 1st Nominated Adjacent Hex (if misses exist)
    # -------------------------------------------------------------
    missed_dice_2 = []
    if missed_dice_1 and len(valid_adj) >= 1:
        adj_1 = valid_adj[0]
        dice_colors_stage_2 = [d.color for d in missed_dice_1]
        rolled_stage_2 = AttackDicePool(dice_colors_stage_2).roll()
        rolls_by_hex[adj_1] = rolled_stage_2

        stage_2_damage_symbols = sum(_count_damage_symbols(d) for d in rolled_stage_2)
        missed_dice_2 = [d for d in rolled_stage_2 if _count_damage_symbols(d) == 0]

        if game_map is not None:
            added_2 = game_map.add_smoke_markers(adj_1, stage_2_damage_symbols, max_per_hex=4)
            smoke_placed[adj_1] = added_2
        else:
            smoke_placed[adj_1] = min(4, stage_2_damage_symbols)

        _trace(
            "SMOKE_STAGE_2",
            hex=adj_1,
            symbols=stage_2_damage_symbols,
            placed=smoke_placed[adj_1],
            misses=len(missed_dice_2),
        )

    # -------------------------------------------------------------
    # STAGE 3: 2nd Nominated Adjacent Hex (if misses still exist)
    # -------------------------------------------------------------
    if missed_dice_2 and len(valid_adj) >= 2:
        adj_2 = valid_adj[1]
        dice_colors_stage_3 = [d.color for d in missed_dice_2]
        rolled_stage_3 = AttackDicePool(dice_colors_stage_3).roll()
        rolls_by_hex[adj_2] = rolled_stage_3

        stage_3_damage_symbols = sum(_count_damage_symbols(d) for d in rolled_stage_3)

        if game_map is not None:
            added_3 = game_map.add_smoke_markers(adj_2, stage_3_damage_symbols, max_per_hex=4)
            smoke_placed[adj_2] = added_3
        else:
            smoke_placed[adj_2] = min(4, stage_3_damage_symbols)

        _trace(
            "SMOKE_STAGE_3",
            hex=adj_2,
            symbols=stage_3_damage_symbols,
            placed=smoke_placed[adj_2],
        )

    # Rule 7.2: A firing status marker is placed on the unit
    attacker.has_fired = True

    return SmokeResolutionResult(
        firer_id=attacker.unit_id,
        target_hex=target_hex,
        adjacent_hexes=valid_adj,
        smoke_placed=smoke_placed,
        rolls_by_hex=rolls_by_hex,
    )
