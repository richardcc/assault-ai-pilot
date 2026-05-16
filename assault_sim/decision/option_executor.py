from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack

from assault_sim.rl.tactical_options import TacticalOption


class OptionExecutor:
    """
    Executes a TacticalOption using RL-driven decisions.

    RESPONSABILIDAD:
    - Traducir intención → acción
    - Selección de objetivo → mejorada
    - Tipo de ataque → controlado por RL
    """

    def __init__(self, heuristic_controller):
        self.heuristic = heuristic_controller

    # -------------------------------------------------
    def execute(self, state, option: TacticalOption, attack_mode: int | None = None):

        unit = state.active_unit

        if unit is None:
            return None

        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            return self._execute_attack(state, unit, attack_mode)

        if option in (
            TacticalOption.ADVANCE,
            TacticalOption.FLANK,
            TacticalOption.RETREAT,
        ):
            return self.heuristic.choose_action(state, option)

        if option == TacticalOption.HOLD:
            return WaitAction(unit.unit_id)

        return WaitAction(unit.unit_id)

    # -------------------------------------------------
    def _execute_attack(self, state, unit, attack_mode):

        # ✅ fallback seguro
        if attack_mode is None:
            attack_mode = 0

        target = self._select_attack_target(state, unit, attack_mode)

        if target is None:
            return WaitAction(unit.unit_id)

        # ✅ INDIRECT
        if attack_mode == 1:
            return RangedIndirectAttack(
                unit_id=unit.unit_id,
                target_hex=target.position,
            )

        # ✅ DIRECT
        return RangedDirectAttack(
            unit_id=unit.unit_id,
            target_id=target.unit_id,
        )

    # -------------------------------------------------
    # ✅ TARGET SELECTION MEJORADO
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

            dist = self._distance(unit.position, e.position)

            hp = getattr(e, "hp", 3)

            score = 0.0

            # ----------------------------------------
            # 🎯 PRIORIDAD: MATAR
            # ----------------------------------------
            if hp == 1:
                score += 10.0
            elif hp == 2:
                score += 5.0

            # ----------------------------------------
            # 🎯 DAÑO POTENCIAL
            # ----------------------------------------
            score += (3 - hp) * 2.0

            # ----------------------------------------
            # 🎯 DISTANCIA SEGÚN MODE
            # ----------------------------------------
            if attack_mode == 1:
                # INDIRECT → prefiere targets lejanos
                score += min(dist, 6) * 1.2
            else:
                # DIRECT → prefiere targets cercanos
                score -= dist * 1.5

            # ----------------------------------------
            # 🎯 TARGET PELIGROSO
            # ----------------------------------------
            if hasattr(e.unit_type, "classification"):
                if e.unit_type.classification == "INDIRECT_FIRE_UNIT":
                    score += 4.0   # eliminar morteros 🚀

            # ----------------------------------------
            # 🎯 EVITAR TARGETS MALOS
            # ----------------------------------------
            if attack_mode == 1 and dist <= 2:
                score -= 5.0   # indirect en melee = malo

            if attack_mode == 0 and dist > 5:
                score -= 3.0   # direct a distancia = malo

            # ----------------------------------------
            if score > best_score:
                best_score = score
                best = e

        return best

    # -------------------------------------------------
    def _distance(self, a, b):
        dq = abs(a.q - b.q)
        dr = abs(a.r - b.r)
        return max(dq, dr)