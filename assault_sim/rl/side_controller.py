# assault_sim/rl/side_controller.py

class SideAwareController:
    """
    Dispatches control based on unit side.

    RL side -> RL policy
    Other side -> heuristic
    """

    def __init__(self, rl_controller, heuristic_controller, rl_side):
        self.rl_controller = rl_controller
        self.heuristic_controller = heuristic_controller
        self.rl_side = rl_side

    def choose_action(self, game_state, obs):
        """
        Parameters
        ----------
        game_state : GameState
            Full simulator state (active unit, rules, legal actions)

        obs : np.ndarray
            RL observation vector (input for policy net)
        """
        unit = game_state.active_unit
        if unit is None:
            return None

        if unit.side == self.rl_side:
            # ✅ RL controller needs BOTH game_state and obs
            return self.rl_controller.choose_action(game_state, obs)
        else:
            # ✅ Heuristic works directly on the game state
            return self.heuristic_controller.choose_action(game_state)