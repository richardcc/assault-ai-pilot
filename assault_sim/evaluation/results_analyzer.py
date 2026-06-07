import statistics

from assault_sim.evaluation.policy.l2_options import compute_option_performance
from assault_sim.evaluation.policy.l3_formations import compute_formation_performance
from assault_sim.evaluation.policy.mapping import (
    build_strategy_option_map,
    normalize_strategy_option_map,
)

from assault_sim.evaluation.units.unit_aggregation import aggregate_units
from assault_sim.evaluation.units.unit_reporting import print_all_units

# ✅ NUEVO (CORRECTO)
from collections import defaultdict


class ResultsAnalyzer:

    def __init__(self, results, rl_side):
        self.results = results
        self.rl_side = rl_side

    # -------------------------------------------------
    # GLOBAL
    # -------------------------------------------------
    def summary(self):

        wins = 0.0
        draws = 0

        vp_list = []
        steps_list = []
        reason_counts = defaultdict(int)
        win_by_reason = defaultdict(float)

        for r in self.results:

            winner = r.get("winner")
            reason = str(r.get("end_reason") or "unknown")
            reason_counts[reason] += 1

            if winner == self.rl_side:
                wins += 1
                win_by_reason[reason] += 1
            elif winner is None:
                wins += 0.5
                draws += 1
                win_by_reason[reason] += 0.5

            vp_list.append(r.get("vp", 0))
            steps_list.append(r.get("steps", 0))

        reason_win_rate = {}
        for reason, count in reason_counts.items():
            reason_win_rate[reason] = win_by_reason[reason] / max(1, count)

        return {
            "episodes": len(self.results),
            "win_rate": wins / len(self.results) if self.results else 0,
            "draws": draws,
            "avg_vp": statistics.mean(vp_list) if vp_list else 0,
            "avg_steps": statistics.mean(steps_list) if steps_list else 0,
            "end_reason_counts": dict(reason_counts),
            "win_rate_by_end_reason": reason_win_rate,
            "victory_level_counts": self.victory_level_counts(),
        }

    def victory_level_counts(self):
        counts = defaultdict(int)
        for r in self.results:
            lvl = r.get("victory_level") or {}
            label = str(lvl.get("result") or "UNKNOWN")
            counts[label] += 1
        return dict(counts)

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

        agg = defaultdict(int)

        for r in self.results:

            adv = r.get("advanced", {})

            agg["good"] += adv.get("good_trades", 0)
            agg["bad"] += adv.get("bad_trades", 0)
            agg["zero"] += adv.get("zero_damage_attacks", 0)
            agg["in_range"] += adv.get("turns_in_range", 0)
            agg["atk_range"] += adv.get("attacks_in_range", 0)

        total = max(1, agg["good"] + agg["bad"])
        range_total = max(1, agg["in_range"])

        return {
            "good_trade_rate": agg["good"] / total,
            "bad_trade_rate": agg["bad"] / total,
            "selectivity": agg["atk_range"] / range_total,
            "zero_dmg_rate": agg["zero"] / total,
        }

    # -------------------------------------------------
    # POLICY ALIGNMENT
    # -------------------------------------------------
    def policy_alignment(self):
        forced_steps = 0
        decisions = 0
        sampled_to_executed = defaultdict(int)
        for r in self.results:
            align = r.get("decision_alignment", {})
            forced_steps += int(align.get("forced_steps", 0))
            decisions += int(align.get("rl_decisions", 0))
            for k, v in align.get("sampled_to_executed_counts", {}).items():
                sampled_to_executed[k] += int(v)
        top_paths = dict(sorted(sampled_to_executed.items(), key=lambda kv: kv[1], reverse=True)[:10])
        return {
            "forced_steps": forced_steps,
            "decisions": decisions,
            "forced_ratio": forced_steps / max(1, decisions),
            "top_sampled_to_executed": top_paths,
        }

    # -------------------------------------------------
    # ✅ ACCIONES REALES (EVENT-BASED)
    # -------------------------------------------------
    def action_execution(self):

        # Aggregate by side using per-episode L1 counters and L1 efficiency
        by_side = {
            "RL": defaultdict(lambda: {"count": 0, "damage": 0.0}),
            "ENEMY": defaultdict(lambda: {"count": 0, "damage": 0.0}),
        }

        action_name_counts = defaultdict(int)

        def map_action_type(action_class_name: str):
            n = (action_class_name or "").lower()
            if "wait" in n:
                return "WAIT"
            if "move" in n:
                return "MOVE"

            # Prioritize explicit class semantics to avoid double-counting.
            if "indirect" in n:
                return "INDIRECT"
            if "rangeddirect" in n:
                return "DIRECT"
            if any(x in n for x in ("close", "direct", "assault", "attack", "fire", "shoot")):
                return "DIRECT"
            if "ranged" in n:
                return "INDIRECT"

            return "OTHER"

        for r in self.results:

            l1 = r.get("l1", {})
            l1_eff = r.get("l1_efficiency", {})
            # collect raw action_class names for diagnostics
            for side in ("RL", "ENEMY"):
                for action_class in l1.get(side, {}).keys():
                    action_name_counts[action_class] += l1.get(side, {}).get(action_class, 0)

            for side in ("RL", "ENEMY"):
                side_l1 = l1.get(side, {})
                side_eff = l1_eff.get(side, {})

                for action_class, count in side_l1.items():
                    try:
                        c = int(count)
                    except Exception:
                        c = 0

                    if c <= 0:
                        continue

                    atype = map_action_type(action_class)

                    dmg_per = 0.0
                    if isinstance(side_eff, dict):
                        dmg_per = side_eff.get(action_class, {}).get("damage_per_attack", 0.0)

                    by_side[side][atype]["count"] += c
                    by_side[side][atype]["damage"] += dmg_per * c

        # Build normalized output
        output = {}
        for side, data in by_side.items():
            output[side] = {}
            for k, v in data.items():
                c = v["count"]
                output[side][k] = {
                    "count": c,
                    "damage_per_action": v["damage"] / c if c else 0.0,
                }

        # attach diagnostics of raw action class usage
        self._action_class_counts = dict(action_name_counts)

        return output

    # -------------------------------------------------
    # PRINT REPORT
    # -------------------------------------------------
    def print_report(self):

        print("\n=== GLOBAL ===")
        summary = self.summary()
        print(summary)
        print("\n--- WIN RATE BY END REASON ---")
        for reason, rate in summary.get("win_rate_by_end_reason", {}).items():
            count = summary.get("end_reason_counts", {}).get(reason, 0)
            print(f"{reason}: win_rate={rate:.3f} episodes={count}")
        print("\n--- VICTORY LEVEL COUNTS ---")
        for label, count in summary.get("victory_level_counts", {}).items():
            print(f"{label}: {count}")

        print("\n=== COMBAT ===")
        print(self.combat_metrics())

        print("\n=== ADVANCED ===")
        for k, v in self.advanced_metrics().items():
            print(f"{k}: {v:.3f}")

        print("\n=== POLICY ALIGNMENT ===")
        align = self.policy_alignment()
        print(f"forced_ratio: {align['forced_ratio']:.3f} ({align['forced_steps']}/{align['decisions']})")

        # ---------------- L2 ----------------
        print("\n=== L2 POLICY PERFORMANCE ===")
        for k, v in sorted(
            compute_option_performance(self.results).items(),
            key=lambda x: x[1]["usage"],
            reverse=True
        ):
            print(f"{k}: usage={v['usage']} dmg/atk={v['damage_per_attack']:.3f}")

        # ---------------- L3 ----------------
        print("\n=== L3 POLICY PERFORMANCE ===")
        for k, v in sorted(
            compute_formation_performance(self.results).items(),
            key=lambda x: x[1]["usage"],
            reverse=True
        ):
            print(f"{k}: usage={v['usage']} dmg/atk={v['damage_per_attack']:.3f}")

        # ---------------- mapping ----------------
        print("\n=== STRATEGY → OPTION ===")

        mapping = normalize_strategy_option_map(
            build_strategy_option_map(self.results)
        )

        for strat, opts in mapping.items():
            print(f"\n{strat}:")
            for opt, (count, ratio) in opts.items():
                print(f"  {opt}: {count} ({ratio:.2%})")

        # ---------------- ✅ NUEVO ----------------
        print("\n=== ACTION EXECUTION (REAL) ===")

        actions = self.action_execution()

        # if structured per-side
        if isinstance(actions, dict) and any(s in actions for s in ("RL", "ENEMY")):
            for side in ("RL", "ENEMY"):
                side_name = "US" if side == "RL" else "OTHER SIDE"
                print(f"\n--- {side_name} ---")
                side_actions = actions.get(side, {})
                if not side_actions:
                    print("  (no actions)")
                    continue
                for k, v in side_actions.items():
                    print(
                        f"  {k}: count={v.get('count', 0)} dmg/action={v.get('damage_per_action', 0.0):.3f}"
                    )
        else:
            # legacy flat format
            for k, v in (actions or {}).items():
                print(
                    f"{k}: count={v.get('count', 0)} dmg/action={v.get('damage_per_action', 0.0):.3f}"
                )

        # ----------------- DIAGNOSTIC: raw action class names -----------------
        print("\n=== RAW ACTION_CLASS COUNTS (diagnostic) ===")
        counts = getattr(self, "_action_class_counts", {})
        if not counts:
            print("(no action class data)")
        else:
            for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:40]:
                print(f"  {k}: {v}")

        # ---------------- UNITS ----------------
        print("\n=== UNIT ANALYSIS (L1) ===")

        units = aggregate_units(self.results)
        print_all_units(units, self.rl_side)