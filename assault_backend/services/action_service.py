from assault_model.actions.movement import MoveAction
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.action_catalog import ActionCatalog


def get_unit_actions(env, unit):
    """
    Compute available actions for a unit and
    convert them to frontend-friendly JSON.
    """

    state = env.game_state

    # ✅ build catalog using real rules
    catalog = ActionCatalog(
        state,
        unit,
        terrain_config=env.config.terrain_config
    )

    actions = catalog.actions()

    moves = []
    attacks = []

    for action in actions:

        # -----------------------------
        # MOVE
        # -----------------------------
        if isinstance(action, MoveAction):
            if action.path:
                last = action.path[-1]
                moves.append({
                    "q": last.q,
                    "r": last.r
                })

        # -----------------------------
        # ASSAULT
        # -----------------------------
        elif isinstance(action, AssaultAction):
            attacks.append({
                "type": "assault",
                "target_id": action.target_id
            })

        # -----------------------------
        # RANGED
        # -----------------------------
        elif isinstance(action, RangedDirectAttack):
            attacks.append({
                "type": "ranged",
                "target_id": action.target_id
            })

    return {
        "unit_id": unit.unit_id,
        "moves": moves,
        "attacks": attacks,
        "abilities": []
    }