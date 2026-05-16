class SurvivalReward:

    def compute(self, *, active, info):

        reward = 0.0

        damage_taken = info.get("damage_taken", 0)
        damage_given = info.get("damage", 0)

        # penalizar recibir daño
        if damage_taken > 0:
            reward -= 0.8 * damage_taken

        # 🔥 evitar malos intercambios
        if damage_taken > damage_given:
            reward -= 0.6

        # muerte
        if active and not active.alive:
            reward -= 7.0

        return reward