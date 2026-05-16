from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import hex_distance
from assault_sim.rl.tactical_options import TacticalOption
import random


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

        # =================================================
        # ✅ INDIRECT FIRE UNIT (MORTAR)
        # =================================================
        if unit.unit_type.classification == "INDIRECT_FIRE_UNIT":

            valid_targets = []

            for e in enemies:
                d = hex_distance(unit.position, e.position)
                if 3 <= d <= 8:
                    valid_targets.append((e, d))

            if valid_targets:
                target, _ = min(valid_targets, key=lambda x: x[1])

                for a in actions:
                    if (
                        hasattr(a, "target_id")
                        and a.target_id == target.unit_id
                        and hasattr(a, "attack_mode")
                        and a.attack_mode == "INDIRECT_FIRE"
                    ):
                        return a

            return self._wait(actions)

        # =================================================
        # NORMAL TARGET
        # =================================================
        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        dist = hex_distance(unit.position, target.position)

        # -------------------------------------------------
        # ATTACK
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:

            if dist <= 1:
                return self._attack_close(actions, target)

            if dist <= 2:
                melee = self._attack_close(actions, target)
                if melee:
                    return melee

            if dist <= 4:
                ranged = self._attack_ranged(actions, state=state, unit=unit)
                if ranged:
                    return ranged

                return self._move_closer(actions, unit, target)

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
                ranged = self._attack_ranged(actions, state=state, unit=unit)
                if ranged:
                    return ranged

                if dist <= 2:
                    return self._attack_close(actions, target)

            return self._wait(actions)

        # -------------------------------------------------
        # RETREAT
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:

            if dist <= 3:
                return self._wait(actions)

            return self._move_away(actions, unit, target)

        # -------------------------------------------------
        # FLANK
        # -------------------------------------------------
        if option == TacticalOption.FLANK:

            if dist <= 4:
                return self._move_closer(actions, unit, target)

            return self._move_closer_force(actions, unit, target)

        return self._wait(actions)

    # =================================================
    # 🔥 ✅ TARGET SCORING RANGED (CLAVE)
    # =================================================
    def _attack_ranged(self, actions, state=None, unit=None):

        best = None
        best_score = -999

        for a in actions:

            if a.action_type.category in (
                ActionCategory.MOVEMENT,
                ActionCategory.STATUS
            ):
                continue

            name = a.__class__.__name__
            if not ("Ranged" in name or "Shoot" in name):
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

            # ✅ PRIORIDAD: MATAR
            if hp == 1:
                score += 8.0
            elif hp == 2:
                score += 4.0

            # ✅ daño esperado
            score += max(0, 3 - hp) * 1.5

            # ✅ distancia
            if dist <= 3:
                score += 1.0
            elif dist <= 5:
                score += 0.5

            # ✅ target peligroso (mortars)
            if hasattr(target.unit_type, "classification"):
                if target.unit_type.classification == "INDIRECT_FIRE_UNIT":
                    score += 2.5

            # ✅ ruido controlado
            score += random.uniform(-0.3, 0.3)

            if score > best_score:
                best_score = score
                best = a

        return best

    # -------------------------------------------------
    # MOVEMENT
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

        return best or self._wait(actions)

    # -------------------------------------------------
    # MELEE
    # -------------------------------------------------
    def _attack_close(self, actions, enemy):

        for a in actions:
            if "Assault" in a.__class__.__name__:
                return a

        for a in actions:
            if a.action_type.category not in (
                ActionCategory.MOVEMENT,
                ActionCategory.STATUS
            ):
                if "Ranged" not in a.__class__.__name__:
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