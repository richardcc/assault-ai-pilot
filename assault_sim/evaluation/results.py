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
    # ACTION USAGE (L2)
    # -------------------------------------------------
    def aggregate_action_usage(self):

        total_counts = defaultdict(int)

        for r in self.results:
            option_counts = r.get("option_counts", {})

            for opt, count in option_counts.items():
                total_counts[opt] += count

        total = sum(total_counts.values())

        return {
            opt: (count, count / total if total > 0 else 0.0)
            for opt, count in total_counts.items()
        }

    # -------------------------------------------------
    # FORMATION USAGE (L3)
    # -------------------------------------------------
    def aggregate_formation_usage(self):

        formation_totals = defaultdict(int)

        for r in self.results:
            formation_counts = r.get("formation_counts", {})

            for k, v in formation_counts.items():
                formation_totals[k] += v

        total = sum(formation_totals.values())

        return {
            k: (v, v / total if total > 0 else 0.0)
            for k, v in formation_totals.items()
        }

    # -------------------------------------------------
    # STRATEGY → OPTION
    # -------------------------------------------------
    def aggregate_strategy_mapping(self):

        strategy_option_totals = defaultdict(lambda: defaultdict(int))

        for r in self.results:
            mapping = r.get("strategy_option_map", {})

            for strat, options in mapping.items():
                for opt, count in options.items():
                    strategy_option_totals[strat][opt] += count

        return strategy_option_totals

    # -------------------------------------------------
    # SIDE AGGREGATION (GLOBAL)
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
    # ✅ NEW: L1 AGGREGATION (acciones reales)
    # -------------------------------------------------
    def aggregate_l1_stats(self):

        agg = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        for r in self.results:
            l1 = r.get("l1", {})

            for side in ["RL", "ENEMY"]:
                for k, v in l1.get(side, {}).items():
                    agg[side][k] += v

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
    # ✅ NEW: L1 EFFICIENCY
    # -------------------------------------------------
    def l1_efficiency(self):

        agg = self.aggregate_l1_stats()

        def compute(side):
            attacks = agg[side].get("attacks", 0)
            damage = agg[side].get("damage", 0)
            kills = agg[side].get("kills", 0)

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
        })

        for r in self.results:
            unit_data = r.get("units", {})

            for side in ["RL", "ENEMY"]:
                for uid, stats in unit_data.get(side, {}).items():

                    # ✅ FIX AQUÍ (usar dict correctamente)
                    units[uid]["damage"] += stats.get("damage", 0)
                    units[uid]["attacks"] += stats.get("attacks", 0)
                    units[uid]["kills"] += stats.get("kills", 0)

        return units

    # -------------------------------------------------
    # TOP UNITS
    # -------------------------------------------------
    def top_units(self, key="damage", top_n=None):

        units = self.aggregate_units()

        sorted_units = sorted(
            units.items(),
            key=lambda x: x[1][key],
            reverse=True
        )

        if top_n is not None:
            return sorted_units[:top_n]

        return sorted_units

    # -------------------------------------------------
    # PRINT REPORT
    # -------------------------------------------------
    def print_report(self):

        summary = self.summary()
        efficiency = self.efficiency()
        sides = self.aggregate_side_stats()

        l1_stats = self.aggregate_l1_stats()
        l1_eff = self.l1_efficiency()

        action_usage = self.aggregate_action_usage()
        formation_usage = self.aggregate_formation_usage()
        strategy_mapping = self.aggregate_strategy_mapping()

        top_units = self.top_units()

        print("\n=== GLOBAL ===")
        print(summary)

        print("\n=== EFFICIENCY ===")
        print(efficiency)

        print("\n=== L1 EFFICIENCY (REAL COMBAT) ===")
        print(l1_eff)

        print("\n=== SIDE TOTALS ===")
        print(dict(sides["RL"]))
        print(dict(sides["ENEMY"]))

        print("\n=== L1 (REAL ACTIONS) ===")
        print(dict(l1_stats["RL"]))
        print(dict(l1_stats["ENEMY"]))

        # -------------------------------------------------
        # L2 ACTION USAGE
        # -------------------------------------------------
        print("\n=== ACTION USAGE (L2) ===")
        if action_usage:
            for opt, (count, ratio) in sorted(
                action_usage.items(),
                key=lambda x: x[1][0],
                reverse=True
            ):
                print(f"{opt}: {count} ({ratio:.2%})")
        else:
            print("No action data.")

        # -------------------------------------------------
        # L3 FORMATION USAGE
        # -------------------------------------------------
        print("\n=== FORMATION USAGE (L3) ===")
        if formation_usage:
            for strat, (count, ratio) in sorted(
                formation_usage.items(),
                key=lambda x: x[1][0],
                reverse=True
            ):
                print(f"{strat}: {count} ({ratio:.2%})")
        else:
            print("No formation data.")

        # -------------------------------------------------
        # L3 → L2 MAPPING
        # -------------------------------------------------
        print("\n=== STRATEGY → OPTION (L3 → L2) ===")

        for strat, options in strategy_mapping.items():
            total = sum(options.values())

            print(f"\n{strat}:")

            for opt, v in sorted(options.items(), key=lambda x: x[1], reverse=True):
                ratio = v / total if total > 0 else 0
                print(f"  {opt}: {v} ({ratio:.2%})")

        # -------------------------------------------------
        # TOP UNITS
        # -------------------------------------------------
        print("\n=== TOP UNITS (damage) ===")
        for uid, data in top_units:
            print(uid, data)
