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
            "win_rate": wins / len(self.results) if self.results else 0,
            "draws": draws,
            "avg_vp": statistics.mean(vp_list) if vp_list else 0,
            "avg_steps": statistics.mean(steps_list) if steps_list else 0,
        }

    # -------------------------------------------------
    # COMBAT
    # -------------------------------------------------
    def combat_metrics(self):

        trade_sum = 0
        trade_count = 0

        total_damage = 0
        total_taken = 0

        for r in self.results:
            combat = r.get("combat", {})
            side = r.get("side", {})

            atk = combat.get("total_attacks", 0)
            trade = combat.get("trade_mean", 0.0)

            trade_sum += trade * atk
            trade_count += atk

            total_damage += side.get("RL", {}).get("damage", 0)
            total_taken += side.get("ENEMY", {}).get("damage", 0)

        return {
            "trade_mean": trade_sum / max(1, trade_count),
            "damage_ratio": total_damage / max(1, total_taken),
        }

    # -------------------------------------------------
    # ADVANCED
    # -------------------------------------------------
    def advanced_metrics(self):

        agg = {
            "good": 0,
            "bad": 0,
            "zero": 0,
            "in_range": 0,
            "attack_in_range": 0,
        }

        for r in self.results:
            adv = r.get("advanced", {})

            agg["good"] += adv.get("good_trades", 0)
            agg["bad"] += adv.get("bad_trades", 0)
            agg["zero"] += adv.get("zero_damage_attacks", 0)
            agg["in_range"] += adv.get("turns_in_range", 0)
            agg["attack_in_range"] += adv.get("attacks_in_range", 0)

        total = max(1, agg["good"] + agg["bad"])
        range_total = max(1, agg["in_range"])

        return {
            "good_trade_rate": agg["good"] / total,
            "bad_trade_rate": agg["bad"] / total,
            "selectivity": agg["attack_in_range"] / range_total,
            "zero_dmg_rate": agg["zero"] / total,
        }

    # -------------------------------------------------
    # ACTION / FORMATION
    # -------------------------------------------------
    def action_usage(self):

        total_counts = defaultdict(int)

        for r in self.results:
            for k, v in r.get("option_counts", {}).items():
                total_counts[k] += v

        total = sum(total_counts.values())

        return {
            k: (v, v / total if total else 0)
            for k, v in total_counts.items()
        }

    def formation_usage(self):

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
    # EFFICIENCY
    # -------------------------------------------------
    def efficiency(self):

        agg = {
            "RL": defaultdict(int),
            "ENEMY": defaultdict(int),
        }

        for r in self.results:
            for side in ["RL", "ENEMY"]:
                for k, v in r["side"][side].items():
                    agg[side][k] += v

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
    # UNITS
    # -------------------------------------------------
    def aggregate_units(self):

        units = defaultdict(lambda: {
            "attacks": 0,
            "damage": 0,
            "kills": 0,
            "side": None,
            "category": None,
            "classification": None,
        })

        for r in self.results:
            for side in ["RL", "ENEMY"]:
                for uid, stats in r.get("units", {}).get(side, {}).items():

                    units[uid]["attacks"] += stats.get("attacks", 0)
                    units[uid]["damage"] += stats.get("damage", 0)
                    units[uid]["kills"] += stats.get("kills", 0)

                    if units[uid]["side"] is None:
                        units[uid]["side"] = side
                        units[uid]["category"] = stats.get("category")
                        units[uid]["classification"] = stats.get("classification")

        return units

    # -------------------------------------------------
    # ALL UNITS (SIN HARDCODE)
    # -------------------------------------------------
    def print_all_units(self):

        units = self.aggregate_units()

        print(f"\n=== ALL UNITS ({self.rl_side}) ===")
        for uid, u in units.items():
            if u["side"] == "RL":
                print(
                    f"{uid} | type={u['category']} | class={u['classification']} | "
                    f"dmg={u['damage']} atk={u['attacks']} kills={u['kills']}"
                )

        print("\n=== ALL UNITS (OTHER SIDE) ===")
        for uid, u in units.items():
            if u["side"] != "RL":
                print(
                    f"{uid} | type={u['category']} | class={u['classification']} | "
                    f"dmg={u['damage']} atk={u['attacks']} kills={u['kills']}"
                )

    # -------------------------------------------------
    # TOP UNITS
    # -------------------------------------------------
    def top_units(self, n=5):

        units = self.aggregate_units()
        items = list(units.items())

        items.sort(key=lambda x: x[1]["damage"], reverse=True)
        return items[:n]

    # -------------------------------------------------
    # PRINT REPORT
    # -------------------------------------------------
    def print_report(self):

        print("\n=== GLOBAL ===")
        print(self.summary())

        print("\n=== COMBAT ===")
        print(self.combat_metrics())

        print("\n=== ADVANCED ===")
        for k, v in self.advanced_metrics().items():
            print(f"{k}: {v:.3f}")

        print("\n=== EFFICIENCY ===")
        print(self.efficiency())

        print("\n=== ACTION USAGE ===")
        for k, (c, r) in sorted(self.action_usage().items(), key=lambda x: x[1][0], reverse=True):
            print(f"{k}: {c} ({r:.2%})")

        print("\n=== FORMATION ===")
        for k, (c, r) in sorted(self.formation_usage().items(), key=lambda x: x[1][0], reverse=True):
            print(f"{k}: {c} ({r:.2%})")

        print("\n=== TOP UNITS ===")
        for uid, u in self.top_units():
            print(f"{uid}: dmg={u['damage']} atk={u['attacks']} kills={u['kills']}")

        # ✅ dinámico
        self.print_all_units()