from __future__ import annotations

import time
from typing import Callable

from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.status import WaitAction


def catalog_priority_action(
    state,
    unit,
    *,
    is_non_displacement_move: Callable[[object, object], bool],
    is_uncaptured_vp_hex_for_side: Callable[[object, str | None, object], bool],
    record_catalog_time: Callable[[float], None] | None = None,
):
    t0 = time.perf_counter()
    try:
        legal_actions = ActionCatalog(
            state,
            unit,
            terrain_config=state.game_map.terrain_config,
        ).actions()
    except Exception:
        return WaitAction(getattr(unit, "unit_id", "SYSTEM")), "catalog_error"
    finally:
        if record_catalog_time is not None:
            try:
                record_catalog_time(time.perf_counter() - t0)
            except Exception:
                pass
    if not legal_actions:
        return WaitAction(getattr(unit, "unit_id", "SYSTEM")), "catalog_empty"

    side = getattr(unit, "side", None)

    def _score(a):
        aid = str(getattr(a, "action_id", "") or "").upper()
        name = str(getattr(a, "__class__", type("X", (), {})).__name__ or "").upper()
        path = getattr(a, "move_path", None) or getattr(a, "path", None)
        end = path[-1] if path else None
        if path and is_uncaptured_vp_hex_for_side(state, side, end):
            return (4, 0)
        is_attack = ("ATTACK" in name) or ("FIRE" in name) or ("RANGED" in aid)
        if is_attack:
            return (3, 0)
        if is_non_displacement_move(a, unit):
            return (0, -999)
        if aid.startswith("WAIT:") or "WAIT" in name:
            return (1, 0)
        return (2, 0)

    return max(legal_actions, key=_score), "catalog_priority"


def finalize_action(
    state,
    unit,
    action,
    *,
    is_non_displacement_move: Callable[[object, object], bool],
    is_uncaptured_vp_hex_for_side: Callable[[object, str | None, object], bool],
    finalizer_override_profile: str = "strict",
    finalizer_debug: bool = False,
    finalizer_debug_budget: int = 0,
    decision_context: dict | None = None,
    record_catalog_time: Callable[[float], None] | None = None,
):
    try:
        legal_actions_t0 = time.perf_counter()
        legal_actions = ActionCatalog(
            state,
            unit,
            terrain_config=state.game_map.terrain_config,
        ).actions()
        if record_catalog_time is not None:
            try:
                record_catalog_time(time.perf_counter() - legal_actions_t0)
            except Exception:
                pass
        legal_ids = {str(getattr(a, "action_id", "") or "") for a in legal_actions}
        aid = str(getattr(action, "action_id", "") or "") if action is not None else ""

        if action is None:
            fb, rsn = catalog_priority_action(
                state,
                unit,
                is_non_displacement_move=is_non_displacement_move,
                is_uncaptured_vp_hex_for_side=is_uncaptured_vp_hex_for_side,
                record_catalog_time=record_catalog_time,
            )
            return fb, f"executor_none->{rsn}", finalizer_debug_budget
        if not aid:
            fb, rsn = catalog_priority_action(
                state,
                unit,
                is_non_displacement_move=is_non_displacement_move,
                is_uncaptured_vp_hex_for_side=is_uncaptured_vp_hex_for_side,
                record_catalog_time=record_catalog_time,
            )
            return fb, f"empty_action_id->{rsn}", finalizer_debug_budget
        if aid not in legal_ids:
            if finalizer_debug and finalizer_debug_budget > 0:
                finalizer_debug_budget -= 1
                legal_sample = sorted(legal_ids)[:8]
                ctx = decision_context or {}
                print(
                    "[FINALIZER][not_in_catalog]"
                    f" unit={getattr(unit, 'unit_id', '?')}"
                    f" strategy={ctx.get('strategy')}"
                    f" sampled={ctx.get('sampled')}"
                    f" resolved={ctx.get('resolved')}"
                    f" executed={ctx.get('executed')}"
                    f" action_cls={type(action).__name__}"
                    f" aid={aid!r}"
                    f" legal_count={len(legal_ids)}"
                    f" legal_sample={legal_sample}"
                )
            fb, rsn = catalog_priority_action(
                state,
                unit,
                is_non_displacement_move=is_non_displacement_move,
                is_uncaptured_vp_hex_for_side=is_uncaptured_vp_hex_for_side,
                record_catalog_time=record_catalog_time,
            )
            return fb, f"not_in_catalog->{rsn}", finalizer_debug_budget
        if is_non_displacement_move(action, unit):
            if str(finalizer_override_profile).lower() == "soft":
                return action, "ok", finalizer_debug_budget
            fb, rsn = catalog_priority_action(
                state,
                unit,
                is_non_displacement_move=is_non_displacement_move,
                is_uncaptured_vp_hex_for_side=is_uncaptured_vp_hex_for_side,
                record_catalog_time=record_catalog_time,
            )
            return fb, f"non_displacement->{rsn}", finalizer_debug_budget
        return action, "ok", finalizer_debug_budget
    except Exception:
        fb, rsn = catalog_priority_action(
            state,
            unit,
            is_non_displacement_move=is_non_displacement_move,
            is_uncaptured_vp_hex_for_side=is_uncaptured_vp_hex_for_side,
            record_catalog_time=record_catalog_time,
        )
        return fb, f"catalog_validation_error->{rsn}", finalizer_debug_budget
