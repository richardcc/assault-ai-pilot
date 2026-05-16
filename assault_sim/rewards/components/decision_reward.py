from assault_model.actions.status import WaitAction


class DecisionReward:

    def compute(self, *, action, action_name, pre_dist, post_dist, wait_streak):

        reward = 0.0

        is_attack = (
            "Ranged" in action_name or
            "Assault" in action_name or
            "Close" in action_name
        )

        is_move = "Move" in action_name
        is_wait = isinstance(action, WaitAction)

        is_indirect = "Indirect" in action_name

        # ----------------------------------------
        # ✅ MOVEMENT
        # ----------------------------------------
        if is_move:
            reward -= 0.10   # 🔧 menos castigo

            if pre_dist is not None and post_dist is not None:
                if post_dist >= pre_dist:
                    reward -= 0.25  # 🔧 menos severo

        # ----------------------------------------
        # ✅ NO ATTACK PENALTY (SUAVIZADO)
        # ----------------------------------------
        if not is_attack and pre_dist is not None:

            if pre_dist <= 3:
                reward -= 0.6   # 🔧 antes 1.5 (demasiado fuerte)

            if pre_dist <= 1:
                reward -= 1.0   # 🔧 antes 2.5

        # ----------------------------------------
        # ✅ INDIRECT AWARENESS (CLAVE)
        # ----------------------------------------
        if is_indirect:

            # ✅ NO castigar indirect por no ser inmediato
            reward += 0.10

        # ----------------------------------------
        # ✅ WAIT (ajustado)
        # ----------------------------------------
        if is_wait:
            reward += 0.05   # 🔧 antes 0.1

        # ----------------------------------------
        # ✅ WAIT STREAK
        # ----------------------------------------
        if wait_streak >= 3:
            reward -= 0.15 * wait_streak   # 🔧 menos castigo

        return reward