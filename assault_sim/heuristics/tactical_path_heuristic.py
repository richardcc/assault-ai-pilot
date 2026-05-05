from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.assault import AssaultAction
from assault_model.map.hex_utils import hex_distance


class TacticalPathHeuristic:
    """
    Tactical heuristic adapted to the new architecture.

    - Movement is 1 hex (MovementRules).
    - ActionCatalog provides all legal actions.
    - This heuristic only chooses, never invents actions.
    """

    def choose_action(self, state):
        unit = state.active_unit
        if unit is None or not unit.alive:
            return None

        actions = ActionCatalog(state).actions()

        # -------------------------------------------------
        # 1. PRIORITY: ASSAULT
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, AssaultAction):
                return action

        # -------------------------------------------------
        # 2. VICTORY POINTS (FIXED)
        # -------------------------------------------------
        vp_tracker = state.vp_tracker
        if not vp_tracker or not vp_tracker.conditions:
            return self._wait(actions)

        # ✅ FIX: extract VP positions correctly
        vp_positions = [
            vp.hex_coords for vp in vp_tracker.conditions.points
        ]
        if not vp_positions:
            return self._wait(actions)

        current_pos = unit.position
        target_vp = min(
            vp_positions,
            key=lambda vp: hex_distance(current_pos, vp)
        )

        best_action = None
        best_dist = hex_distance(current_pos, target_vp)

        # -------------------------------------------------
        # 3. CHOOSE BEST MOVE ACTION
        # -------------------------------------------------
        for action in actions:
            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(action, "path", None)
            if not path:
                continue

            dest = path[-1]  # HexCoord
            d = hex_distance(dest, target_vp)

            if d < best_dist:
                best_dist = d
                best_action = action

        if best_action:
            return best_action

        return self._wait(actions)

    def _wait(self, actions):
        for a in actions:
            if a.action_type.category == ActionCategory.STATUS:
                return a
        return actions[0]