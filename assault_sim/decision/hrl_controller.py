# assault_sim/rl/hrl_controller.py

from assault_sim.rl.tactical_options import TacticalOption


class HRLController:
    """
    Hierarchical RL controller.

    Decides WHEN to select a new tactical option and
    delegates execution to heuristics.
    """

    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 5,
        TacticalOption.FLANK: 6,
        TacticalOption.ATTACK: 2,
        TacticalOption.HOLD: 1,
        TacticalOption.RETREAT: 3,
    }

    def __init__(self, option_policy, option_executor, rl_side):
        self.policy = option_policy
        self.executor = option_executor
        self.rl_side = rl_side

        self.current_option = None
        self.steps_remaining = 0

    def choose_action(self, state, obs):
        """
        Choose an engine action using HRL.
        """

        active = state.active_unit
        if active is None or active.side != self.rl_side:
            return None

        # Select a new option if needed
        if self.current_option is None or self.steps_remaining <= 0:
            self.current_option = self.policy.choose_option(obs)
            self.steps_remaining = self.OPTION_HORIZON[self.current_option]

        self.steps_remaining -= 1

        # Delegate execution to heuristics
        return self.executor.execute(
            self.current_option,
            state,
            active
        )
