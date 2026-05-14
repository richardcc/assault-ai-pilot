from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.map.hex_utils import hex_distance


class TacticalPathHeuristic:

    # -------------------------------------------------
    # MAIN HEURISTIC (FINAL VERSION)
    # -------------------------------------------------
    def choose_action(self, state):

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

        # objetivo principal
        closest_enemy = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        dist_to_enemy = hex_distance(unit.position, closest_enemy.position)

        # -------------------------------------------------
        # 1. RANGED (si puede disparar → hazlo)
        # -------------------------------------------------
        ranged_action = None

        for action in actions:
            if isinstance(action, RangedDirectAttack):
                ranged_action = action
                break

        if ranged_action:
            return ranged_action

        # -------------------------------------------------
        # 2. MOVIMIENTO INTELIGENTE (CLAVE)
        # -------------------------------------------------
        best_move = None
        best_dist = dist_to_enemy

        for action in actions:

            if action.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(action, "path", None)
            if not path:
                continue

            dest = path[-1]

            # distancia desde destino a enemigo
            d = hex_distance(dest, closest_enemy.position)

            # ✅ PRIORIDAD 1: entrar en el mismo hex → provoca assault
            if dest == closest_enemy.position:

                # opcional: solo si conviene (ejemplo básico)
                if unit.hp >= closest_enemy.hp or closest_enemy.hp <= 1:
                    return action

            # ✅ PRIORIDAD 2: acercarse
            if d < best_dist:
                best_dist = d
                best_move = action

            # ✅ PRIORIDAD 3: movimiento lateral (ANTI-FREEZE)
            elif best_move is None:
                best_move = action

        if best_move:
            return best_move

        # -------------------------------------------------
        # 3. FALLBACK
        # -------------------------------------------------
        return self._wait(actions)

    # -------------------------------------------------
    # HRL WRAPPERS
    # -------------------------------------------------
    def advance_towards_enemy(self, unit, state):
        return self.choose_action(state)

    def flank_best_position(self, unit, state):
        return self.choose_action(state)

    def retreat(self, unit, state):

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

            # alejarse
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