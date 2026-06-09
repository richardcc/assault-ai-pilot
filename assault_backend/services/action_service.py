from assault_model.actions.movement import MoveAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack  # ✅ NUEVO
from assault_model.actions.status import WaitAction
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction
from assault_model.actions.action_catalog import ActionCatalog

import json


def _build_attack_status(state, unit, attacks, catalog):
    if attacks:
        return {
            "can_attack": True,
            "reason_code": "ok",
            "reason_text": "Attack available",
        }

    enemies = [
        u for u in state.units
        if getattr(u, "alive", True) and getattr(u, "side", None) != unit.side
    ]
    if not enemies:
        return {
            "can_attack": False,
            "reason_code": "no_enemy_alive",
            "reason_text": "No alive enemy targets",
        }

    spotted_ids = set(getattr(unit, "spotted_enemies", []) or [])
    spotted_enemies = [u for u in enemies if u.unit_id in spotted_ids]
    if not spotted_enemies:
        return {
            "can_attack": False,
            "reason_code": "target_not_spotted",
            "reason_text": "No spotted enemy target",
        }

    in_range = [u for u in spotted_enemies if catalog._in_weapon_range(unit, u)]
    if not in_range:
        return {
            "can_attack": False,
            "reason_code": "out_of_range",
            "reason_text": "Spotted targets are out of weapon range",
        }

    has_los = [u for u in in_range if catalog._has_line_of_sight(unit, u)]
    if not has_los:
        return {
            "can_attack": False,
            "reason_code": "los_blocked",
            "reason_text": "Line of sight is blocked to in-range spotted targets",
        }

    return {
        "can_attack": False,
        "reason_code": "no_valid_attack_action",
        "reason_text": "No valid attack action for current state",
    }


def get_unit_actions(env, unit):
    """
    Compute available actions for a unit and
    convert them to frontend-friendly JSON.
    """

    state = env.game_state
    runtime = env.runtime

    if not getattr(unit, "alive", True):
        return {
            "unit_id": unit.unit_id,
            "moves": [],
            "attacks": [],
            "waits": [],
            "attack_status": {
                "can_attack": False,
                "reason_code": "unit_dead",
                "reason_text": "Unit is destroyed",
            },
            "abilities": [],
            "disabled": True,
        }

    # -------------------------------------------------
    # VALIDATION (runtime)
    # -------------------------------------------------
    is_active_side = (unit.side == getattr(runtime, "active_side", None))
    is_not_activated = (unit.unit_id not in getattr(runtime, "activated_units", set()))

    if not (is_active_side and is_not_activated):
        if not is_active_side:
            code = "not_active_side"
            text = "Unit side is not the active side"
        else:
            code = "already_activated"
            text = "Unit already activated this turn"
        return {
            "unit_id": unit.unit_id,
            "moves": [],
            "attacks": [],
            "waits": [],
            "attack_status": {
                "can_attack": False,
                "reason_code": code,
                "reason_text": text,
            },
            "abilities": [],
            "disabled": True
        }

    # -------------------------------------------------
    # TERRAIN CONFIG
    # -------------------------------------------------
    terrain_config = state.game_map.terrain_config

    # -------------------------------------------------
    # ACTION CATALOG
    # -------------------------------------------------
    catalog = ActionCatalog(
        state,
        unit,
        terrain_config=terrain_config
    )

    actions = catalog.actions()

    moves = []
    attacks = []
    waits = []

    # -------------------------------------------------
    # PROCESS ACTIONS
    # -------------------------------------------------
    for action in actions:

        # -------------------------
        # MOVEMENT
        # -------------------------
        if isinstance(action, MoveAction):
            if action.path:
                last = action.path[-1]
                moves.append({
                    "q": last.q,
                    "r": last.r,
                    "action_id": action.action_id
                })

        # -------------------------
        # ASSAULT
        # -------------------------
        elif isinstance(action, AssaultAction):
            attacks.append({
                "type": "assault",
                "target_id": action.target_id,
                "action_id": action.action_id
            })

        # -------------------------
        # RANGED DIRECT
        # -------------------------
        elif isinstance(action, RangedDirectAttack):
            attacks.append({
                "type": "ranged",
                "target_id": action.target_id,
                "action_id": action.action_id
            })

        # -------------------------
        # RANGED INDIRECT ✅ NUEVO
        # -------------------------
        elif isinstance(action, RangedIndirectAttack):
            attacks.append({
                "type": "ranged_indirect",
                "target_id": action.target_id,
                "action_id": action.action_id
            })

        # -------------------------
        # MOVE THEN FIRE (MVP 9.3)
        # -------------------------
        elif isinstance(action, MoveThenFireAction):
            dst = action.move_path[-1] if getattr(action, "move_path", None) else None
            attacks.append({
                "type": "move_then_fire",
                "target_id": getattr(action, "target_id", None),
                "target_hex": getattr(action.fire_action, "target_hex", None),
                "move_to": {"q": getattr(dst, "q", None), "r": getattr(dst, "r", None)} if dst is not None else None,
                "action_id": action.action_id,
            })

        # -------------------------
        # FIRE THEN MOVE (MVP 9.3)
        # -------------------------
        elif isinstance(action, FireThenMoveAction):
            dst = action.move_path[-1] if getattr(action, "move_path", None) else None
            attacks.append({
                "type": "fire_then_move",
                "target_id": getattr(action, "target_id", None),
                "target_hex": getattr(action.fire_action, "target_hex", None),
                "move_to": {"q": getattr(dst, "q", None), "r": getattr(dst, "r", None)} if dst is not None else None,
                "action_id": action.action_id,
            })

        # -------------------------
        # WAIT
        # -------------------------
        elif isinstance(action, WaitAction):
            waits.append({
                "type": "wait",
                "action_id": getattr(action, "action_id", f"WAIT:{unit.unit_id}")
            })

        # -------------------------
        # DEBUG UNKNOWN (MUY ÚTIL)
        # -------------------------
        else:
            print("[WARNING] Unknown action type:", type(action))

    # -------------------------------------------------
    # RESULT
    # -------------------------------------------------
    result = {
        "unit_id": unit.unit_id,
        "moves": moves,
        "attacks": attacks,
        "waits": waits,
        "attack_status": _build_attack_status(state, unit, attacks, catalog),
        "abilities": [],
        "disabled": False
    }

    # -------------------------------------------------
    # DEBUG
    # -------------------------------------------------
    print("[DEBUG][get_unit_actions]")
    print(json.dumps(result, indent=2))

    return result
