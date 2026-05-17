from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import hex_distance

from assault_sim.rl.tactical_options import TacticalOption


class OptionExecutor:
    """
    Executes a TacticalOption using RL-driven decisions.
    """

    def __init__(self, heuristic_controller):
        self.heuristic = heuristic_controller  # ✅ temporal

    # -------------------------------------------------
    def execute(self, state, option: TacticalOption, attack_mode: int | None = None):

        unit = state.active_unit

        if unit is None:
            return None

        # -------------------------------------------------
        # ✅ ATTACK (ya en L2)
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            return self._execute_attack(state, unit, attack_mode)

        # -------------------------------------------------
        # ✅ ADVANCE (nuevo en L2)
        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self._move_closer(state, unit)

        # -------------------------------------------------
        # ✅ resto aún usa heuristic (por ahora)
        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return self._flank_move(state, unit)

        if option == TacticalOption.RETREAT:
            return self.heuristic.choose_action(state, option)
        

        # -------------------------------------------------
        if option == TacticalOption.HOLD:
            return WaitAction(unit.unit_id)

        return WaitAction(unit.unit_id)

    # -------------------------------------------------
    # ✅ ATTACK
    # -------------------------------------------------
    def _execute_attack(self, state, unit, attack_mode):

        if attack_mode is None:
            attack_mode = 0

        target = self._select_attack_target(state, unit, attack_mode)

        if target is None:
            return WaitAction(unit.unit_id)

        # INDIRECT
        if attack_mode == 1:
            return RangedIndirectAttack(
                unit_id=unit.unit_id,
                target_hex=target.position,
            )

        # DIRECT
        return RangedDirectAttack(
            unit_id=unit.unit_id,
            target_id=target.unit_id,
        )

    # -------------------------------------------------
    # ✅ TARGET SELECTION (migrado desde heuristic)
    # -------------------------------------------------
    def _select_attack_target(self, state, unit, attack_mode):

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return None

        best = None
        best_score = -999

        for e in enemies:

            dist = hex_distance(unit.position, e.position)
            hp = getattr(e, "hp", 3)

            score = 0.0

            # ✅ prioridad matar (igual que heuristic)
            if hp == 1:
                score += 6.0
            elif hp == 2:
                score += 3.0

            # ✅ distancia
            score += max(0, 5 - dist)

            if score > best_score:
                best_score = score
                best = e

        return best

    # -------------------------------------------------
    # ✅ MOVE CLOSER (migrado desde heuristic)
    # -------------------------------------------------
    def _move_closer(self, state, unit):

        actions = ActionCatalog(state).actions()

        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if not enemies:
            return WaitAction(unit.unit_id)

        # mismo target heuristic
        target = min(
            enemies,
            key=lambda e: hex_distance(unit.position, e.position)
        )

        best = None
        best_dist = hex_distance(unit.position, target.position)

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            d = hex_distance(path[-1], target.position)

            if d < best_dist:
                best_dist = d
                best = a

        return best or WaitAction(unit.unit_id)
    
    # -------------------------------------------------
    # ✅ FLANK = acercarse pero evitando frontal directo
    # -------------------------------------------------
    def _flank_move(self, state, unit):

        from assault_model.actions.action_catalog import ActionCatalog
        from assault_model.actions.action_category import ActionCategory

        actions = ActionCatalog(state).actions()

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

            # distancia al enemigo
            dist = hex_distance(new_pos, target.position)

            score = 0.0

            # ✅ queremos acercarnos
            score += max(0, 6 - dist)

            # ✅ pero no demasiado directo (evita melee inmediato)
            if dist <= 1:
                score -= 3.0

            # ✅ ligero sesgo lateral (rompe línea directa)
            # truco simple: penalizar quedarse en misma línea q/r
            if new_pos.q == unit.position.q or new_pos.r == unit.position.r:
                score -= 1.0

            if score > best_score:
                best_score = score
                best = a

        return best or self._move_closer(state, unit)