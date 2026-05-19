import random
from assault_sim.rl.tactical_options import TacticalOption


class RLvsHeuristicController:

    def __init__(self, rl_side, hrl_controller, heuristic, executor):
        self.rl_side = rl_side
        self.hrl_controller = hrl_controller
        self.heuristic = heuristic
        self.executor = executor

    def act(self, state, side, unit, obs):

        if side == self.rl_side:
            return self.hrl_controller.choose_action(state, unit, obs)

        # puedes usar heuristic directo o executor
        return self.heuristic.choose_action(
            state, unit, TacticalOption.ATTACK
        )