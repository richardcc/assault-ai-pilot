from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


class OptionExecutor:
    """
    Executes a TacticalOption using existing heuristics.

    This class ADAPTS HRL intentions to the real heuristic API.
    It must NOT assume methods that do not exist.
    """

    def __init__(self, heuristic_controller):
        self.heuristic = heuristic_controller

    def execute(self, option: TacticalOption, state, unit):
        """
        Execute ONE step of the given tactical option.
        """

        # -------------------------------------------------
        # ADVANCE: create contact / move forward
        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self.heuristic.advance_towards_enemy(unit, state)

        # -------------------------------------------------
        # FLANK: currently reuse heuristic logic
        # (can be specialized later)
        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return self.heuristic.flank_best_position(unit, state)

        # -------------------------------------------------
        # ATTACK: defer to existing heuristic attack logic
        # (choose_action already prioritizes assault/ranged)
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            return self.heuristic.choose_action(state)

        # -------------------------------------------------
        # HOLD: explicit wait
        # -------------------------------------------------
        if option == TacticalOption.HOLD:
            return WaitAction(unit.unit_id)

        # -------------------------------------------------
        # RETREAT: move away from closest enemy
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:
            return self.heuristic.retreat(unit, state)

        # -------------------------------------------------
        # SAFETY FALLBACK
        # -------------------------------------------------
        return WaitAction(unit.unit_id)