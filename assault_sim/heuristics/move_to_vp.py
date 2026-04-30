from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.assault import AssaultAction
from assault_model.map.hex_utils import hex_distance


class MoveToVictoryPointHeuristic:
    """
    Moves units towards Victory Points defined by vp_tracker.conditions.
    Prioritizes Close Combat when available.
    """

    def choose_action(self, state):
        unit = state.active_unit
        actions = ActionCatalog(state).actions()

        if unit is None or not actions:
            return None

        # -------------------------------------------------
        # ✅ PRIORITY: CLOSE COMBAT
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, AssaultAction):
                return action

        vp_tracker = getattr(state, "vp_tracker", None)
        if not vp_tracker or not vp_tracker.conditions:
            return self._wait(actions)

        # -------------------------------------------------
        # ✅ Get VP positions via public API
        # -------------------------------------------------
        vp_positions = vp_tracker.conditions.get_positions()
        if not vp_positions:
            return self._wait(actions)

        # -------------------------------------------------
        # ✅ Nearest VP
        # -------------------------------------------------
        current_pos = unit.position
        target_vp = min(
            vp_positions,
            key=lambda p: hex_distance(current_pos, p)
        )

        best_action = None
        best_dist = hex_distance(current_pos, target_vp)

        for action in actions:
            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(action, "path", None)
            if not path:
                continue

            dest = path[-1]
            dest_pos = (dest.q, dest.r)

            d = hex_distance(dest_pos, target_vp)
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