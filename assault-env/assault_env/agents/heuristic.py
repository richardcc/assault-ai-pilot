class HeuristicAgent:
    """
    Simple rule-based agent for AssaultEnv.
    """

    def act(self, obs) -> int:
        # ✅ SAFETY: unwrap Gym-style (obs, info)
        if isinstance(obs, tuple):
            obs = obs[0]

        if obs.get("can_assault", False):
            return 2  # ASSAULT

        if not obs.get("in_enemy_zoc", False):
            return 1  # MOVE_FORWARD

        return 0  # WAIT
