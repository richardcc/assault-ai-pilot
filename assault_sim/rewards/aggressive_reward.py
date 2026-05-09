from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import hex_distance
from .base_reward import BaseReward


class AggressiveReward(BaseReward):
    def compute(
        self,
        *,
        state,
        next_state,
        action,
        active,
        info,
        pre_dist,
        post_dist
    ) -> float:

        reward = 0.0

        # --- VP delta ---
        current_vp = next_state.vp_tracker.total_points if next_state.vp_tracker else 0
        reward += current_vp - self.prev_vp
        self.prev_vp = current_vp

        # --- detect attack ---
        action_name = action.__class__.__name__ if action else ""
        is_attack = "Ranged" in action_name or "Close" in action_name

        if is_attack:
            reward += 0.3

        dmg = info.get("damage", 0) if isinstance(info, dict) else 0
        killed = info.get("defender_killed", False) if isinstance(info, dict) else False
        sector = info.get("sector") if isinstance(info, dict) else None

        reward += 0.6 * dmg
        if killed:
            reward += 4.0

        if sector in ("FLANK", "FLANK_LEFT", "FLANK_RIGHT"):
            reward += 0.4
        if sector == "REAR":
            reward += 0.7

        if pre_dist is not None and post_dist is not None:
            delta = pre_dist - post_dist
            reward += 0.15 * delta
            if delta < 0:
                reward -= 0.15
            self.prev_enemy_dist = post_dist

        if isinstance(action, WaitAction) and pre_dist is not None:
            reward -= 0.1

        return reward