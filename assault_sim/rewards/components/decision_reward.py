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

        # mover sin valor
        if is_move:
            reward -= 0.15

            if pre_dist is not None and post_dist is not None:
                if post_dist >= pre_dist:
                    reward -= 0.4

        # no atacar en rango
        if not is_attack and pre_dist is not None:
            if pre_dist <= 3:
                reward -= 1.5
            if pre_dist <= 1:
                reward -= 2.5

        # esperar puede ser correcto
        if is_wait:
            reward += 0.1

        # streak
        if wait_streak >= 3:
            reward -= 0.3 * wait_streak

        return reward