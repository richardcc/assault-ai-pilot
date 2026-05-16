import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter


class EvalDashboard:

    def __init__(self):
        self.records = []

        # L3 (formation)
        self.formation_counter = Counter()

        # L2 (options)
        self.option_counter = Counter()

    # -------------------------------------------------
    # ADD EPISODE
    # -------------------------------------------------
    def add_episode(self, result):

        rl_damage = result["side"]["RL"].get("damage", 0)
        rl_attacks = result["side"]["RL"].get("attacks", 0)

        enemy_damage = result["side"]["ENEMY"].get("damage", 0)
        enemy_attacks = result["side"]["ENEMY"].get("attacks", 0)

        # -----------------------------
        # L2 tracking
        # -----------------------------
        option_counts = result.get("option_counts", {})
        self.option_counter.update(option_counts)

        # -----------------------------
        # L3 tracking
        # -----------------------------
        formation_counts = result.get("formation_counts", {})
        self.formation_counter.update(formation_counts)

        # -----------------------------
        # Episode row
        # -----------------------------
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

    # -------------------------------------------------
    # DATAFRAME
    # -------------------------------------------------
    def to_dataframe(self):
        return pd.DataFrame(self.records)

    # -------------------------------------------------
    # SAVE
    # -------------------------------------------------
    def save_csv(self, path="metrics.csv"):
        df = self.to_dataframe()
        df.to_csv(path, index=False)

    # -------------------------------------------------
    # PRINT STRATEGY STATS
    # -------------------------------------------------
    def print_strategy_stats(self):

        print("\n=== FORMATION DISTRIBUTION (L3) ===")

        total = sum(self.formation_counter.values())
        for k, v in self.formation_counter.most_common():
            ratio = v / total if total > 0 else 0
            print(f"{k}: {v} ({ratio:.2%})")

        print("\n=== OPTION DISTRIBUTION (L2) ===")

        total = sum(self.option_counter.values())
        for k, v in self.option_counter.most_common():
            ratio = v / total if total > 0 else 0
            print(f"{k}: {v} ({ratio:.2%})")

    # -------------------------------------------------
    # MAIN PLOT (UNCHANGED BASE)
    # -------------------------------------------------
    def plot(self):

        df = self.to_dataframe()

        if df.empty:
            print("No data to plot.")
            return

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
        # Damage
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

    # -------------------------------------------------
    # ✅ NEW: STRATEGY BAR PLOTS
    # -------------------------------------------------
    def plot_strategy_distribution(self):

        # ---------------------------
        # L3 Formation
        # ---------------------------
        if self.formation_counter:
            plt.figure(figsize=(10, 4))

            names = list(self.formation_counter.keys())
            values = list(self.formation_counter.values())

            plt.bar(names, values)
            plt.title("Formation Strategy Distribution (L3)")
            plt.xticks(rotation=45)

            plt.tight_layout()
            plt.show()

        else:
            print("No formation data available.")

        # ---------------------------
        # L2 Options
        # ---------------------------
        if self.option_counter:
            plt.figure(figsize=(10, 4))

            names = list(self.option_counter.keys())
            values = list(self.option_counter.values())

            plt.bar(names, values)
            plt.title("Tactical Option Distribution (L2)")
            plt.xticks(rotation=45)

            plt.tight_layout()
            plt.show()

        else:
            print("No option data available.")

# -------------------------------------------------
    # ✅ FULL DASHBOARD (ALL IN ONE FIGURE)
    # -------------------------------------------------
    def plot_all(self):

        df = self.to_dataframe()

        if df.empty:
            print("No data to plot.")
            return

        # 2 filas × 3 columnas
        fig, axs = plt.subplots(2, 3, figsize=(16, 8))

        # ---------------------------
        # VP
        # ---------------------------
        axs[0, 0].plot(df["vp"])
        axs[0, 0].set_title("VP over episodes")

        # ---------------------------
        # Steps
        # ---------------------------
        axs[0, 1].plot(df["steps"])
        axs[0, 1].set_title("Steps")

        # ---------------------------
        # Damage
        # ---------------------------
        axs[0, 2].plot(df["rl_damage"], label="RL")
        axs[0, 2].plot(df["enemy_damage"], label="ENEMY")
        axs[0, 2].set_title("Damage")
        axs[0, 2].legend()

        # ---------------------------
        # Efficiency
        # ---------------------------
        axs[1, 0].plot(df["rl_efficiency"], label="RL")
        axs[1, 0].plot(df["enemy_efficiency"], label="ENEMY")
        axs[1, 0].set_title("Efficiency")
        axs[1, 0].legend()

        # ---------------------------
        # L3 (formation)
        # ---------------------------
        if self.formation_counter:
            names = list(self.formation_counter.keys())
            values = list(self.formation_counter.values())

            axs[1, 1].bar(names, values)
            axs[1, 1].set_title("L3 Formation")
            axs[1, 1].tick_params(axis='x', rotation=45)
        else:
            axs[1, 1].set_title("L3 Formation (empty)")

        # ---------------------------
        # L2 (options)
        # ---------------------------
        if self.option_counter:
            names = list(self.option_counter.keys())
            values = list(self.option_counter.values())

            axs[1, 2].bar(names, values)
            axs[1, 2].set_title("L2 Options")
            axs[1, 2].tick_params(axis='x', rotation=45)
        else:
            axs[1, 2].set_title("L2 Options (empty)")

        plt.tight_layout()
        plt.show()
        
if __name__ == "__main__":
    print("✅ Dashboard module ready")