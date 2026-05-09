from abc import ABC, abstractmethod


class BaseReward(ABC):
    """
    Base class for all reward functions.
    """

    def __init__(self, rl_side: str):
        self.rl_side = rl_side
        self.prev_vp = 0
        self.prev_enemy_dist = None

    def reset(self, state):
        self.prev_vp = (
            state.vp_tracker.total_points
            if state.vp_tracker else 0
        )
        self.prev_enemy_dist = None

    @abstractmethod
    def compute(
        self,
        *,
        state,
        next_state,
        action,
        active,
        info,
        pre_dist,
        post_dist,
    ) -> float:
        pass