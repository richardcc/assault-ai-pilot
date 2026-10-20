from __future__ import annotations

from typing import Dict, List, Optional

from assault_bench.telemetry_models import normalize_side_key


def side_hp_snapshot(units) -> Dict[str, float]:
    hp: Dict[str, float] = {}
    for u in list(units or []):
        if isinstance(u, dict):
            side_raw = u.get("side", "")
            hp_raw = u.get("hp", 0.0)
        else:
            side_raw = getattr(u, "side", "")
            hp_raw = getattr(u, "hp", 0.0)
        side = normalize_side_key(side_raw)
        if not side:
            continue
        hp[side] = hp.get(side, 0.0) + float(max(0.0, float(hp_raw or 0.0)))
    return hp


def side_alive_snapshot(units) -> Dict[str, int]:
    alive: Dict[str, int] = {}
    for u in list(units or []):
        if isinstance(u, dict):
            side_raw = u.get("side", "")
            alive_raw = u.get("alive", False)
        else:
            side_raw = getattr(u, "side", "")
            alive_raw = getattr(u, "alive", False)
        side = normalize_side_key(side_raw)
        if not side:
            continue
        if bool(alive_raw):
            alive[side] = alive.get(side, 0) + 1
    return alive


def unit_suppressed_state_from_raw(unit_obj: object) -> Optional[bool]:
    if isinstance(unit_obj, dict):
        getter = lambda key: unit_obj.get(key, None)
    else:
        getter = lambda key: getattr(unit_obj, key, None)
    for key in ("suppressed", "is_suppressed", "pinned", "is_pinned"):
        raw = getter(key)
        if raw is None:
            continue
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        txt = str(raw).strip().lower()
        if txt in {"1", "true", "yes", "y", "on"}:
            return True
        if txt in {"0", "false", "no", "n", "off"}:
            return False
    return None


def unit_snapshot_dict(u) -> Dict[str, object]:
    if isinstance(u, dict):
        getter = lambda key, default: u.get(key, default)
    else:
        getter = lambda key, default: getattr(u, key, default)
    suppressed_state = unit_suppressed_state_from_raw(u)
    doctrine_role = str(getter("doctrine_role", "") or "")
    active_role = str(getter("active_role", getter("current_role", getter("role_assigned", doctrine_role))) or doctrine_role)
    role_is_mutated = bool(getter("role_is_mutated", getter("mutated", False)))
    role_mutation_reason = str(getter("role_mutation_reason", getter("mutation_reason", "DEFAULT_PROFILE")) or "DEFAULT_PROFILE")
    prior_boost_applied = float(getter("prior_boost_applied", 0.0) or 0.0)
    badge_label = str(getter("badge_label", "") or "")
    if not badge_label and active_role:
        badge_label = f"{active_role.replace('ROLE_', '')}"

    return {
        "unit_id": str(getter("unit_id", "") or ""),
        "unit_key": str(getter("unit_key", "") or ""),
        "unit_label": str(getter("unit_label", "") or ""),
        "side": str(getter("side", "") or ""),
        "q": int(getter("q", 0) or 0),
        "r": int(getter("r", 0) or 0),
        "hp": float(getter("hp", 0.0) or 0.0),
        "alive": bool(getter("alive", False)),
        "suppressed": (
            bool(suppressed_state) if suppressed_state is not None else None
        ),
        "doctrine_role": doctrine_role,
        "active_role": active_role,
        "role_assigned": active_role,
        "role_is_mutated": role_is_mutated,
        "role_mutation_reason": role_mutation_reason,
        "prior_boost_applied": prior_boost_applied,
        "badge_label": badge_label,
    }


def units_snapshot(units) -> List[Dict[str, object]]:
    return [unit_snapshot_dict(u) for u in list(units or [])]
