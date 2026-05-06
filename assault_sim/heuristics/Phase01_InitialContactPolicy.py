from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.assault import AssaultAction
from assault_model.map.hex_utils import hex_distance


class Phase01_InitialContactPolicy:
    """
    Phase 01 — Initial Contact Policy

    Purpose:
    - Guarantee activity (avoid WAIT)
    - Guarantee inevitable contact
    - Teach only: action → consequence → VP

    This policy is deliberately non-tactical.
    """

    def choose_action(self, state):
        unit = state.active_unit

        # Safety guard
        if unit is None or not unit.alive:
            return None

        # Get all legal actions
        actions = ActionCatalog(state).actions()

        if not actions:
            return None

        # -------------------------------------------------
        # 1. ABSOLUTE PRIORITY: ASSAULT IF POSSIBLE
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, AssaultAction):
                return action

        # -------------------------------------------------
        # 2. SELECT TARGET (VP FIRST, ENEMY AS FALLBACK)
        # -------------------------------------------------
        target_hex = self._select_target_hex(state, unit)

        if target_hex is None:
            return self._wait_action(actions)

        # -------------------------------------------------
        # 3. MOVE TOWARDS TARGET (GREEDY DISTANCE REDUCTION)
        # -------------------------------------------------
        best_action = None
        best_distance = hex_distance(unit.position, target_hex)

        for action in actions:
            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(action, "path", None)
            if not path:
                continue

            destination = path[-1]
            distance = hex_distance(destination, target_hex)

            if distance < best_distance:
                best_distance = distance
                best_action = action

        if best_action is not None:
            return best_action

        # -------------------------------------------------
        # 4. FALLBACK: WAIT (ONLY IF NO BETTER OPTION EXISTS)
        # -------------------------------------------------
        return self._wait_action(actions)

    # =====================================================
    # Helpers
    # =====================================================

    def _select_target_hex(self, state, unit):
        """
        Target selection logic for Phase 01.

        Priority:
        1. Victory Point hex
        2. Closest enemy unit
        """

        # --- 1. Victory Points ---
        vp_tracker = getattr(state, "vp_tracker", None)
        if vp_tracker and vp_tracker.conditions:
            vp_positions = vp_tracker.conditions.get_positions()
            if vp_positions:
                return min(
                    vp_positions,
                    key=lambda vp: hex_distance(unit.position, vp)
                )

        # --- 2. Closest enemy unit ---
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if enemies:
            closest_enemy = min(
                enemies,
                key=lambda e: hex_distance(unit.position, e.position)
            )
            return closest_enemy.position

        return None

    def _wait_action(self, actions):
        """
        Return a WAIT / STATUS action if available.
        Used only as a last resort.
        """
        for action in actions:
            if action.action_type.category == ActionCategory.STATUS:
                return action

        # Absolute fallback (should rarely happen)
        return actions[0]