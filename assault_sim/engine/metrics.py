class MetricsTracker:

    def __init__(self):
        self.reset()

    def reset(self):
        self.kills = 0
        self.damage = 0
        self.attacks = 0
        self.wins = 0

    def update(self, info):
        self.kills = info.get("rl_kills", self.kills)
        self.damage = info.get("rl_damage", self.damage)
        self.attacks = info.get("rl_attacks", self.attacks)

    def summary(self):
        return {
            "kills": self.kills,
            "damage": self.damage,
            "attacks": self.attacks,
        }