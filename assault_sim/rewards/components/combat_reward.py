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

        # ----------------------------------------
        # ✅ BASE DAMAGE
        # ----------------------------------------
        reward += 0.5 * dmg

        # ----------------------------------------
        # ✅ KILL
        # ----------------------------------------
        if killed:
            reward += 4.5

        # ----------------------------------------
        # ✅ ATTACK BONUS
        # ----------------------------------------
        if is_attack:
            reward += 0.4

        # ========================================
        # 🔥 ✅ INDIRECT FIRE BONUS (CLAVE)
        # ========================================
        if "Indirect" in action_name:

            # ✅ base: que no desaparezca
            reward += 1.5

            # ✅ SI acierta → muy valioso
            if dmg > 0:
                reward += 2.0

            # ✅ SI mata → aún mejor que direct
            if killed:
                reward += 3.0

        return reward