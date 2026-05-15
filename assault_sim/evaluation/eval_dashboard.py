import pandas as pd
import matplotlib.pyplot as plt


class EvalDashboard:
    def __init__(self):
        self.records = []

    def add_episode(self, result):

        rl_damage = result["side"]["RL"].get("damage", 0)
        rl_attacks = result["side"]["RL"].get("attacks", 0)

        enemy_damage = result["side"]["ENEMY"].get("damage", 0)
        enemy_attacks = result["side"]["ENEMY"].get("attacks", 0)

        row = {
            "winner": str(result.get("winner")),
            "vp": float(result.get("vp") or 0),
            "steps": float(result.get("steps") or 0),

            "rl_damage": float(rl_damage),
            "enemy_damage": float(enemy_damage),

            "rl_attacks": float(rl_attacks),
            "enemy_attacks": float(enemy_attacks),

            "rl_kills": float(result["side"]["RL"].get("kills", 0)),
            "enemy_kills": float(result["side"]["ENEMY"].get("kills", 0)),

            "rl_efficiency": rl_damage / max(1, rl_attacks),
            "enemy_efficiency": enemy_damage / max(1, enemy_attacks),
        }

        self.records.append(row)

    def to_dataframe(self):
        return pd.DataFrame(self.records)

    def save_csv(self, path="metrics.csv"):
        df = self.to_dataframe()
        df.to_csv(path, index=False)

    def plot(self):

        df = self.to_dataframe()

        # ✅ UNA SOLA FIGURA con subplots
        fig, axs = plt.subplots(2, 2, figsize=(12, 8))

        # ---------------------------
        # VP
        # ---------------------------
        axs[0, 0].plot(df["vp"])
        axs[0, 0].set_title("VP over episodes")
        axs[0, 0].set_xlabel("Episode")
        axs[0, 0].set_ylabel("VP")

        # ---------------------------
        # Steps
        # ---------------------------
        axs[0, 1].plot(df["steps"])
        axs[0, 1].set_title("Steps per episode")
        axs[0, 1].set_xlabel("Episode")
        axs[0, 1].set_ylabel("Steps")

        # ---------------------------
        # Damage comparison
        # ---------------------------
        axs[1, 0].plot(df["rl_damage"], label="RL")
        axs[1, 0].plot(df["enemy_damage"], label="ENEMY")
        axs[1, 0].set_title("Damage")
        axs[1, 0].legend()

        # ---------------------------
        # Efficiency
        # ---------------------------
        axs[1, 1].plot(df["rl_efficiency"], label="RL")
        axs[1, 1].plot(df["enemy_efficiency"], label="ENEMY")
        axs[1, 1].set_title("Efficiency (damage per attack)")
        axs[1, 1].legend()

        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    print("Dashboard module ready")
