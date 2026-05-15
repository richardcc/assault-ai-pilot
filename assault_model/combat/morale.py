# assault_model/combat/morale.py

import os
from assault_model.units.unit_instance import UnitInstance

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

    ✅ Does NOT duplicate logic
    ✅ Delegates to UnitInstance
    """

    if not unit.is_alive():
        return

    # delega en la unidad (ya tiene lógica de fallback incluida)
    unit.apply_suppression()


def apply_suppression_hits(unit: UnitInstance, hits: int):
    """
    Apply multiple suppression hits from combat result.

    IMPORTANT:
    - Each hit after the first may trigger fallback
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


def resolve_fallback(unit: UnitInstance):
    """
    Resolve fallback effects AFTER it has been triggered.

    This separates:
    ✔ state change (UnitInstance)
    ✔ behaviour (movement, destruction, etc.)
    """

    if not unit.is_in_fallback():
        return

    _trace(
        "RESOLVE_FALLBACK",
        unit=unit.unit_id,
        position=unit.position,
    )

    # ===============================
    # SPECIAL RULES
    # ===============================

    # artillery eliminated on fallback
    try:
        category = unit.unit_type.category.name
    except Exception:
        category = None

    if category == "ARTILLERY":
        _trace("FALLBACK_ARTILLERY_DESTROYED", unit=unit.unit_id)
        unit.alive = False
        return

    # ===============================
    # MOVEMENT (MVP SIMPLE)
    # ===============================

    retreat_unit_simple(unit)


# =====================================================
# INTERNAL HELPERS
# =====================================================

def retreat_unit_simple(unit: UnitInstance):
    """
    Minimal fallback movement (safe implementation).

    ✅ No dependency on map system
    ✅ Does not break engine
    ✅ Replace later with real pathfinding
    """

    if unit.position is None:
        return  # embarked or invalid

    try:
        q, r = unit.position

        # simple retreat backwards (placeholder)
        new_pos = (q - 1, r)

        _trace(
            "FALLBACK_MOVE",
            unit=unit.unit_id,
            from_pos=unit.position,
            to=new_pos,
        )

        unit.position = new_pos

    except Exception:
        _trace(
            "FALLBACK_MOVE_FAILED",
            unit=unit.unit_id,
        )