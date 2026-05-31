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
    # ✅ ADVANCED METRICS
    # -------------------------------------------------
    def aggregate_advanced_metrics(self):

        agg = {
            "good_trades": 0,
            "bad_trades": 0,
            "zero_damage_attacks": 0,
            "turns_in_range": 0,
            "attacks_in_range": 0,
            "total_attacks": 0,
        }

        for r in self.results:
            adv = r.get("advanced", {})

            agg["good_trades"] += adv.get("good_trades", 0)
            agg["bad_trades"] += adv.get("bad_trades", 0)
            agg["zero_damage_attacks"] += adv.get("zero_damage_attacks", 0)
            agg["turns_in_range"] += adv.get("turns_in_range", 0)
            agg["attacks_in_range"] += adv.get("attacks_in_range", 0)
            agg["total_attacks"] += adv.get("total_attacks", 0)

        return agg

    # -------------------------------------------------
    # ACTION USAGE
    # -------------------------------------------------
    def aggregate_action_usage(self):

        total_counts = defaultdict(int)

        for r in self.results:
            for opt, count in r.get("option_counts", {}).items():
                total_counts[opt] += count

        total = sum(total_counts.values())

        return {
            opt: (count, count / total if total else 0)
            for opt, count in total_counts.items()
        }

    # -------------------------------------------------
    # FORMATION USAGE
    # -------------------------------------------------
    def aggregate_formation_usage(self):

        totals = defaultdict(int)

        for r in self.results:
            for k, v in r.get("formation_counts", {}).items():
                totals[k] += v

        total = sum(totals.values())

        return {
            k: (v, v / total if total else 0)
            for k, v in totals.items()
        }

    # -------------------------------------------------
    # STRATEGY MAPPING
    # -------------------------------------------------
    def aggregate_strategy_mapping(self):

        mapping = defaultdict(lambda: defaultdict(int))

        for r in self.results:
            m = r.get("strategy_option_map", {})

            for strat, opts in m.items():
                for o, c in opts.items():
                    mapping[strat][o] += c

        return mapping

    # -------------------------------------------------
    # SIDE TOTALS
    # -------------------------------------------------
    def aggregate_side_stats(self):

        agg = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        for r in self.results:
            for side in ["RL", "ENEMY"]:
                for k, v in r["side"][side].items():
                    agg[side][k] += v

        return agg

    # -------------------------------------------------
    # L1 STATS
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
    # EFFICIENCY
    # -------------------------------------------------
    def efficiency(self):

        agg = self.aggregate_side_stats()

        def compute(side):
            a = agg[side]["attacks"]
            d = agg[side]["damage"]
            k = agg[side]["kills"]

            return {
                "damage_per_attack": d / a if a else 0,
                "kills_per_attack": k / a if a else 0,
            }

        return {"RL": compute("RL"), "ENEMY": compute("ENEMY")}

    # -------------------------------------------------
    # L1 EFFICIENCY
    # -------------------------------------------------
    def l1_efficiency(self):

        agg = self.aggregate_l1_stats()

        def compute(side):
            a = agg[side].get("attacks", 0)
            d = agg[side].get("damage", 0)
            k = agg[side].get("kills", 0)

            return {
                "damage_per_attack": d / a if a else 0,
                "kills_per_attack": k / a if a else 0,
            }

        return {"RL": compute("RL"), "ENEMY": compute("ENEMY")}

    # -------------------------------------------------
    # UNIT AGGREGATION
    # -------------------------------------------------
    def aggregate_units(self):

        units = defaultdict(lambda: {
            "attacks": 0,
            "damage": 0,
            "kills": 0,
            "unit_key": None,
            "category": None,
            "classification": None,
        })

        for r in self.results:
            for side in ["RL", "ENEMY"]:
                for uid, stats in r.get("units", {}).get(side, {}).items():

                    units[uid]["damage"] += stats.get("damage", 0)
                    units[uid]["attacks"] += stats.get("attacks", 0)
                    units[uid]["kills"] += stats.get("kills", 0)

                    if units[uid]["unit_key"] is None:
                        units[uid]["unit_key"] = stats.get("unit_key")
                        units[uid]["category"] = stats.get("category")
                        units[uid]["classification"] = stats.get("classification")

        return units

    # -------------------------------------------------
    # PRINT REPORT
    # -------------------------------------------------
    def print_report(self):

        summary = self.summary()
        sides = self.aggregate_side_stats()
        l1_stats = self.aggregate_l1_stats()
        eff = self.efficiency()
        l1_eff = self.l1_efficiency()

        action = self.aggregate_action_usage()
        formation = self.aggregate_formation_usage()
        mapping = self.aggregate_strategy_mapping()

        adv = self.aggregate_advanced_metrics()

        print("\n=== GLOBAL ===")
        print(summary)

        print("\n=== EFFICIENCY ===")
        print(eff)

        print("\n=== L1 EFFICIENCY (REAL COMBAT) ===")
        print(l1_eff)

        print("\n=== SIDE TOTALS ===")
        print(dict(sides["RL"]))
        print(dict(sides["ENEMY"]))

        print("\n=== L1 (REAL ACTIONS) ===")
        print(dict(l1_stats["RL"]))
        print(dict(l1_stats["ENEMY"]))

        print("\n=== ACTION USAGE ===")
        for k, (c, r) in sorted(action.items(), key=lambda x: x[1][0], reverse=True):
            print(f"{k}: {c} ({r:.2%})")

        print("\n=== FORMATION USAGE ===")
        for k, (c, r) in sorted(formation.items(), key=lambda x: x[1][0], reverse=True):
            print(f"{k}: {c} ({r:.2%})")

        print("\n=== STRATEGY → OPTION ===")
        for strat, opts in mapping.items():
            total = sum(opts.values())
            print(f"\n{strat}:")
            for o, v in sorted(opts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {o}: {v} ({v/total:.2%})")

        # ✅ ADVANCED
        print("\n=== ADVANCED METRICS ===")

        total_attacks = max(1, adv["total_attacks"])
        range_total = max(1, adv["turns_in_range"])

        print(f"good_trade_rate:  {adv['good_trades'] / total_attacks:.3f}")
        print(f"bad_trade_rate:   {adv['bad_trades'] / total_attacks:.3f}")
        print(f"selectivity:      {adv['attacks_in_range'] / range_total:.3f}")
        print(f"zero_dmg_rate:    {adv['zero_damage_attacks'] / total_attacks:.3f}")