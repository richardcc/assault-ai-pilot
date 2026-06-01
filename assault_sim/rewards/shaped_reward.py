from .progressive_reward import ProgressiveReward


class ShapedReward(ProgressiveReward):
    """Wrapper reward that composes ProgressiveReward and applies
    additional shaping: stronger penalty for zero-damage attacks and
    an extra bonus for clearly positive trades.
    """

    def __init__(self, rl_side=None, zero_damage_penalty=0.6, extra_good_trade_bonus=0.2):
        super().__init__(rl_side=rl_side)
        self.zero_damage_penalty = zero_damage_penalty
        self.extra_good_trade_bonus = extra_good_trade_bonus

    def compute(self, *args, **kwargs):
        # base reward
        reward = super().compute(*args, **kwargs)

        info = kwargs.get("info") or (args[3] if len(args) > 3 else {})
        damage = info.get("rl_damage", 0)
        damage_taken = info.get("enemy_damage", 0)

        trade = damage - damage_taken

        # stronger penalty for zero-damage attacks
        if trade == 0 and damage == 0 and info.get("is_wait") is False:
            reward -= self.zero_damage_penalty

        # extra bonus for clear good trades
        if trade > 0:
            reward += self.extra_good_trade_bonus

        return reward
