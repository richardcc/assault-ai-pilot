from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import hex_distance
from assault_sim.rl.tactical_options import TacticalOption
import random


class TacticalPathHeuristic:

    # -------------------------------------------------
    # ✅ NUEVA FIRMA (SIN active_unit)
    # -------------------------------------------------
    def choose_action(self, state, unit, option: TacticalOption):

        if unit is None or not unit.alive:
            return None

        actions = ActionCatalog(state, unit).actions()
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
        # ATTACK
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            ranged = self._attack_ranged(actions, state, unit)
            if ranged:
                return ranged
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
            ranged = self._attack_ranged(actions, state, unit)
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
            return self._move_closer(actions, unit, target)

        return self._wait(actions)

    # =================================================
    # RANGED
    # =================================================
    def _attack_ranged(self, actions, state, unit):

        best = None
        best_score = -999

        for a in actions:

            if a.action_type.category in (
                ActionCategory.MOVEMENT,
                ActionCategory.STATUS
            ):
                continue

            name = a.__class__.__name__
            if "Ranged" not in name:
                continue

            target_id = getattr(a, "target_id", None)
            if not target_id:
                continue

            target = next(
                (u for u in state.units if u.unit_id == target_id),
                None
            )

            if target is None or not target.alive:
                continue

            dist = hex_distance(unit.position, target.position)
            hp = getattr(target, "hp", 3)

            score = 0.0

            if hp == 1:
                score += 6.0
            elif hp == 2:
                score += 3.0

            score += max(0, 5 - dist)
            score += random.uniform(-0.2, 0.2)

            if score > best_score:
                best_score = score
                best = a

        return best

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
    def _wait(self, actions):
        for a in actions:
            if a.action_type.category == ActionCategory.STATUS:
                return a
        return actions[0]