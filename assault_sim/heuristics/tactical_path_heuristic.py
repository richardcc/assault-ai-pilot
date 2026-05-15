from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import hex_distance
from assault_sim.rl.tactical_options import TacticalOption


class TacticalPathHeuristic:

    def choose_action(self, state, option: TacticalOption):

        unit = state.active_unit
        if unit is None or not unit.alive:
            return None

        actions = ActionCatalog(state).actions()
        if not actions:
            return None

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return self._wait(actions)

        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        dist = hex_distance(unit.position, target.position)

        # -------------------------------------------------
        # ✅ ✅ ✅ ATTACK (FIX REAL)
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:

            # 🔴 1. SI ESTÁ ADYACENTE → MELEE SIEMPRE
            if dist <= 1:
                return self._attack_close(actions, target)

            # 🟡 2. DISTANCIA MEDIA → RANGED
            if dist <= 3:
                ranged = self._attack_ranged(actions)
                if ranged:
                    return ranged

            # 🟢 3. LEJOS → MOVER
            return self._move_closer(actions, unit, target)

        # -------------------------------------------------
        # ADVANCE
        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self._move_closer(actions, unit, target)

        # -------------------------------------------------
        # HOLD
        # -------------------------------------------------
        if option == TacticalOption.HOLD:
            if dist <= 3:
                ranged = self._attack_ranged(actions)
                if ranged:
                    return ranged
            return self._wait(actions)

        # -------------------------------------------------
        # RETREAT
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:
            return self._move_away(actions, unit, target)

        # -------------------------------------------------
        # FLANK
        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return self._move_closer_force(actions, unit, target)

        return self._wait(actions)

    # -------------------------------------------------
    # ✅ ATAQUE RANGED
    # -------------------------------------------------
    def _attack_ranged(self, actions):
        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT \
               and a.action_type.category != ActionCategory.STATUS:

                name = a.__class__.__name__

                if "Ranged" in name or "Shoot" in name:
                    return a

        return None

    # -------------------------------------------------
    # MOVIMIENTO
    # -------------------------------------------------
    def _move_closer(self, actions, unit, enemy):

        best = None
        best_dist = hex_distance(unit.position, enemy.position)

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], enemy.position)

            if d < best_dist:
                best_dist = d
                best = a

        return best or self._wait(actions)

    def _move_closer_force(self, actions, unit, enemy):

        best = None
        best_dist = hex_distance(unit.position, enemy.position)

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], enemy.position)

            if d < best_dist:
                best_dist = d
                best = a
            elif best is None and d <= best_dist:
                best = a

        return best or self._wait(actions)

    # -------------------------------------------------
    # ✅ ✅ ✅ MELEE REAL (FIX IMPORTANTE)
    # -------------------------------------------------
    def _attack_close(self, actions, enemy):

        # ✅ PRIORIDAD → acciones melee explícitas
        for a in actions:
            name = a.__class__.__name__

            if "Assault" in name or "Close" in name:
                return a

        # ✅ fallback ofensivo (evitar ranged si hay otra cosa)
        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT \
               and a.action_type.category != ActionCategory.STATUS:

                name = a.__class__.__name__
                if not ("Ranged" in name):
                    return a

        return self._wait(actions)

    # -------------------------------------------------
    # RETREAT
    # -------------------------------------------------
    def _move_away(self, actions, unit, enemy):

        best = None
        best_dist = hex_distance(unit.position, enemy.position)

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], enemy.position)

            if d > best_dist:
                best_dist = d
                best = a

        return best or self._wait(actions)

    # -------------------------------------------------
    # WAIT
    # -------------------------------------------------
    def _wait(self, actions):
        for a in actions:
            if a.action_type.category == ActionCategory.STATUS:
                return a
        return actions[0]