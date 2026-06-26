from __future__ import annotations

from typing import Literal

from assault_model.map.hex_utils import safe_hex_distance

PlanIntent = Literal["CAPTURE", "DENY", "ATTRIT", "PRESERVE", "UNKNOWN", "SETUP_CAPTURE"]
UnitRole = Literal["ASSAULT", "SUPPORT_FIRE", "SCREEN", "HOLD_VP", "RESERVE", "UNKNOWN"]
RoleResolveReason = Literal[
    "mapped_support",
    "mapped_assault",
    "mapped_intent",
    "fallback_intent",
    "fallback_no_unit",
]

_FALLBACK_ROLE_BY_INTENT: dict[str, UnitRole] = {
    "PRESERVE": "RESERVE",
    "PRESERVE_AND_HOLD": "RESERVE",
    "DENY": "HOLD_VP",
    "DENY_COUNTER": "HOLD_VP",
    "CAPTURE": "SCREEN",
    "SETUP_CAPTURE": "SCREEN",
    "CAPTURE_PUSH": "SCREEN",
    "ATTRIT": "ASSAULT",
    "FIX_AND_FLANK": "ASSAULT",
    "UNKNOWN": "SCREEN",
}


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
    role, _ = resolve_role_with_reason(state, unit, plan_intent)
    return role


def resolve_role_with_reason(state, unit, plan_intent: str | None) -> tuple[UnitRole, RoleResolveReason]:
    intent = str(plan_intent or "UNKNOWN").upper().strip() or "UNKNOWN"
    fallback_role = _FALLBACK_ROLE_BY_INTENT.get(intent, "SCREEN")

    if unit is None:
        return fallback_role, "fallback_no_unit"

    local_role = _local_role_kind(state, unit) if state is not None else "MANEUVER"
    if local_role == "SUPPORT":
        return "SUPPORT_FIRE", "mapped_support"
    if local_role == "ASSAULT":
        return "ASSAULT", "mapped_assault"

    mapped = _FALLBACK_ROLE_BY_INTENT.get(intent)
    if mapped is not None:
        return mapped, "mapped_intent"
    return "SCREEN", "fallback_intent"
