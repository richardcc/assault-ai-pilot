from .progressive_reward import ProgressiveReward
from pathlib import Path
from assault_sim.config.reward_config import RewardConfig


class ShapedReward(ProgressiveReward):
    """Wrapper reward that composes ProgressiveReward and applies
    additional shaping: stronger penalty for zero-damage attacks and
    an extra bonus for clearly positive trades.
    """

    def __init__(
        self,
        rl_side=None,
        zero_damage_penalty: float | None = None,
        extra_good_trade_bonus: float | None = None,
        config: RewardConfig | None = None,
        config_path: Path | None = None,
    ):
        super().__init__(rl_side=rl_side, config=config, config_path=config_path)
        self.zero_damage_penalty = (
            self.cfg.shaped_zero_damage_penalty
            if zero_damage_penalty is None
            else float(zero_damage_penalty)
        )
        self.extra_good_trade_bonus = (
            self.cfg.shaped_good_trade_bonus
            if extra_good_trade_bonus is None
            else float(extra_good_trade_bonus)
        )

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
