class AdvancedMetrics:

    def __init__(self):
        self.total_attacks = 0
        self.good_trades = 0
        self.bad_trades = 0

        self.turns_in_range = 0
        self.attacks_in_range = 0

        self.zero_damage_attacks = 0

    # -------------------------------------------------
    # UPDATE (PER STEP)
    # -------------------------------------------------
    def update(self, info, pre_dist):

        damage = info.get("rl_damage", 0)
        damage_taken = info.get("enemy_damage", 0)

        action_class = info.get("action_class", "")
        is_attack = "ATTACK" in action_class.upper()

        trade = damage - damage_taken

        # =================================================
        # ✅ ATTACK METRICS (FIXED)
        # =================================================
        if is_attack:

            # 🔥 SOLO contar ataques "reales"
            # (evita inflar métricas con acciones basura)
            if damage > 0 or damage_taken > 0:

                self.total_attacks += 1

                if trade > 0:
                    self.good_trades += 1
                elif trade < 0:
                    self.bad_trades += 1

                # ✅ zero damage SOLO si hubo interacción
                if damage == 0:
                    self.zero_damage_attacks += 1

        # =================================================
        # ✅ RANGE / SELECTIVITY
        # =================================================
        if pre_dist is not None and pre_dist <= 3:
            self.turns_in_range += 1

            if is_attack:
                self.attacks_in_range += 1

    # -------------------------------------------------
    # EXPORT
    # -------------------------------------------------
    def to_dict(self):
        return {
            "total_attacks": self.total_attacks,
            "good_trades": self.good_trades,
            "bad_trades": self.bad_trades,
            "turns_in_range": self.turns_in_range,
            "attacks_in_range": self.attacks_in_range,
            "zero_damage_attacks": self.zero_damage_attacks,
        }