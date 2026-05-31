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
        # ✅ NEW: ADVANCED METRICS
        # -----------------------------
        adv = result.get("advanced", {})

        total_attacks = max(1, adv.get("total_attacks", 0))
        range_total = max(1, adv.get("turns_in_range", 0))

        good_trade = adv.get("good_trades", 0) / total_attacks
        bad_trade = adv.get("bad_trades", 0) / total_attacks
        selectivity = adv.get("attacks_in_range", 0) / range_total
        zero_dmg = adv.get("zero_damage_attacks", 0) / total_attacks

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

            # ✅ NEW (advanced)
            "good_trade": good_trade,
            "bad_trade": bad_trade,
            "selectivity": selectivity,
            "zero_dmg": zero_dmg,
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

        axs[0, 0].plot(df["vp"])
        axs[0, 0].set_title("VP over episodes")

        axs[0, 1].plot(df["steps"])
        axs[0, 1].set_title("Steps")

        axs[1, 0].plot(df["rl_damage"], label="RL")
        axs[1, 0].plot(df["enemy_damage"], label="ENEMY")
        axs[1, 0].set_title("Damage")
        axs[1, 0].legend()

        axs[1, 1].plot(df["rl_efficiency"], label="RL")
        axs[1, 1].plot(df["enemy_efficiency"], label="ENEMY")
        axs[1, 1].set_title("Efficiency")
        axs[1, 1].legend()

        plt.tight_layout()
        plt.show()

    # -------------------------------------------------
    # ✅ FULL DASHBOARD (EXTENDED, SAME WINDOW)
    # -------------------------------------------------
    def plot_all(self):

        df = self.to_dataframe()

        if df.empty:
            print("No data to plot.")
            return

        # 🔥 Expandimos a 3x3 (pero manteniendo todo lo anterior)
        fig, axs = plt.subplots(3, 3, figsize=(16, 12))

        # =============================
        # ROW 1 (original)
        # =============================
        axs[0, 0].plot(df["vp"])
        axs[0, 0].set_title("VP")

        axs[0, 1].plot(df["steps"])
        axs[0, 1].set_title("Steps")

        axs[0, 2].plot(df["rl_damage"], label="RL")
        axs[0, 2].plot(df["enemy_damage"], label="ENEMY")
        axs[0, 2].set_title("Damage")
        axs[0, 2].legend()

        # =============================
        # ROW 2 (original + improved)
        # =============================
        axs[1, 0].plot(df["rl_efficiency"], label="RL")
        axs[1, 0].plot(df["enemy_efficiency"], label="ENEMY")
        axs[1, 0].set_title("Efficiency")
        axs[1, 0].legend()

        # ✅ NEW
        axs[1, 1].plot(df["selectivity"])
        axs[1, 1].set_title("Selectivity")

        axs[1, 2].plot(df["good_trade"])
        axs[1, 2].set_title("Good Trade Rate")

        # =============================
        # ROW 3 (advanced)
        # =============================
        axs[2, 0].plot(df["zero_dmg"])
        axs[2, 0].set_title("Zero Damage Rate")

        axs[2, 1].plot(df["bad_trade"])
        axs[2, 1].set_title("Bad Trade Rate")

        # L3 formation (existing)
        if self.formation_counter:
            axs[2, 2].bar(
                list(self.formation_counter.keys()),
                list(self.formation_counter.values())
            )
            axs[2, 2].set_title("L3 Formation")
            axs[2, 2].tick_params(axis='x', rotation=45)
        else:
            axs[2, 2].set_title("L3 Formation (empty)")

        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    print("✅ Dashboard module ready")