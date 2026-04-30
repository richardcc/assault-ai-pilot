from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import hex_distance


class HeuristicBase:
    """
    Heuristic that moves units TOWARDS the nearest enemy.
    """

    # unit_id -> previous position (written by runtime)
    previous_position = {}

    @staticmethod
    def choose_action(game_state):
        actions = ActionCatalog(game_state).actions()
        unit = game_state.active_unit

        # Safety
        if unit is None or not actions:
            return None

        unit_id = unit.unit_id
        current_pos = unit.position
        prev_pos = HeuristicBase.previous_position.get(unit_id)

        # ---------------------------------
        # 1️⃣ Find enemies
        # ---------------------------------
        enemies = [u for u in game_state.units if u.side != unit.side]

        if not enemies:
            for action in actions:
                if action.action_type.category == ActionCategory.STATUS:
                    return action
            return actions[0]

        # ---------------------------------
        # 2️⃣ Nearest enemy
        # ---------------------------------
        nearest_enemy = min(
            enemies,
            key=lambda e: hex_distance(current_pos, e.position),
        )

        # ---------------------------------
        # 3️⃣ Prefer combat if available
        # ---------------------------------
        for action in actions:
            if action.action_type.category == ActionCategory.COMBAT:
                return action

        # ---------------------------------
        # 4️⃣ Move closer
        # ---------------------------------
        best_action = None
        best_dist = hex_distance(current_pos, nearest_enemy.position)

        for action in actions:
            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            # ✅ MoveAction uses `path`, not `payload`
            path = getattr(action, "path", None)
            if not path:
                continue

            dest = path[-1]
            dest_pos = (dest.q, dest.r)

            # Avoid immediate return
            if prev_pos is not None and dest_pos == prev_pos:
                continue

            d = hex_distance(dest_pos, nearest_enemy.position)
            if d < best_dist:
                best_dist = d
                best_action = action

        if best_action:
            return best_action

        # ---------------------------------
        # 5️⃣ Wait
        # ---------------------------------
        for action in actions:
            if action.action_type.category == ActionCategory.STATUS:
                return action

        return actions[0]