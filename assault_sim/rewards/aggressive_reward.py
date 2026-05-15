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
        info = info or {}

        # -----------------------------
        # 1. VP
        # -----------------------------
        current_vp = next_state.vp_tracker.total_points if next_state.vp_tracker else 0
        reward += 4.0 * (current_vp - self.prev_vp)
        self.prev_vp = current_vp

        # -----------------------------
        # 2. OCUPACIÓN VP
        # -----------------------------
        if active and active.position and next_state.vp_tracker:
            for vp in next_state.vp_tracker.conditions.points:
                if (active.position.q, active.position.r) == vp.hex_coords:
                    reward += 0.8

        # -----------------------------
        # 3. ATAQUE (solo identificar)
        # -----------------------------
        action_name = action.__class__.__name__ if action else ""

        is_attack = (
            "Ranged" in action_name or
            "Assault" in action_name or
            "Close" in action_name
        )

        dmg = info.get("damage", 0)
        killed = info.get("defender_killed", False)

        reward += 0.5 * dmg

        if killed:
            reward += 3.0

        # -----------------------------
        # 4. DISTANCIA ENEMIGO
        # -----------------------------
        if pre_dist is not None and post_dist is not None:
            delta = pre_dist - post_dist
            reward += 0.6 * delta

            if delta < 0:
                reward -= 0.5

        # -----------------------------
        # 5. NO ATACAR EN RANGO
        # -----------------------------
        if not is_attack and pre_dist is not None:

            if pre_dist <= 3:
                reward -= 1.0

            if pre_dist <= 1:
                reward -= 2.0

        # -----------------------------
        # 6. DISTANCIA A VP
        # -----------------------------
        if next_state.vp_tracker:

            vp_points = next_state.vp_tracker.conditions.points

            if vp_points:

                def min_dist(units, vp_points):
                    return min(
                        hex_distance(u.position, vp.hex_coords)
                        for u in units
                        if u.position and u.alive
                        for vp in vp_points
                    )

                try:
                    pre_vp_dist = min_dist(state.units, vp_points)
                    post_vp_dist = min_dist(next_state.units, vp_points)

                    delta_vp = pre_vp_dist - post_vp_dist
                    reward += 0.3 * delta_vp

                except ValueError:
                    pass

        # -----------------------------
        # 7. WAIT
        # -----------------------------
        is_wait = isinstance(action, WaitAction)

        if is_wait:
            reward -= 0.3

        if is_wait:
            self.wait_streak = getattr(self, "wait_streak", 0) + 1
        else:
            self.wait_streak = 0

        if self.wait_streak >= 2:
            reward -= 0.2 * self.wait_streak

        # -----------------------------
        # 8. TIEMPO
        # -----------------------------
        reward -= 0.02

        # -----------------------------
        # 9. CLIP
        # -----------------------------
        reward = max(min(reward, 6.0), -6.0)

        return reward
