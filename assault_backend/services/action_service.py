from assault_model.actions.movement import MoveAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.action_catalog import ActionCatalog

import json


def get_unit_actions(env, unit):
    """
    Compute available actions for a unit and
    convert them to frontend-friendly JSON.
    """

    state = env.game_state
    runtime = env.runtime

    # -------------------------------------------------
    # ✅ VALIDATION (runtime)
    # -------------------------------------------------
    is_active_side = (unit.side == getattr(runtime, "active_side", None))
    is_not_activated = (unit.unit_id not in getattr(runtime, "activated_units", set()))

    if not (is_active_side and is_not_activated):
        return {
            "unit_id": unit.unit_id,
            "moves": [],
            "attacks": [],
            "abilities": [],
            "disabled": True
        }

    # -------------------------------------------------
    # ✅ TERRAIN CONFIG (CORRECTO)
    # -------------------------------------------------
    terrain_config = state.game_map.terrain_config

    # -------------------------------------------------
    # ✅ ACTION CATALOG
    # -------------------------------------------------
    catalog = ActionCatalog(
        state,
        unit,
        terrain_config=terrain_config
    )

    actions = catalog.actions()

    moves = []
    attacks = []

    # -------------------------------------------------
    # ✅ PROCESS ACTIONS (CORRECTO)
    # -------------------------------------------------
    for action in actions:

        if isinstance(action, MoveAction):
            if action.path:
                last = action.path[-1]
                moves.append({
                    "q": last.q,
                    "r": last.r
                })

        elif isinstance(action, AssaultAction):
            attacks.append({
                "type": "assault",
                "target_id": action.target_id
            })

        elif isinstance(action, RangedDirectAttack):
            attacks.append({
                "type": "ranged",
                "target_id": action.target_id
            })

    # -------------------------------------------------
    # ✅ RESULT (FUERA DEL LOOP)
    # -------------------------------------------------
    result = {
        "unit_id": unit.unit_id,
        "moves": moves,
        "attacks": attacks,
        "abilities": [],
        "disabled": False
    }

    # -------------------------------------------------
    # ✅ DEBUG
    # -------------------------------------------------
    print("[DEBUG][get_unit_actions]")
    print(json.dumps(result, indent=2))

    return result