# assault_model/combat/morale.py

from typing import Optional
import os
from assault_model.units.unit_instance import UnitInstance
from assault_model.map.hex_coord import HexCoord

DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# =====================================================
# PUBLIC API
# =====================================================

def apply_suppression(unit: UnitInstance):
    """
    Entry point for suppression handling.
    Delegates to UnitInstance state machine.
    """
    if not unit.is_alive():
        return
    unit.apply_suppression()


def apply_suppression_hits(unit: UnitInstance, hits: int):
    """
    Apply multiple suppression hits from combat result.
    Each hit after the first may trigger fallback.
    """
    if not unit.is_alive() or hits <= 0:
        return

    _trace(
        "SUPPRESSION_HITS",
        unit=unit.unit_id,
        hits=hits,
    )

    for _ in range(hits):
        unit.apply_suppression()


def resolve_fallback(
    unit: UnitInstance,
    game_state=None,
    attacker=None,
    friendly_edge: Optional[str] = None,
):
    """
    Resolve fallback effects AFTER it has been triggered according to Rule 13.3 (Section 6.4):
    1. If unit is Artillery or Immobilized, it is eliminated immediately.
    2. If game_state is provided, executes the canonical Defilade & Friendly Edge retreat
       algorithm via MovementRules.calculate_fallback_destination.
    3. If no legal retreat hex exists (unit surrounded or impassable), it takes 1 damage point (Rule 13.3).
    4. Falls back to retreat_unit_simple only if no game_state or map is available (legacy decoupled).
    """
    if not unit.is_in_fallback():
        return

    _trace(
        "RESOLVE_FALLBACK",
        unit=unit.unit_id,
        position=unit.position,
    )

    # ===============================
    # SPECIAL RULES (Rule 13.3)
    # Artillery or immobilised units are eliminated if they are ever in fallback.
    # ===============================
    category = None
    try:
        category = unit.unit_type.category.name
    except Exception:
        category = None

    is_immobile = getattr(unit, "immobile", False)

    if category == "ARTILLERY" or is_immobile:
        _trace("FALLBACK_ARTILLERY_OR_IMMOBILE_DESTROYED", unit=unit.unit_id)
        unit.alive = False
        unit.strength = 0
        return

    # ===============================
    # MOVEMENT: CANONICAL DEFILADE & FRIENDLY EDGE (Rule 13.3 / Sec 6.4)
    # ===============================
    if game_state is not None:
        from assault_model.rules.movement_rules import MovementRules

        dest, debug_candidates = MovementRules.calculate_fallback_destination(
            game_state,
            unit,
            attacker=attacker,
            friendly_edge=friendly_edge,
        )

        if dest is not None:
            old_pos = unit.position
            unit.position = dest
            unit.fallback = True
            _trace(
                "FALLBACK_DEFILADE_MOVE",
                unit=unit.unit_id,
                from_pos=old_pos,
                to=dest,
                score=debug_candidates[0]["total_score"] if debug_candidates else 0,
            )
            if hasattr(game_state, "recalculate_hex_control"):
                game_state.recalculate_hex_control(affected_positions=[old_pos, dest])
        else:
            # Rule 13.3: If retreat is impossible, the unit takes a damage point
            # and remains in the hex it was last able to retreat into.
            _trace("FALLBACK_BLOCKED_TAKES_DAMAGE", unit=unit.unit_id, position=unit.position)
            unit.apply_damage(1)
            unit.fallback = True
            if unit.hp <= 0:
                unit.alive = False
    else:
        retreat_unit_simple(unit)


# =====================================================
# INTERNAL HELPERS
# =====================================================

def retreat_unit_simple(unit: UnitInstance):
    """
    Fallback retreat movement (decoupled fallback): moves unit 1 hex away.
    """
    if unit.position is None:
        return

    q, r = unit.position
    new_pos = HexCoord(q - 1, r)

    _trace(
        "FALLBACK_MOVE",
        unit=unit.unit_id,
        from_pos=unit.position,
        to=new_pos,
    )
    unit.position = new_pos
