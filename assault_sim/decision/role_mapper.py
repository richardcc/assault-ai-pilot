from __future__ import annotations

from typing import Literal

from assault_model.map.hex_utils import safe_hex_distance

PlanIntent = Literal["CAPTURE", "DENY", "ATTRIT", "PRESERVE", "UNKNOWN", "SETUP_CAPTURE"]
UnitRole = Literal["ASSAULT", "SUPPORT_FIRE", "SCREEN", "HOLD_VP", "RESERVE", "UNKNOWN"]


def _local_role_kind(state, unit) -> str:
    classification = str(getattr(getattr(unit, "unit_type", None), "classification", "")).upper()
    if "INDIRECT" in classification or "SUPPORT" in classification:
        return "SUPPORT"
    enemies = [u for u in getattr(state, "units", []) if getattr(u, "alive", False) and getattr(u, "side", None) != getattr(unit, "side", None) and getattr(u, "position", None) is not None]
    if not enemies or getattr(unit, "position", None) is None:
        return "MANEUVER"
    dmin = min(safe_hex_distance(unit.position, e.position) for e in enemies)
    return "ASSAULT" if dmin <= 2 else "MANEUVER"


def assign_role(state, unit, plan_intent: str | None) -> UnitRole:
    if unit is None:
        return "UNKNOWN"
    intent = str(plan_intent or "").upper().strip()
    local_role = _local_role_kind(state, unit) if state is not None else "MANEUVER"
    if local_role == "SUPPORT":
        return "SUPPORT_FIRE"
    if local_role == "ASSAULT":
        return "ASSAULT"
    if intent in {"PRESERVE", "PRESERVE_AND_HOLD"}:
        return "RESERVE"
    if intent in {"DENY", "DENY_COUNTER"}:
        return "HOLD_VP"
    if intent in {"CAPTURE", "SETUP_CAPTURE", "CAPTURE_PUSH"}:
        return "SCREEN"
    if intent in {"ATTRIT", "FIX_AND_FLANK"}:
        return "ASSAULT"
    return "SCREEN"
