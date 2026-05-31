from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import hex_distance

from assault_sim.rl.tactical_options import TacticalOption

from assault_model.map.terrain_config import terrain_config


class OptionExecutor:

    def __init__(self, heuristic_controller):
        self.heuristic = heuristic_controller

    # -------------------------------------------------
    def execute(
        self,
        state,
        unit,
        option: TacticalOption,
        attack_mode: int | None = None
    ):

        if unit is None:
            return WaitAction("SYSTEM")

        # -------------------------------------------------
        # ✅ ATTACK
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            return self._execute_attack(state, unit, attack_mode)

        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self._move_closer(state, unit)

        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return self._flank_move(state, unit)

        # -------------------------------------------------
        # ✅ RETREAT (NO ATAQUE)
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:

            action = self.heuristic.choose_action(state, unit, option)

            # bloquear ataques
            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                return WaitAction(unit.unit_id)

            return action or WaitAction(unit.unit_id)

        # -------------------------------------------------
        # ✅ HOLD (MEJORADO)
        # -------------------------------------------------
        if option == TacticalOption.HOLD:

            actions = ActionCatalog(state, unit, terrain_config).actions()

            attacks = [
                a for a in actions
                if isinstance(a, RangedDirectAttack)
            ]

            if attacks:
                return self._best_attack(attacks)  # ✅ CAMBIO CLAVE

            return WaitAction(unit.unit_id)

        return WaitAction(unit.unit_id)

    # -------------------------------------------------
    # ✅ ATTACK (MEJORADO)
    # -------------------------------------------------
    def _execute_attack(self, state, unit, attack_mode):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        attacks = [
            a for a in actions
            if isinstance(a, (RangedDirectAttack, RangedIndirectAttack))
        ]

        if not attacks:
            return self._move_closer(state, unit)

        return self._best_attack(attacks)  # ✅ CAMBIO CLAVE

    # -------------------------------------------------
    def _move_closer(self, state, unit):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return WaitAction(unit.unit_id)

        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best = None
        best_dist = None  # ✅ fix implícito seguro

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], target.position)

            if best is None or d <= best_dist:
                best = a
                best_dist = d

        return best or WaitAction(unit.unit_id)

    # -------------------------------------------------
    def _flank_move(self, state, unit):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return WaitAction(unit.unit_id)

        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best = None
        best_score = -999

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            dist = hex_distance(new_pos, target.position)

            score = max(0, 6 - dist)

            if score > best_score:
                best_score = score
                best = a

        return best or self._move_closer(state, unit)

    # -------------------------------------------------
    # ✅ NUEVO: SELECCIÓN INTELIGENTE DE TARGET
    # -------------------------------------------------
    def _best_attack(self, attacks):

        best = None
        best_score = float("-inf")

        for a in attacks:
            target = getattr(a, "target", None)

            score = 0

            if target is not None:

                hp = getattr(target, "hp", 10)

                # ✅ prioriza enemigos débiles
                score += (10 - hp) * 5

                # ✅ bonus por kill
                if hp <= 1:
                    score += 100

                # ✅ evita targets con mucha vida
                score -= hp * 2

            # pequeño sesgo ofensivo
            score += 5

            if score > best_score:
                best_score = score
                best = a

        return best