from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.map.hex_utils import hex_distance
from assault_model.map.terrain_config import terrain_config

from assault_sim.rl.tactical_options import TacticalOption


class TacticalPathHeuristic:

    def choose_action(self, state, unit, option):

        if unit is None:
            return None

        # ------------------------------------------
        # ✅ OBTENER ACCIONES VÁLIDAS (FIX CLAVE)
        # ------------------------------------------
        actions = ActionCatalog(
            state,
            unit,
            terrain_config
        ).actions()

        if not actions:
            return None

        # ------------------------------------------
        # ✅ FILTRAR TIPOS
        # ------------------------------------------
        attacks = [
            a for a in actions
            if isinstance(a, RangedDirectAttack)
        ]

        moves = [
            a for a in actions
            if getattr(a.action_type, "category", None).name == "MOVEMENT"
        ]

        # ------------------------------------------
        # ✅ OPCIÓN: ATTACK
        # ------------------------------------------
        if option == TacticalOption.ATTACK:

            if attacks:
                return attacks[0]

            return self._move_closer(state, unit, moves)

        # ------------------------------------------
        # ✅ OPCIÓN: ADVANCE
        # ------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self._move_closer(state, unit, moves)

        # ------------------------------------------
        # ✅ OPCIÓN: FLANK
        # ------------------------------------------
        if option == TacticalOption.FLANK:
            return self._flank_move(state, unit, moves)

        # ------------------------------------------
        # ✅ OPCIÓN: HOLD
        # ------------------------------------------
        if option == TacticalOption.HOLD:

            if attacks:
                return attacks[0]

            return None

        # ------------------------------------------
        # ✅ OPCIÓN: RETREAT
        # ------------------------------------------
        if option == TacticalOption.RETREAT:
            return self._retreat(state, unit, moves)

        return None

    # -------------------------------------------------
    def _move_closer(self, state, unit, moves):

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies or not moves:
            return None

        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best = None
        best_dist = float("inf")

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], target.position)

            if d < best_dist:
                best_dist = d
                best = m

        return best

    # -------------------------------------------------
    def _flank_move(self, state, unit, moves):

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies or not moves:
            return None

        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best = None
        best_score = -999

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            dist = hex_distance(new_pos, target.position)

            score = max(0, 6 - dist)

            if score > best_score:
                best_score = score
                best = m

        return best

    # -------------------------------------------------
    def _retreat(self, state, unit, moves):

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies or not moves:
            return None

        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best = None
        best_dist = -1

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], target.position)

            if d > best_dist:
                best_dist = d
                best = m

        return best
