class CombatReward:

    def compute(self, *, action_name, info):

        reward = 0.0

        is_attack = (
            "Ranged" in action_name or
            "Assault" in action_name or
            "Close" in action_name
        )

        dmg = info.get("damage", 0)
        killed = info.get("defender_killed", False)

        # daño
        reward += 0.5 * dmg

        # kill
        if killed:
            reward += 4.5

        # bonus por atacar
        if is_attack:
            reward += 0.4

        return reward