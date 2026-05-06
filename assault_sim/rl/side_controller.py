# assault_sim/rl/side_controller.py

class SideAwareController:
    """
    Dispatches control based on unit side.

    Example:
      GE -> RL policy
      US -> heuristic
    """

    def __init__(self, rl_controller, heuristic_controller, rl_side):
        self.rl_controller = rl_controller
        self.heuristic_controller = heuristic_controller
        self.rl_side = rl_side

    def choose_action(self, state):
        unit = state.active_unit
        if unit is None:
            return None

        if unit.side == self.rl_side:
            return self.rl_controller.choose_action(state)
        else:
            return self.heuristic_controller.choose_action(state)