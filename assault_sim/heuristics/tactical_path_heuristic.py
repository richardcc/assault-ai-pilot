from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.assault import AssaultAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.map.hex_utils import hex_distance


class TacticalPathHeuristic:
    """
    Tactical heuristic adapted to support HRL.

    Core method:
    - choose_action(state): unchanged, legacy-safe

    Additional lightweight wrappers:
    - advance_towards_enemy
    - flank_best_position
    - retreat
    """

    # -------------------------------------------------
    # MAIN HEURISTIC (UNCHANGED)
    # -------------------------------------------------
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
        # 2. PRIORITY: RANGED FIRE
        # -------------------------------------------------
        for action in actions:
            if isinstance(action, RangedDirectAttack):
                return action

        # -------------------------------------------------
        # 3. CREATE CONTACT (ANTI-PASSIVE)
        # -------------------------------------------------
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if enemies:
            closest_enemy = min(
                enemies,
                key=lambda e: hex_distance(unit.position, e.position)
            )

            # Move towards enemy to create interaction
            best_move = None
            best_dist = hex_distance(unit.position, closest_enemy.position)

            for action in actions:
                if action.action_type.category != ActionCategory.MOVEMENT:
                    continue

                path = getattr(action, "path", None)
                if not path:
                    continue

                dest = path[-1]
                d = hex_distance(dest, closest_enemy.position)

                if d < best_dist:
                    best_dist = d
                    best_move = action

            if best_move:
                return best_move

        # -------------------------------------------------
        # 4. FALLBACK: WAIT
        # -------------------------------------------------
        return self._wait(actions)

    # -------------------------------------------------
    # HRL WRAPPERS (NEW, MINIMAL)
    # -------------------------------------------------
    def advance_towards_enemy(self, unit, state):
        """
        HRL ADVANCE:
        Reuse existing heuristic logic to create contact.
        """
        return self.choose_action(state)

    def flank_best_position(self, unit, state):
        """
        HRL FLANK:
        For now, reuse choose_action.
        Later, flank-specific logic can be added safely.
        """
        return self.choose_action(state)

    def retreat(self, unit, state):
        """
        HRL RETREAT:
        Move away from closest enemy.
        """
        actions = ActionCatalog(state).actions()
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return self._wait(actions)

        closest_enemy = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best_move = None
        best_dist = hex_distance(unit.position, closest_enemy.position)

        for action in actions:
            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(action, "path", None)
            if not path:
                continue

            dest = path[-1]
            d = hex_distance(dest, closest_enemy.position)

            # Retreat = increase distance
            if d > best_dist:
                best_dist = d
                best_move = action

        if best_move:
            return best_move

        return self._wait(actions)

    # -------------------------------------------------
    # INTERNAL
    # -------------------------------------------------
    def _wait(self, actions):
        for a in actions:
            if a.action_type.category == ActionCategory.STATUS:
                return a
        return actions[0]
