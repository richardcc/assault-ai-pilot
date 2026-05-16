class MetricsTracker:

    def __init__(self):
        self.reset()

    def reset(self):
        self.kills = 0
        self.damage = 0
        self.attacks = 0
        self.wins = 0

    def update(self, info):
        self.kills += info.get("rl_kills", 0)
        self.damage += info.get("rl_damage", 0)
        self.attacks += info.get("rl_attacks", 0)

    def summary(self):
        return {
            "kills": self.kills,
            "damage": self.damage,
            "attacks": self.attacks,
        }