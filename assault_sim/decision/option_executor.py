from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


class OptionExecutor:
    """
    Executes a TacticalOption using heuristics.

    ✅ RESPONSABILIDAD:
    - traducir intención → acción
    - SIEMPRE pasar option a la heurística
    """

    def __init__(self, heuristic_controller):
        self.heuristic = heuristic_controller

    def execute(self, state, option: TacticalOption):
        """
        Execute ONE step of the given tactical option.
        """

        unit = state.active_unit

        if unit is None:
            return None

        # -------------------------------------------------
        # ✅ TODAS LAS OPCIONES VAN POR choose_action
        # -------------------------------------------------
        if option in (
            TacticalOption.ADVANCE,
            TacticalOption.FLANK,
            TacticalOption.ATTACK,
        ):
            return self.heuristic.choose_action(state, option)

        # -------------------------------------------------
        # HOLD
        # -------------------------------------------------
        if option == TacticalOption.HOLD:
            return WaitAction(unit.unit_id)

        # -------------------------------------------------
        # RETREAT
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:
            return self.heuristic.choose_action(state, option)

        # -------------------------------------------------
        # SAFETY
        # -------------------------------------------------
        return WaitAction(unit.unit_id)