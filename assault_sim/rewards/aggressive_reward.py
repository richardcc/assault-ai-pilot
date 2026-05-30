from .base_reward import BaseReward
from assault_model.actions.status import WaitAction


class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None):
        super().__init__(rl_side)
        self.rl_side = rl_side
        self.last_action = None

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
        # ✅ DAMAGE (CORE)
        # =================================================
        reward += damage * 0.8
        reward -= damage_taken * 0.8

        # ✅ trade positivo
        if damage > damage_taken:
            reward += 0.2

        # ✅ trade perfecto
        if damage >= 2 and damage_taken == 0:
            reward += 0.4

        # ✅ supervivencia SOLO si haces algo útil
        if damage_taken == 0 and damage > 0:
            reward += 0.1

        # =================================================
        # ✅ ATTACK QUALITY (REBALANCEADO)
        # =================================================
        if is_attack:

            reward += 0.3  # antes 0.5 → bajamos dominancia

            if damage > 0:
                reward += 1.0
            else:
                reward -= 0.4   # castigo fuerte

            # 🔥 MAL trade = muy castigado
            if damage_taken > damage:
                reward -= 0.6

        # =================================================
        # ✅ KILL
        # =================================================
        if killed:
            reward += 4.0

        # =================================================
        # ✅ POSITIONING
        # =================================================
        if pre_dist is not None and post_dist is not None:

            if post_dist < pre_dist:
                reward += 0.05

            if post_dist <= 2:
                reward += 0.1

        # =================================================
        # ✅ HOLD PASIVO
        # =================================================
        if (
            l2 == "HOLD"
            and not is_attack
            and pre_dist is not None
            and pre_dist <= 3
        ):
            reward -= 0.5

        # HOLD sin impacto
        if l2 == "HOLD" and damage == 0:
            reward -= 0.15

        # =================================================
        # ✅ INACTIVITY
        # =================================================
        if damage == 0 and not is_attack:
            reward -= 0.05

        # =================================================
        # ✅ WAIT
        # =================================================
        if isinstance(action, WaitAction):
            reward -= 0.2

        # =================================================
        # ✅ L2 CONTROL
        # =================================================

        # -------------------------
        # ATTACK
        # -------------------------
        if l2 == "ATTACK":
            reward += 0.2

        # -------------------------
        # RETREAT (IMPORTANTE)
        # -------------------------
        elif l2 == "RETREAT":

            if pre_dist is not None and pre_dist <= 3:
                reward += 0.6

            if damage_taken == 0:
                reward += 0.2

            if damage_taken > damage:
                reward += 0.3  # escapar buen trade

        # -------------------------
        # FLANK (CLAVE)
        # -------------------------
        elif l2 == "FLANK":

            reward += 0.4

            if damage_taken == 0:
                reward += 0.2

            if pre_dist is not None and post_dist is not None:
                if abs(post_dist - pre_dist) <= 1:
                    reward += 0.3

        # -------------------------
        # ADVANCE control
        # -------------------------
        if l2 == "ADVANCE" and damage_taken > 0:
            reward -= 0.25

        # =================================================
        # 🔥 FORZAR DECISIÓN EN COMBATE
        # =================================================
        if pre_dist is not None and pre_dist <= 3 and not is_attack:
            reward -= 0.2

        # =================================================
        # ✅ ANTI-SPAM
        # =================================================
        if self.last_action is not None and self.last_action == action_class:
            reward -= 0.1

        self.last_action = action_class

        # =================================================
        # ✅ VICTORY POINTS
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
        # ✅ TIME COST
        # =================================================
        reward -= 0.02

        # =================================================
        # ✅ CLIP
        # =================================================
        return max(min(reward, 10.0), -10.0)