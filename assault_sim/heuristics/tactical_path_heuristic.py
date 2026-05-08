from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.map.hex_utils import hex_distance


class TacticalPathHeuristic:
    """
    Tactical heuristic adapted to the new architecture.

    PURPOSE:
    - Act as a stable, non-learning opponent
    - PRIORITIZE REAL COMBAT when possible
    - AVOID passive VP blocking that prevents interaction

    PRIORITY ORDER:
    1. ASSAULT (if in contact)
    2. RANGED FIRE (if line of sight exists)
    3. MOVE TO CREATE CONTACT (anti-VP camping)
    4. MOVE TOWARD VP
    5. WAIT (last resort)
    """

    def choose_action(self, state):
        unit = state.active_unit
        if unit is None or not unit.alive:
            return None

        actions = ActionCatalog(state).actions()
        if not actions:
            return None

        # -------------------------------------------------
        # 1. ABSOLUTE PRIORITY: ASSAULT
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, AssaultAction):
                return action

        # -------------------------------------------------
        # 2. PRIORITY: RANGED FIRE (REAL COMBAT)
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, RangedDirectAttack):
                return action

        # -------------------------------------------------
        # 3. ANTI-PASSIVE VP CAMPING
        #    If holding VP and enemy is nearby,
        #    MOVE to seek line of sight instead of WAIT
        # -------------------------------------------------
        vp_tracker = state.vp_tracker
        vp_positions = []

        if vp_tracker and vp_tracker.conditions:
            vp_positions = [vp.hex_coords for vp in vp_tracker.conditions.points]

        if unit.position in vp_positions:
            enemies = [
                u for u in state.units
                if u.side != unit.side and u.alive
            ]

            if enemies:
                closest_enemy = min(
                    enemies,
                    key=lambda e: hex_distance(unit.position, e.position)
                )

                # Enemy nearby → move to create interaction
                if hex_distance(unit.position, closest_enemy.position) <= 3:
                    for action in actions:
                        if action.action_type.category == ActionCategory.MOVEMENT:
                            return action

        # -------------------------------------------------
        # 4. MOVE TOWARD VP (STANDARD LOGIC)
        # -------------------------------------------------
        if not vp_positions:
            return self._wait(actions)

        current_pos = unit.position
        target_vp = min(
            vp_positions,
            key=lambda vp: hex_distance(current_pos, vp)
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
            d = hex_distance(dest, target_vp)

            if d < best_dist:
                best_dist = d
                best_action = action

        if best_action:
            return best_action

        # -------------------------------------------------
        # 5. FALLBACK: WAIT
        # -------------------------------------------------
        return self._wait(actions)

    def _wait(self, actions):
        for a in actions:
            if a.action_type.category == ActionCategory.STATUS:
                return a
        return actions[0]