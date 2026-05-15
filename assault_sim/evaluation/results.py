# assault_sim/evaluation/results.py

import statistics
from collections import defaultdict


class ResultsAnalyzer:

    def __init__(self, results, rl_side):
        self.results = results
        self.rl_side = rl_side

    # -------------------------------------------------
    # GLOBAL SUMMARY
    # -------------------------------------------------
    def summary(self):

        wins = 0.0
        draws = 0

        vp_list = []
        steps_list = []

        for r in self.results:
            winner = r["winner"]

            if winner == self.rl_side:
                wins += 1
            elif winner is None:
                wins += 0.5
                draws += 1

            vp_list.append(r["vp"])
            steps_list.append(r["steps"])

        return {
            "episodes": len(self.results),
            "win_rate": wins / len(self.results),
            "draws": draws,
            "avg_vp": statistics.mean(vp_list) if vp_list else 0,
            "avg_steps": statistics.mean(steps_list) if steps_list else 0,
        }

    # -------------------------------------------------
    # SIDE AGGREGATION
    # -------------------------------------------------
    def aggregate_side_stats(self):

        agg = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        for r in self.results:
            side = r["side"]

            for s in ["RL", "ENEMY"]:
                for k, v in side[s].items():
                    agg[s][k] += v

        return agg

    # -------------------------------------------------
    # EFFICIENCY (GLOBAL)
    # -------------------------------------------------
    def efficiency(self):

        agg = self.aggregate_side_stats()

        def compute(side):
            attacks = agg[side]["attacks"]
            damage = agg[side]["damage"]
            kills = agg[side]["kills"]

            return {
                "damage_per_attack": damage / attacks if attacks else 0,
                "kills_per_attack": kills / attacks if attacks else 0,
            }

        return {
            "RL": compute("RL"),
            "ENEMY": compute("ENEMY"),
        }

    # -------------------------------------------------
    # UNIT AGGREGATION
    # -------------------------------------------------
    def aggregate_units(self):

        units = defaultdict(lambda: {
            "attacks": 0,
            "damage": 0,
            "kills": 0,
            "alive_count": 0,
        })

        for r in self.results:
            for uid, stats in r["units"].items():

                units[uid]["attacks"] += stats.attacks
                units[uid]["damage"] += stats.damage_done
                units[uid]["kills"] += stats.kills

                if stats.alive:
                    units[uid]["alive_count"] += 1

        return units

    # -------------------------------------------------
    # TOP UNITS
    # -------------------------------------------------
    def top_units(self, key="damage", top_n=10):

        units = self.aggregate_units()

        return sorted(
            units.items(),
            key=lambda x: x[1][key],
            reverse=True
        )[:top_n]

    # -------------------------------------------------
    # PRINT REPORT
    # -------------------------------------------------
    def print_report(self):

        summary = self.summary()
        efficiency = self.efficiency()
        sides = self.aggregate_side_stats()
        top_units = self.top_units()

        print("\n=== GLOBAL ===")
        print(summary)

        print("\n=== EFFICIENCY ===")
        print(efficiency)

        print("\n=== SIDE TOTALS ===")
        print(dict(sides["RL"]))
        print(dict(sides["ENEMY"]))

        print("\n=== TOP UNITS (damage) ===")
        for uid, data in top_units:
            print(uid, data)
