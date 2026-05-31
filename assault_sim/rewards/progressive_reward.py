from .base_reward import BaseReward
from assault_model.actions.status import WaitAction


class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None):
        super().__init__(rl_side)
        self.rl_side = rl_side
        self.last_action = None

        # -------------------------------
        # METRICS (DEBUG / ANALYTICS)
        # -------------------------------
        self.trade_sum = 0.0
        self.trade_count = 0

        self.bad_attacks = 0
        self.total_attacks = 0

        self.damage_given_total = 0
        self.damage_taken_total = 0

    # -------------------------------------------------
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

        info = info or {}
        reward = 0.0

        # -------------------------------
        # CORE DATA
        # -------------------------------
        damage = info.get("rl_damage", 0)
        damage_taken = info.get("enemy_damage", 0)
        killed = info.get("rl_kills", 0) > 0

        action_class = info.get("action_class", "")
        l2 = info.get("l2_option", "")

        is_attack = "ATTACK" in action_class.upper()

        # =================================================
        # METRICS TRACKING (no reward impact)
        # =================================================
        self.damage_given_total += damage
        self.damage_taken_total += damage_taken

        trade = damage - damage_taken

        if is_attack:
            self.trade_sum += trade
            self.trade_count += 1

            if damage_taken > damage:
                self.bad_attacks += 1

            self.total_attacks += 1

        # =================================================
        # 🔥 CORE: COMBAT QUALITY (balanced)
        # =================================================
        if is_attack:

            # Main signal (stable scaling)
            reward += trade * 1.0

            # Penalize bad trades
            if trade < 0:
                reward -= 0.5

            # Reward good trades (controlled)
            elif trade > 0:
                reward += 0.4 + (trade * 0.25)

            # Avoid useless attacks
            if damage == 0:
                reward -= 0.4

            # 🔥 small base cost to attack (encourage selectivity)
            reward -= 0.1

        else:
            # Reward avoiding bad combat
            if trade < 0:
                reward += 0.2

        # =================================================
        # ✅ KILL
        # =================================================
        if killed:
            reward += 3.0

        # =================================================
        # ✅ POSITIONING
        # =================================================
        if pre_dist is not None and post_dist is not None:

            if post_dist < pre_dist:
                reward += 0.05

            if post_dist <= 2:
                reward += 0.05

        # =================================================
        # ✅ RETREAT (important under disadvantage)
        # =================================================
        if l2 == "RETREAT":

            reward += 0.6

            if damage_taken == 0:
                reward += 0.6

        # =================================================
        # ✅ PASSIVITY CONTROL
        # =================================================
        if l2 == "HOLD" and not is_attack:
            reward -= 0.15

        # =================================================
        # ✅ PRESSURE CONTROL (forces decisions)
        # =================================================
        if (
            pre_dist is not None
            and pre_dist <= 3
            and not is_attack
            and l2 != "RETREAT"
        ):
            reward -= 0.3

        # =================================================
        # ✅ ACTION PENALTIES
        # =================================================
        if isinstance(action, WaitAction):
            reward -= 0.25

        if self.last_action == action_class:
            reward -= 0.05

        self.last_action = action_class

        # =================================================
        # ✅ OBJECTIVES (VP)
        # =================================================
        if hasattr(state, "vp_tracker") and state.vp_tracker:
            if hasattr(next_state, "vp_tracker") and next_state.vp_tracker:

                prev_vp = state.vp_tracker.score.get(self.rl_side, 0)
                new_vp = next_state.vp_tracker.score.get(self.rl_side, 0)

                reward += (new_vp - prev_vp) * 1.5

        # =================================================
        # ✅ ENDGAME
        # =================================================
        if getattr(next_state, "done", False):
            winner = getattr(next_state, "winner", None)

            if winner == self.rl_side:
                reward += 5.0
            elif winner is not None:
                reward -= 5.0

        # =================================================
        # ✅ TIME PENALTY
        # =================================================
        reward -= 0.02

        return max(min(reward, 10.0), -10.0)