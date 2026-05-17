class SurvivalReward:

    def compute(self, *, active, info, action_name=None):

        reward = 0.0

        damage_taken = info.get("damage_taken", 0)
        damage_given = info.get("damage", 0)

        is_indirect = action_name and "Indirect" in action_name

        # ----------------------------------------
        # ✅ EVITAR DAÑO
        # ----------------------------------------
        if damage_taken > 0:
            reward -= 0.3 * damage_taken   # 🔧 antes 0.8 (demasiado fuerte)

        # ----------------------------------------
        # ✅ INTERCAMBIO (SUAVIZADO)
        # ----------------------------------------
        if damage_taken > damage_given:
            reward -= 0.1   # 🔧 antes -0.6

        # ----------------------------------------
        # ✅ INDIRECT FIRE DEFENSIVO
        # ----------------------------------------
        if is_indirect:

            # ✅ si no recibe daño → bueno
            if damage_taken == 0:
                reward += 0.2

        # ----------------------------------------
        # ✅ MUERTE
        # ----------------------------------------
        if active and not active.alive:
            reward -= 7.0

        return reward