from abc import ABC, abstractmethod


class BaseReward(ABC):
    """
    Base class for reward functions.

    Responsibilities:
    - Provide shared state tracking (VP, etc.)
    - Define compute() interface
    """

    def __init__(self, rl_side: str):
        self.rl_side = rl_side
        self.prev_vp = 0

    # -------------------------------------------------
    def reset(self, state):
        """
        Reset internal state at episode start.
        """

        if hasattr(state, "vp_tracker") and state.vp_tracker:
            self.prev_vp = state.vp_tracker.total_points
        else:
            self.prev_vp = 0

    # -------------------------------------------------
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
        """
        Compute reward for a transition.

        Must be implemented by subclasses.
        """
        pass
