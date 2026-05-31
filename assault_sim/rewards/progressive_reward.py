from .base_reward import BaseReward
from assault_model.actions.status import WaitAction


class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None):
        super().__init__(rl_side)
        self.rl_side = rl_side
        self.last_action = None

        # =================================================
        # ✅ METRICS (COMBAT INTELLIGENCE)
        # =================================================
        self.trade_sum = 0.0
        self.trade_count = 0

        self.bad_attacks = 0
        self.total_attacks = 0

        self.damage_given_total = 0
        self.damage_taken_total = 0

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

        # -------------------------------------------------
        # DATA
        # -------------------------------------------------
        damage = info.get("rl_damage", 0)
        damage_taken = info.get("enemy_damage", 0)
        killed = info.get("rl_kills", 0) > 0

        action_class = info.get("action_class", "")
        action_upper = action_class.upper()

        l2 = info.get("l2_option", "")
        is_attack = "ATTACK" in action_upper

        # =================================================
        # ✅ BASE REWARD
        # =================================================
        if l2 == "FLANK":
            if pre_dist is not None and pre_dist <= 3:
                reward += 0.5
            else:
                reward += 0.1

        elif l2 == "RETREAT":
            reward += 1.0

        # =================================================
        # ✅ DAMAGE
        # =================================================
        reward += damage * 0.8
        reward -= damage_taken * 0.8

        if damage > damage_taken:
            reward += 0.2

        if damage >= 2 and damage_taken == 0:
            reward += 0.4

        if damage_taken == 0 and damage > 0:
            reward += 0.3

        # =================================================
        # ✅ METRICS LOGGING (NO afecta al reward)
        # =================================================
        self.damage_given_total += damage
        self.damage_taken_total += damage_taken

        if is_attack:
            trade = damage - damage_taken

            self.trade_sum += trade
            self.trade_count += 1

            if damage_taken > damage:
                self.bad_attacks += 1

            self.total_attacks += 1

        # =================================================
        # 🔥 COMBAT INTELLIGENCE (PHASE 2.5 FINAL)
        # =================================================
        if is_attack:

            trade = damage - damage_taken

            # ✅ señal principal (mantener)
            reward += trade * 0.6

            # ✅ castigo ligero (NO bloquear comportamiento)
            if trade < 0:
                reward -= 0.2   # 🔥 BAJADO más

            # ✅ incentivo por buen ataque
            elif trade > 0:
                reward += 0.25

        # =================================================
        # ✅ ATTACK (AJUSTADO FINAL)
        # =================================================
        if is_attack:

            # ✅ incentivo a participar (IMPORTANTE)
            reward += 0.15   # 🔥 SUBIDO (era 0.1)

            if damage > 0:
                reward += 0.15
            else:
                reward -= 0.5   # 🔽 ligeramente

            # ❌ ELIMINAR ESTA LÍNEA (DOBLE PENALIZACIÓN)
            # if damage_taken > damage:
            #     reward -= 0.5

        # =================================================
        # ✅ KILL
        # =================================================
        if killed:
            reward += 4.0

        # =================================================
        # ✅ POSITION
        # =================================================
        if pre_dist is not None and post_dist is not None:

            if post_dist < pre_dist:
                reward += 0.05

            if post_dist <= 2:
                reward += 0.1

        # =================================================
        # ✅ HOLD
        # =================================================
        if (
            l2 == "HOLD"
            and not is_attack
            and pre_dist is not None
            and pre_dist <= 3
        ):
            reward -= 0.5

        if l2 == "HOLD" and damage == 0:
            reward -= 0.15

        # =================================================
        # ✅ INACTIVITY
        # =================================================
        if damage == 0 and not is_attack and l2 not in ["FLANK", "RETREAT"]:
            reward -= 0.05

        # =================================================
        # ✅ WAIT
        # =================================================
        if isinstance(action, WaitAction):
            reward -= 0.2

        # =================================================
        # ✅ L2 CONTROL
        # =================================================

        if l2 == "RETREAT":

            if pre_dist is not None and pre_dist <= 3:
                reward += 1.0

            if damage_taken == 0:
                reward += 0.6

            if damage_taken > damage:
                reward += 0.3

        elif l2 == "FLANK":

            if pre_dist is not None and pre_dist <= 3:

                reward += 1.0

                if damage_taken == 0:
                    reward += 0.2

                if post_dist is not None:
                    if abs(post_dist - pre_dist) <= 1:
                        reward += 0.3

                if damage == 0:
                    reward += 0.5

        # =================================================
        # ✅ ADVANCE
        # =================================================
        if l2 == "ADVANCE" and damage_taken > 0:
            reward -= 0.25

        # =================================================
        # ✅ COMBAT PRESSURE
        # =================================================
        if (
            pre_dist is not None
            and pre_dist <= 3
            and not is_attack
            and l2 not in ["FLANK", "RETREAT"]
        ):
            reward -= 0.2

        # =================================================
        # ✅ ANTI-SPAM
        # =================================================
        if self.last_action is not None and self.last_action == action_class:
            reward -= 0.1

        self.last_action = action_class

        # =================================================
        # ✅ VP
        # =================================================
        if hasattr(state, "vp_tracker") and state.vp_tracker:
            if hasattr(next_state, "vp_tracker") and next_state.vp_tracker:

                prev_vp = state.vp_tracker.score.get(self.rl_side, 0)
                new_vp = next_state.vp_tracker.score.get(self.rl_side, 0)

                reward += (new_vp - prev_vp) * 1.2

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
        # ✅ TIME
        # =================================================
        reward -= 0.02

        # =================================================
        # ✅ CLAMP FINAL
        # =================================================
        if l2 == "FLANK":
            reward = max(reward, 0.3)

        elif l2 == "RETREAT":
            reward = max(reward, 0.5)

        if l2 == "ATTACK":
            reward = min(reward, 1.2)

        # =================================================
        return max(min(reward, 10.0), -10.0)