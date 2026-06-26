import os
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
        self._use_color = os.getenv("NO_COLOR") is None

    def _c(self, text, color=None, bold=False):
        if not self._use_color:
            return str(text)
        codes = []
        if bold:
            codes.append("1")
        palette = {
            "red": "31",
            "green": "32",
            "yellow": "33",
            "blue": "34",
            "magenta": "35",
            "cyan": "36",
            "gray": "90",
        }
        if color in palette:
            codes.append(palette[color])
        if not codes:
            return str(text)
        return f"\033[{';'.join(codes)}m{text}\033[0m"

    def _section(self, title, color="cyan"):
        print(f"\n{self._c(f'=== {title} ===', color=color, bold=True)}")

    def _subsection(self, title, color="blue"):
        print(f"\n{self._c(f'--- {title} ---', color=color, bold=True)}")

    # -------------------------------------------------
    # GLOBAL
    # -------------------------------------------------
    def summary(self):

        score_wins = 0.0
        objective_wins = 0
        draws = 0
        losses = 0

        vp_list = []
        steps_list = []
        reason_counts = defaultdict(int)
        win_by_reason = defaultdict(float)
        rl_result_counts = defaultdict(int)
        tracked_result_counts = defaultdict(int)
        captured_final_counts = defaultdict(int)

        for r in self.results:

            reason = str(r.get("end_reason") or "unknown")
            reason_counts[reason] += 1
            rl_result = str(r.get("rl_result") or "draw")
            tracked_result = str(r.get("tracked_result") or "UNKNOWN")
            tracked_result_norm = tracked_result.strip().upper()
            rl_result_counts[rl_result] += 1
            tracked_result_counts[tracked_result] += 1
            victory_level = r.get("victory_level") or {}
            try:
                captured_final = int(victory_level.get("captured", -1))
                if captured_final >= 0:
                    captured_final_counts[str(captured_final)] += 1
            except Exception:
                pass

            is_objective_win = tracked_result_norm.startswith("VITTORIA")
            is_draw = tracked_result_norm == "PAREGGIO"
            if is_objective_win:
                score_wins += 1
                objective_wins += 1
                win_by_reason[reason] += 1
            elif is_draw:
                score_wins += 0.5
                draws += 1
                win_by_reason[reason] += 0.5
            else:
                losses += 1

            vp_list.append(r.get("vp", 0))
            steps_list.append(r.get("steps", 0))

        reason_win_rate = {}
        for reason, count in reason_counts.items():
            reason_win_rate[reason] = win_by_reason[reason] / max(1, count)

        return {
            "episodes": len(self.results),
            # Objective-based score metric (draw=0.5): derived from tracked_result.
            "win_rate": score_wins / len(self.results) if self.results else 0,
            "win_score_rate": score_wins / len(self.results) if self.results else 0,
            # Canonical win criterion: scenario objective outcome (tracked_result startswith "Vittoria").
            "true_win_rate": objective_wins / len(self.results) if self.results else 0,
            "draw_rate": draws / len(self.results) if self.results else 0,
            "loss_rate": losses / len(self.results) if self.results else 0,
            "draws": draws,
            "losses": losses,
            "avg_vp": statistics.mean(vp_list) if vp_list else 0,
            "avg_steps": statistics.mean(steps_list) if steps_list else 0,
            "end_reason_counts": dict(reason_counts),
            "win_rate_by_end_reason": reason_win_rate,
            "victory_level_counts": self.victory_level_counts(),
            "rl_result_counts": dict(rl_result_counts),
            "tracked_result_counts": dict(tracked_result_counts),
            "captured_final_counts": dict(captured_final_counts),
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
            "total_damage_rl": total_damage,
            "total_damage_enemy": total_taken,
            "trade_samples": trade_count,
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
        composite_available_count = 0
        composite_selected_count = 0
        composite_available_decisions = 0
        for r in self.results:
            align = r.get("decision_alignment", {})
            forced_steps += int(align.get("forced_steps", 0))
            decisions += int(align.get("rl_decisions", 0))
            composite_available_count += int(align.get("composite_available_count", 0))
            composite_selected_count += int(align.get("composite_selected_count", 0))
            composite_available_decisions += int(align.get("composite_available_decisions", 0))
            for k, v in align.get("sampled_to_executed_counts", {}).items():
                sampled_to_executed[k] += int(v)
        top_paths = dict(sorted(sampled_to_executed.items(), key=lambda kv: kv[1], reverse=True)[:10])
        return {
            "forced_steps": forced_steps,
            "decisions": decisions,
            "forced_ratio": forced_steps / max(1, decisions),
            "top_sampled_to_executed": top_paths,
            "composite_available_count": composite_available_count,
            "composite_selected_count": composite_selected_count,
            "composite_available_decisions": composite_available_decisions,
            "composite_selection_rate_when_available": (
                composite_selected_count / max(1, composite_available_decisions)
            ),
        }

    # -------------------------------------------------
    # MISSION METRICS (capture-focused)
    # -------------------------------------------------
    def mission_metrics(self):
        def _percentile(values, q):
            if not values:
                return None
            xs = sorted(float(v) for v in values)
            if len(xs) == 1:
                return xs[0]
            pos = (len(xs) - 1) * q
            lo = int(pos)
            hi = min(lo + 1, len(xs) - 1)
            frac = pos - lo
            return xs[lo] * (1.0 - frac) + xs[hi] * frac

        total_contact_steps = 0
        total_hold_steps = 0
        total_decisions = 0
        first_contact_turns = []
        first_progress_turns = []
        first_vp_entry_turns = []
        contact_to_progress_delays = []
        progress_to_capture_delays = []
        latency_invalid_order_total = 0
        latency_missing_progress_total = 0
        latency_missing_capture_total = 0
        stuck_ratios = []
        concentration = []
        vp_entry_opportunities = 0
        vp_entries_taken = 0
        contact_events_total = 0
        contact_to_capture_success_total = 0
        vp_net_progress_vals = []
        reversal_rates = []
        near_vp_attack_missed_rates = []
        vp_control_turns_share_vals = []
        capture_attempt_success_rates = []
        capture_attempted_total = 0
        capture_committed_total = 0
        capture_cancelled_by_finalizer_total = 0
        capture_cancelled_by_finalizer_reason_totals = defaultdict(int)
        fallback_to_attack_capture_rates = []
        capture_intent_persistence_rates = []
        attack_opportunity_cost_near_vp_rates = []
        vp_control_auc_vals = []
        contributing_attack_units = []
        contributing_damage_units = []
        intent_commitment_stub_rates = []
        role_diversity_stub_vals = []
        plan_role_counts_totals = defaultdict(int)
        plan_focus_switch_total = 0
        plan_stage_counts_totals = defaultdict(int)
        plan_replan_reason_totals = defaultdict(int)
        plan_fallback_reason_totals = defaultdict(int)
        plan_role_unknown_reason_totals = defaultdict(int)
        capture_branch_totals = defaultdict(int)
        near_vp_l2_transition_totals = defaultdict(int)
        near_vp_l2_transition_by_l3_totals = defaultdict(int)
        budget_remaining_by_role_totals = defaultdict(int)
        budget_violation_total = 0
        budget_violation_rates = []
        budget_compliance_rates = []
        action_finalize_reason_totals = defaultdict(int)
        lote_e_attack_cost_vals = []
        lote_e_capture_window_vals = []
        lote_e_expected_vp_swing_vals = []
        lote_e_expected_trade_vals = []
        strategy_option_totals = defaultdict(lambda: defaultdict(int))
        capture_fallback_reason_totals = defaultdict(int)
        capture_move_block_profile_totals = defaultdict(int)
        capture_override_reason_totals = defaultdict(int)
        l3_capture_forced_total = 0
        l3_capture_forced_rates = []
        l3_capture_force_reason_totals = defaultdict(int)
        post_open_window_followup_advance_total = 0
        post_open_window_followup_success_total = 0
        capture_emergency_override_rates = []
        capture_legal_override_rates = []
        capture_emergency_override_total = 0
        capture_legal_override_total = 0
        capture_progress_available_rates = []
        capture_suspected_progress_miss_rates = []
        capture_progress_available_total = 0
        capture_suspected_progress_miss_total = 0
        capture_progress_candidate_totals = 0
        capture_equal_candidate_totals = 0
        capture_increase_candidate_totals = 0
        capture_move_candidates_totals = 0
        capture_reversal_filtered_totals = 0
        capture_selected_move_reason_totals = defaultdict(int)
        attack_fallback_to_move_total = 0
        attack_fallback_reason_totals = defaultdict(int)
        vp_stepin_legal_total = 0
        vp_stepin_selected_total = 0
        vp_stepin_block_reason_totals = defaultdict(int)
        vp_no_legal_stepin_near_total = 0
        vp_opening_attack_candidates_total = 0
        stepin_legal_mask_total = 0
        stepin_forced_option_total = 0
        vp_control_after_entry_turns_all = []
        per_unit_vp_entry_attempts_totals = defaultdict(int)
        per_unit_vp_entry_success_totals = defaultdict(int)
        plan_success_k_vals = []
        plan_latency_to_progress_vals = []
        invalid_action_total = 0
        fallback_action_total = 0
        wait_recovery_sb3_backstep_total = 0
        reward_component_values = defaultdict(list)
        source_mix_counts_totals = defaultdict(int)
        source_mix_capture_event_totals = defaultdict(int)
        plan_progress_rates = []
        coordination_gain_vals = []
        avg_legal_actions_vals = []
        action_catalog_gen_ms_vals = []
        avg_legal_actions_by_side_totals = defaultdict(float)
        avg_legal_actions_by_side_counts = defaultdict(int)
        action_catalog_gen_ms_by_side_totals = defaultdict(float)
        action_catalog_gen_ms_by_side_counts = defaultdict(int)

        for r in self.results:
            mission = r.get("mission", {}) or {}
            total_contact_steps += int(mission.get("vp_contact_steps", 0))
            total_hold_steps += int(mission.get("vp_hold_steps", 0))
            align = r.get("decision_alignment", {}) or {}
            decisions = int(align.get("rl_decisions", 0))
            total_decisions += decisions
            first_turn = mission.get("first_vp_contact_turn")
            if isinstance(first_turn, (int, float)) and first_turn > 0:
                first_contact_turns.append(float(first_turn))
            first_progress = mission.get("turn_first_progress")
            if isinstance(first_progress, (int, float)) and first_progress > 0:
                first_progress_turns.append(float(first_progress))

            formation_counts = r.get("formation_counts", {}) or {}
            if decisions > 0 and formation_counts:
                dominant = max(int(v) for v in formation_counts.values())
                stuck_ratios.append(dominant / decisions)

            units_rl = (r.get("units", {}) or {}).get("RL", {}) or {}
            dmg_vals = [float((stats or {}).get("damage", 0)) for stats in units_rl.values()]
            total_dmg = sum(dmg_vals)
            if total_dmg > 0:
                concentration.append(max(dmg_vals) / total_dmg)
            vp_entry_opportunities += int(mission.get("vp_entry_opportunities", 0))
            vp_entries_taken += int(mission.get("vp_entries_taken", 0))
            if "vp_net_progress" in mission:
                try:
                    vp_net_progress_vals.append(float(mission.get("vp_net_progress", 0.0)))
                except Exception:
                    pass
            if "position_reversal_rate" in mission:
                try:
                    reversal_rates.append(float(mission.get("position_reversal_rate", 0.0)))
                except Exception:
                    pass
            if "attack_near_vp_instead_of_capture_rate" in mission:
                try:
                    near_vp_attack_missed_rates.append(float(mission.get("attack_near_vp_instead_of_capture_rate", 0.0)))
                except Exception:
                    pass
            if "vp_control_turns_share" in mission:
                try:
                    vp_control_turns_share_vals.append(float(mission.get("vp_control_turns_share", 0.0)))
                except Exception:
                    pass
            if "capture_attempt_success_rate" in mission:
                try:
                    capture_attempt_success_rates.append(float(mission.get("capture_attempt_success_rate", 0.0)))
                except Exception:
                    pass
            try:
                capture_attempted_total += int(mission.get("capture_attempted", 0) or 0)
                capture_committed_total += int(mission.get("capture_committed", 0) or 0)
                capture_cancelled_by_finalizer_total += int(
                    mission.get("capture_cancelled_by_finalizer", 0) or 0
                )
            except Exception:
                pass
            for reason, count in (mission.get("capture_cancelled_by_finalizer_reason_counts", {}) or {}).items():
                try:
                    capture_cancelled_by_finalizer_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            if "first_vp_entry_turn" in mission:
                first_entry = mission.get("first_vp_entry_turn")
                if isinstance(first_entry, (int, float)) and first_entry > 0:
                    first_vp_entry_turns.append(float(first_entry))
            c2p = mission.get("contact_to_progress_delay")
            if isinstance(c2p, (int, float)):
                contact_to_progress_delays.append(float(c2p))
            p2c = mission.get("progress_to_capture_delay")
            if isinstance(p2c, (int, float)):
                progress_to_capture_delays.append(float(p2c))
            latency_invalid_order_total += int(mission.get("latency_invalid_order_count", 0) or 0)
            latency_missing_progress_total += int(mission.get("latency_missing_progress_count", 0) or 0)
            latency_missing_capture_total += int(mission.get("latency_missing_capture_count", 0) or 0)
            contact_events_total += int(mission.get("contact_events", 0))
            contact_to_capture_success_total += int(mission.get("contact_to_capture_success", 0))
            if "capture_intent_persistence" in mission:
                try:
                    capture_intent_persistence_rates.append(float(mission.get("capture_intent_persistence", 0.0)))
                except Exception:
                    pass
            if "attack_opportunity_cost_near_vp" in mission:
                try:
                    attack_opportunity_cost_near_vp_rates.append(float(mission.get("attack_opportunity_cost_near_vp", 0.0)))
                except Exception:
                    pass
            if "vp_control_auc" in mission:
                try:
                    vp_control_auc_vals.append(float(mission.get("vp_control_auc", 0.0)))
                except Exception:
                    pass
            if "intent_commitment_rate_stub" in mission:
                try:
                    intent_commitment_stub_rates.append(float(mission.get("intent_commitment_rate_stub", 0.0)))
                except Exception:
                    pass
            if "role_diversity_index_stub" in mission:
                try:
                    role_diversity_stub_vals.append(float(mission.get("role_diversity_index_stub", 0.0)))
                except Exception:
                    pass
            for role, count in (mission.get("plan_role_counts_stub", {}) or {}).items():
                try:
                    plan_role_counts_totals[str(role)] += int(count)
                except Exception:
                    pass
            try:
                plan_focus_switch_total += int(mission.get("plan_focus_switch_count", 0))
            except Exception:
                pass
            for stage, count in (mission.get("plan_stage_counts", {}) or {}).items():
                try:
                    plan_stage_counts_totals[str(stage)] += int(count)
                except Exception:
                    pass
            for reason, count in (mission.get("plan_replan_reason_counts", {}) or {}).items():
                try:
                    plan_replan_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            for reason, count in (mission.get("plan_fallback_reason_counts", {}) or {}).items():
                try:
                    plan_fallback_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            for reason, count in (mission.get("plan_role_unknown_reason_counts", {}) or {}).items():
                try:
                    plan_role_unknown_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            for branch, count in (mission.get("capture_branch_counts", {}) or {}).items():
                try:
                    capture_branch_totals[str(branch)] += int(count)
                except Exception:
                    pass
            for key, count in (mission.get("near_vp_l2_transition_counts", {}) or {}).items():
                try:
                    near_vp_l2_transition_totals[str(key)] += int(count)
                except Exception:
                    pass
            for key, count in (mission.get("near_vp_l2_transition_by_l3_counts", {}) or {}).items():
                try:
                    near_vp_l2_transition_by_l3_totals[str(key)] += int(count)
                except Exception:
                    pass
            for role, remaining in (mission.get("budget_remaining_by_role", {}) or {}).items():
                try:
                    budget_remaining_by_role_totals[str(role)] += int(remaining)
                except Exception:
                    pass
            try:
                budget_violation_total += int(mission.get("budget_violation_count", 0))
            except Exception:
                pass
            if "budget_violation_rate" in mission:
                try:
                    budget_violation_rates.append(float(mission.get("budget_violation_rate", 0.0)))
                except Exception:
                    pass
            if "budget_compliance_rate" in mission:
                try:
                    budget_compliance_rates.append(float(mission.get("budget_compliance_rate", 1.0)))
                except Exception:
                    pass
            for reason, count in (mission.get("action_finalize_reason_counts", {}) or {}).items():
                try:
                    action_finalize_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            if "lote_e_attack_opportunity_cost_near_vp_norm" in mission:
                try:
                    lote_e_attack_cost_vals.append(float(mission.get("lote_e_attack_opportunity_cost_near_vp_norm", 0.0)))
                except Exception:
                    pass
            if "lote_e_capture_window_open_rate" in mission:
                try:
                    lote_e_capture_window_vals.append(float(mission.get("lote_e_capture_window_open_rate", 0.0)))
                except Exception:
                    pass
            if "lote_e_expected_vp_swing_if_advance" in mission:
                try:
                    lote_e_expected_vp_swing_vals.append(float(mission.get("lote_e_expected_vp_swing_if_advance", 0.0)))
                except Exception:
                    pass
            if "lote_e_expected_trade_if_attack" in mission:
                try:
                    lote_e_expected_trade_vals.append(float(mission.get("lote_e_expected_trade_if_attack", 0.0)))
                except Exception:
                    pass
            if "fallback_to_attack_rate_in_capture" in mission:
                try:
                    fallback_to_attack_capture_rates.append(float(mission.get("fallback_to_attack_rate_in_capture", 0.0)))
                except Exception:
                    pass
            for reason, count in (mission.get("capture_fallback_reason_counts", {}) or {}).items():
                try:
                    capture_fallback_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            for reason, count in (mission.get("capture_move_block_profile", {}) or {}).items():
                try:
                    capture_move_block_profile_totals[str(reason)] += int(count)
                except Exception:
                    pass
            for reason, count in (mission.get("capture_override_reason_counts", {}) or {}).items():
                try:
                    capture_override_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            try:
                l3_capture_forced_total += int(mission.get("l3_capture_forced_count", 0))
            except Exception:
                pass
            if "l3_capture_forced_rate" in mission:
                try:
                    l3_capture_forced_rates.append(float(mission.get("l3_capture_forced_rate", 0.0)))
                except Exception:
                    pass
            for reason, count in (mission.get("l3_capture_force_reason_counts", {}) or {}).items():
                try:
                    l3_capture_force_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            try:
                post_open_window_followup_advance_total += int(mission.get("post_open_window_followup_advance_count", 0))
                post_open_window_followup_success_total += int(mission.get("post_open_window_followup_success_count", 0))
            except Exception:
                pass
            try:
                capture_emergency_override_total += int(mission.get("capture_emergency_override_count", 0))
                capture_legal_override_total += int(mission.get("capture_legal_override_count", 0))
                capture_progress_available_total += int(mission.get("capture_progress_available_count", 0))
                capture_suspected_progress_miss_total += int(mission.get("capture_suspected_progress_miss_count", 0))
                capture_progress_candidate_totals += int(mission.get("capture_progress_candidate_total", 0))
                capture_equal_candidate_totals += int(mission.get("capture_equal_candidate_total", 0))
                capture_increase_candidate_totals += int(mission.get("capture_increase_candidate_total", 0))
                capture_move_candidates_totals += int(mission.get("capture_move_candidates_total", 0))
                capture_reversal_filtered_totals += int(mission.get("capture_reversal_filtered_total", 0))
            except Exception:
                pass
            if "capture_emergency_override_rate" in mission:
                try:
                    capture_emergency_override_rates.append(float(mission.get("capture_emergency_override_rate", 0.0)))
                except Exception:
                    pass
            if "capture_legal_override_rate" in mission:
                try:
                    capture_legal_override_rates.append(float(mission.get("capture_legal_override_rate", 0.0)))
                except Exception:
                    pass
            if "capture_progress_available_rate" in mission:
                try:
                    capture_progress_available_rates.append(float(mission.get("capture_progress_available_rate", 0.0)))
                except Exception:
                    pass
            if "capture_suspected_progress_miss_rate" in mission:
                try:
                    capture_suspected_progress_miss_rates.append(float(mission.get("capture_suspected_progress_miss_rate", 0.0)))
                except Exception:
                    pass
            for reason, count in (mission.get("capture_selected_move_reason_counts", {}) or {}).items():
                try:
                    capture_selected_move_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            try:
                attack_fallback_to_move_total += int(mission.get("attack_fallback_to_move_count", 0))
            except Exception:
                pass
            for reason, count in (mission.get("attack_fallback_reason_counts", {}) or {}).items():
                try:
                    attack_fallback_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            try:
                vp_stepin_legal_total += int(mission.get("vp_stepin_legal_count", 0))
                vp_stepin_selected_total += int(mission.get("vp_stepin_selected_count", 0))
            except Exception:
                pass
            for reason, count in (mission.get("vp_stepin_block_reason_counts", {}) or {}).items():
                try:
                    vp_stepin_block_reason_totals[str(reason)] += int(count)
                except Exception:
                    pass
            try:
                vp_no_legal_stepin_near_total += int(mission.get("vp_no_legal_stepin_near_count", 0))
            except Exception:
                pass
            try:
                vp_opening_attack_candidates_total += int(mission.get("vp_opening_attack_candidates_total", 0))
            except Exception:
                pass
            try:
                stepin_legal_mask_total += int(mission.get("stepin_legal_mask_count", 0))
                stepin_forced_option_total += int(mission.get("stepin_forced_option_count", 0))
            except Exception:
                pass
            for v in (mission.get("vp_control_after_entry_turns", []) or []):
                try:
                    vp_control_after_entry_turns_all.append(float(v))
                except Exception:
                    pass
            for uid, count in (mission.get("per_unit_vp_entry_attempts", {}) or {}).items():
                try:
                    per_unit_vp_entry_attempts_totals[str(uid)] += int(count)
                except Exception:
                    pass
            for uid, count in (mission.get("per_unit_vp_entry_success", {}) or {}).items():
                try:
                    per_unit_vp_entry_success_totals[str(uid)] += int(count)
                except Exception:
                    pass
            if "plan_success_k" in mission:
                try:
                    plan_success_k_vals.append(float(mission.get("plan_success_k", 0.0)))
                except Exception:
                    pass
            if mission.get("plan_latency_to_progress") is not None:
                try:
                    plan_latency_to_progress_vals.append(float(mission.get("plan_latency_to_progress")))
                except Exception:
                    pass
            try:
                invalid_action_total += int(mission.get("invalid_action_count", 0))
                fallback_action_total += int(mission.get("fallback_action_count", 0))
                wait_recovery_sb3_backstep_total += int(mission.get("wait_recovery_sb3_backstep_count", 0))
            except Exception:
                pass
            for k, v in (mission.get("reward_component_means", {}) or {}).items():
                try:
                    reward_component_values[str(k)].append(float(v))
                except Exception:
                    pass
            for k, v in (mission.get("source_mix_counts", {}) or {}).items():
                try:
                    source_mix_counts_totals[str(k)] += int(v)
                except Exception:
                    pass
            for k, v in (mission.get("source_mix_capture_event_counts", {}) or {}).items():
                try:
                    source_mix_capture_event_totals[str(k)] += int(v)
                except Exception:
                    pass
            if "plan_progress_rate" in mission:
                try:
                    plan_progress_rates.append(float(mission.get("plan_progress_rate", 0.0)))
                except Exception:
                    pass
            if "coordination_gain" in mission:
                try:
                    coordination_gain_vals.append(float(mission.get("coordination_gain", 0.0)))
                except Exception:
                    pass
            if "avg_legal_actions_per_decision" in mission:
                try:
                    avg_legal_actions_vals.append(float(mission.get("avg_legal_actions_per_decision", 0.0)))
                except Exception:
                    pass
            if "mean_action_catalog_gen_ms" in mission:
                try:
                    action_catalog_gen_ms_vals.append(float(mission.get("mean_action_catalog_gen_ms", 0.0)))
                except Exception:
                    pass
            for k, v in (mission.get("avg_legal_actions_per_decision_by_side", {}) or {}).items():
                try:
                    avg_legal_actions_by_side_totals[str(k)] += float(v)
                    avg_legal_actions_by_side_counts[str(k)] += 1
                except Exception:
                    pass
            for k, v in (mission.get("mean_action_catalog_gen_ms_by_side", {}) or {}).items():
                try:
                    action_catalog_gen_ms_by_side_totals[str(k)] += float(v)
                    action_catalog_gen_ms_by_side_counts[str(k)] += 1
                except Exception:
                    pass

            atk_units = 0
            dmg_units = 0
            for stats in units_rl.values():
                if int((stats or {}).get("attacks", 0)) > 0:
                    atk_units += 1
                if float((stats or {}).get("damage", 0)) > 0:
                    dmg_units += 1
            contributing_attack_units.append(atk_units)
            contributing_damage_units.append(dmg_units)

            mapping = r.get("strategy_option_map", {}) or {}
            for strat, opts in mapping.items():
                for opt, count in (opts or {}).items():
                    strategy_option_totals[str(strat)][str(opt)] += int(count)

        transition_matrix = {
            strat: dict(opts) for strat, opts in strategy_option_totals.items()
        }
        vp_contact_rate = (total_contact_steps + total_hold_steps) / max(1, total_decisions)
        capture_pressure_turn = statistics.mean(first_contact_turns) if first_contact_turns else None
        strategy_stuck_ratio = statistics.mean(stuck_ratios) if stuck_ratios else 0.0
        unit_concentration_index = statistics.mean(concentration) if concentration else 0.0

        checks = {
            "strategy_stuck_ok": strategy_stuck_ratio < 0.90,
            "unit_concentration_ok": unit_concentration_index < 0.80,
            "vp_contact_ok": vp_contact_rate > 0.15,
        }
        passed = sum(1 for ok in checks.values() if ok)
        if passed == 3:
            stability_status = "green"
        elif passed >= 1:
            stability_status = "yellow"
        else:
            stability_status = "red"

        vp_entry_conversion_rate = (
            (vp_entries_taken / vp_entry_opportunities)
            if vp_entry_opportunities > 0 else None
        )
        vp_entry_missed_rate = (
            1.0 - vp_entry_conversion_rate
            if vp_entry_conversion_rate is not None else None
        )
        capture_conversion_after_contact = (
            (contact_to_capture_success_total / contact_events_total)
            if contact_events_total > 0 else 0.0
        )
        capture_attempt_success_rate = (
            statistics.mean(capture_attempt_success_rates) if capture_attempt_success_rates else 0.0
        )
        fallback_to_attack_rate_in_capture = (
            statistics.mean(fallback_to_attack_capture_rates) if fallback_to_attack_capture_rates else 0.0
        )

        capture_checks = {
            "vp_contact_min": vp_contact_rate > 0.20,
            "pressure_turn_set": capture_pressure_turn is not None,
            "concentration_ok": unit_concentration_index < 0.80,
            "vp_entry_missed_ok": (vp_entry_missed_rate is not None) and (vp_entry_missed_rate < 0.90),
            "capture_success_ok": capture_attempt_success_rate >= 0.05,
            "capture_fallback_ok": fallback_to_attack_rate_in_capture < 0.55,
        }
        capture_readiness = all(capture_checks.values())
        # Final status must reflect both behavioral stability and capture readiness.
        if passed == 3 and capture_readiness:
            stability_status = "green"
        elif passed >= 1:
            stability_status = "yellow"
        else:
            stability_status = "red"

        return {
            "vp_contact_rate": vp_contact_rate,
            "capture_pressure_turn": capture_pressure_turn,
            "strategy_stuck_ratio": strategy_stuck_ratio,
            "unit_concentration_index": unit_concentration_index,
            "objective_transition_matrix": transition_matrix,
            "vp_entry_opportunities": vp_entry_opportunities,
            "vp_entries_taken": vp_entries_taken,
            "vp_entry_conversion_rate": vp_entry_conversion_rate,
            "vp_entry_missed_rate": vp_entry_missed_rate,
            "vp_net_progress": statistics.mean(vp_net_progress_vals) if vp_net_progress_vals else 0.0,
            "position_reversal_rate": statistics.mean(reversal_rates) if reversal_rates else 0.0,
            "attack_near_vp_instead_of_capture_rate": (
                statistics.mean(near_vp_attack_missed_rates) if near_vp_attack_missed_rates else 0.0
            ),
            "vp_control_turns_share": (
                statistics.mean(vp_control_turns_share_vals) if vp_control_turns_share_vals else 0.0
            ),
            "capture_attempt_success_rate": capture_attempt_success_rate,
            "capture_attempted": int(capture_attempted_total),
            "capture_committed": int(capture_committed_total),
            "capture_cancelled_by_finalizer": int(capture_cancelled_by_finalizer_total),
            "capture_cancelled_by_finalizer_rate": (
                float(capture_cancelled_by_finalizer_total) / max(1.0, float(capture_attempted_total))
            ),
            "capture_cancelled_by_finalizer_reason_counts": dict(
                capture_cancelled_by_finalizer_reason_totals
            ),
            "first_vp_entry_turn_p50": _percentile(first_vp_entry_turns, 0.50),
            "first_vp_entry_turn_p90": _percentile(first_vp_entry_turns, 0.90),
            "turn_first_contact": _percentile(first_contact_turns, 0.50),
            "turn_first_progress": _percentile(first_progress_turns, 0.50),
            "turn_first_capture": _percentile(first_vp_entry_turns, 0.50),
            "contact_to_progress_delay": _percentile(contact_to_progress_delays, 0.50),
            "progress_to_capture_delay": _percentile(progress_to_capture_delays, 0.50),
            "latency_invalid_order_count": int(latency_invalid_order_total),
            "latency_missing_progress_count": int(latency_missing_progress_total),
            "latency_missing_capture_count": int(latency_missing_capture_total),
            "capture_conversion_after_contact": capture_conversion_after_contact,
            "capture_intent_persistence": (
                statistics.mean(capture_intent_persistence_rates)
                if capture_intent_persistence_rates else 0.0
            ),
            "attack_opportunity_cost_near_vp": (
                statistics.mean(attack_opportunity_cost_near_vp_rates)
                if attack_opportunity_cost_near_vp_rates else 0.0
            ),
            "vp_control_auc": (
                statistics.mean(vp_control_auc_vals) if vp_control_auc_vals else 0.0
            ),
            "intent_commitment_rate_stub": (
                statistics.mean(intent_commitment_stub_rates) if intent_commitment_stub_rates else 0.0
            ),
            "role_diversity_index_stub": (
                statistics.mean(role_diversity_stub_vals) if role_diversity_stub_vals else 0.0
            ),
            "intent_commitment_rate": (
                statistics.mean(intent_commitment_stub_rates) if intent_commitment_stub_rates else 0.0
            ),
            "role_diversity_index": (
                statistics.mean(role_diversity_stub_vals) if role_diversity_stub_vals else 0.0
            ),
            "plan_role_counts_stub": dict(plan_role_counts_totals),
            "plan_focus_switch_count": int(plan_focus_switch_total),
            "plan_commit_rate": (
                1.0 - (float(plan_focus_switch_total) / max(1.0, float(total_decisions)))
            ),
            "focus_switch_rate": (
                float(plan_focus_switch_total) / max(1.0, float(total_decisions))
            ),
            "plan_stage_counts": dict(plan_stage_counts_totals),
            "plan_replan_reason_counts": dict(plan_replan_reason_totals),
            "plan_fallback_reason_counts": dict(plan_fallback_reason_totals),
            "plan_role_unknown_reason_counts": dict(plan_role_unknown_reason_totals),
            "capture_branch_counts": dict(capture_branch_totals),
            "near_vp_l2_transition_counts": dict(near_vp_l2_transition_totals),
            "near_vp_l2_transition_by_l3_counts": dict(near_vp_l2_transition_by_l3_totals),
            "budget_remaining_by_role": dict(budget_remaining_by_role_totals),
            "budget_violation_count": int(budget_violation_total),
            "budget_violation_rate": (
                statistics.mean(budget_violation_rates) if budget_violation_rates else 0.0
            ),
            "budget_compliance_rate": (
                statistics.mean(budget_compliance_rates) if budget_compliance_rates else 1.0
            ),
            "action_finalize_reason_counts": dict(action_finalize_reason_totals),
            "invalid_action_count": int(invalid_action_total),
            "fallback_action_count": int(fallback_action_total),
            "wait_recovery_sb3_backstep_count": int(wait_recovery_sb3_backstep_total),
            "invalid_action_rate": (
                float(invalid_action_total) / max(1.0, float(total_decisions))
            ),
            "fallback_rate": (
                float(fallback_action_total) / max(1.0, float(total_decisions))
            ),
            "wait_recovery_sb3_backstep_rate": (
                float(wait_recovery_sb3_backstep_total) / max(1.0, float(total_decisions))
            ),
            "reward_component_means": {
                k: statistics.mean(vals) for k, vals in reward_component_values.items() if vals
            },
            "source_mix_counts": dict(source_mix_counts_totals),
            "source_mix_rates": {
                k: (float(v) / max(1.0, float(total_decisions)))
                for k, v in source_mix_counts_totals.items()
            },
            "source_mix_capture_event_counts": dict(source_mix_capture_event_totals),
            "source_mix_capture_event_rates": {
                k: (
                    float(source_mix_capture_event_totals.get(k, 0))
                    / max(1.0, float(source_mix_counts_totals.get(k, 0)))
                )
                for k in source_mix_counts_totals.keys()
            },
            "finalizer_override_reason_counts": {
                k: int(v)
                for k, v in action_finalize_reason_totals.items()
                if str(k) != "ok"
            },
            "finalizer_override_reason_rates": {
                k: (
                    float(v)
                    / max(1.0, float(source_mix_counts_totals.get("finalizer_override", 0)))
                )
                for k, v in action_finalize_reason_totals.items()
                if str(k) != "ok"
            },
            "plan_progress_rate": (
                statistics.mean(plan_progress_rates) if plan_progress_rates else 0.0
            ),
            "coordination_gain": (
                statistics.mean(coordination_gain_vals) if coordination_gain_vals else 0.0
            ),
            "avg_legal_actions_per_decision": (
                statistics.mean(avg_legal_actions_vals) if avg_legal_actions_vals else 0.0
            ),
            "mean_action_catalog_gen_ms": (
                statistics.mean(action_catalog_gen_ms_vals) if action_catalog_gen_ms_vals else 0.0
            ),
            "avg_legal_actions_per_decision_by_side": {
                k: (
                    float(avg_legal_actions_by_side_totals.get(k, 0.0))
                    / max(1.0, float(avg_legal_actions_by_side_counts.get(k, 0)))
                )
                for k in avg_legal_actions_by_side_totals.keys()
            },
            "mean_action_catalog_gen_ms_by_side": {
                k: (
                    float(action_catalog_gen_ms_by_side_totals.get(k, 0.0))
                    / max(1.0, float(action_catalog_gen_ms_by_side_counts.get(k, 0)))
                )
                for k in action_catalog_gen_ms_by_side_totals.keys()
            },
            "plan_success_k": (
                statistics.mean(plan_success_k_vals) if plan_success_k_vals else 0.0
            ),
            "plan_latency_to_progress": (
                statistics.mean(plan_latency_to_progress_vals) if plan_latency_to_progress_vals else None
            ),
            "lote_e_attack_opportunity_cost_near_vp_norm": (
                statistics.mean(lote_e_attack_cost_vals) if lote_e_attack_cost_vals else 0.0
            ),
            "lote_e_capture_window_open_rate": (
                statistics.mean(lote_e_capture_window_vals) if lote_e_capture_window_vals else 0.0
            ),
            "lote_e_expected_vp_swing_if_advance": (
                statistics.mean(lote_e_expected_vp_swing_vals) if lote_e_expected_vp_swing_vals else 0.0
            ),
            "lote_e_expected_trade_if_attack": (
                statistics.mean(lote_e_expected_trade_vals) if lote_e_expected_trade_vals else 0.0
            ),
            "fallback_to_attack_rate_in_capture": fallback_to_attack_rate_in_capture,
            "capture_fallback_reason_counts": dict(capture_fallback_reason_totals),
            "capture_move_block_profile": dict(capture_move_block_profile_totals),
            "capture_override_reason_counts": dict(capture_override_reason_totals),
            "l3_capture_forced_count": int(l3_capture_forced_total),
            "l3_capture_forced_rate": (
                statistics.mean(l3_capture_forced_rates) if l3_capture_forced_rates else 0.0
            ),
            "l3_capture_force_reason_counts": dict(l3_capture_force_reason_totals),
            "post_open_window_followup_advance_count": int(post_open_window_followup_advance_total),
            "post_open_window_followup_success_count": int(post_open_window_followup_success_total),
            "post_open_window_followup_success_rate": (
                post_open_window_followup_success_total / max(1, post_open_window_followup_advance_total)
            ),
            "capture_emergency_override_count": int(capture_emergency_override_total),
            "capture_legal_override_count": int(capture_legal_override_total),
            "capture_progress_available_count": int(capture_progress_available_total),
            "capture_suspected_progress_miss_count": int(capture_suspected_progress_miss_total),
            "capture_progress_candidate_total": int(capture_progress_candidate_totals),
            "capture_equal_candidate_total": int(capture_equal_candidate_totals),
            "capture_increase_candidate_total": int(capture_increase_candidate_totals),
            "capture_move_candidates_total": int(capture_move_candidates_totals),
            "capture_reversal_filtered_total": int(capture_reversal_filtered_totals),
            "capture_selected_move_reason_counts": dict(capture_selected_move_reason_totals),
            "attack_fallback_to_move_count": int(attack_fallback_to_move_total),
            "attack_fallback_reason_counts": dict(attack_fallback_reason_totals),
            "vp_stepin_legal_count": int(vp_stepin_legal_total),
            "vp_stepin_selected_count": int(vp_stepin_selected_total),
            "vp_stepin_selection_rate": (
                vp_stepin_selected_total / max(1, vp_stepin_legal_total)
            ),
            "vp_stepin_block_reason_counts": dict(vp_stepin_block_reason_totals),
            "vp_no_legal_stepin_near_count": int(vp_no_legal_stepin_near_total),
            "vp_opening_attack_candidates_total": int(vp_opening_attack_candidates_total),
            "stepin_legal_mask_count": int(stepin_legal_mask_total),
            "stepin_forced_option_count": int(stepin_forced_option_total),
            "vp_control_after_entry_turns_p50": _percentile(vp_control_after_entry_turns_all, 0.50),
            "vp_control_after_entry_turns_p90": _percentile(vp_control_after_entry_turns_all, 0.90),
            "per_unit_vp_entry_attempts": dict(per_unit_vp_entry_attempts_totals),
            "per_unit_vp_entry_success": dict(per_unit_vp_entry_success_totals),
            "capture_emergency_override_rate": (
                statistics.mean(capture_emergency_override_rates) if capture_emergency_override_rates else 0.0
            ),
            "capture_legal_override_rate": (
                statistics.mean(capture_legal_override_rates) if capture_legal_override_rates else 0.0
            ),
            "capture_progress_available_rate": (
                statistics.mean(capture_progress_available_rates) if capture_progress_available_rates else 0.0
            ),
            "capture_suspected_progress_miss_rate": (
                statistics.mean(capture_suspected_progress_miss_rates) if capture_suspected_progress_miss_rates else 0.0
            ),
            "multi_unit_contribution": {
                "attack_units_mean": (
                    statistics.mean(contributing_attack_units) if contributing_attack_units else 0.0
                ),
                "damage_units_mean": (
                    statistics.mean(contributing_damage_units) if contributing_damage_units else 0.0
                ),
            },
            "stability_checks": checks,
            "stability_status": stability_status,
            "capture_checks": capture_checks,
            "capture_readiness": capture_readiness,
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
            # Composite move/fire actions must be detected before generic "move".
            if "movethenfire" in n or "move_then_fire" in n:
                return "MOVE_THEN_FIRE"
            if "firethenmove" in n or "fire_then_move" in n:
                return "FIRE_THEN_MOVE"
            if "wait" in n:
                return "WAIT"
            if "move" in n:
                return "MOVE"

            # Prioritize explicit class semantics to avoid double-counting.
            if "assault" in n or "closecombat" in n or "close_combat" in n:
                return "ASSAULT_MELEE"
            if "indirect" in n:
                return "INDIRECT"
            if "rangeddirect" in n or "ranged_direct" in n:
                return "DIRECT_RANGED"
            if "direct" in n:
                return "DIRECT_RANGED"
            if any(x in n for x in ("attack", "fire", "shoot")):
                return "DIRECT_RANGED"
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

    def unit_analysis(self):
        units = aggregate_units(self.results)
        grouped = {"RL": [], "ENEMY": []}
        for uid, stats in units.items():
            side = "RL" if str(stats.get("side", "")).upper() == "RL" else "ENEMY"
            attacks = int(stats.get("attacks", 0) or 0)
            damage = float(stats.get("damage", 0) or 0.0)
            kills = int(stats.get("kills", 0) or 0)
            grouped[side].append(
                {
                    "unit_id": str(uid),
                    "category": str(stats.get("category") or ""),
                    "classification": str(stats.get("classification") or ""),
                    "attacks": attacks,
                    "damage": damage,
                    "kills": kills,
                    "damage_per_attack": (damage / attacks) if attacks > 0 else 0.0,
                    "kills_per_attack": (float(kills) / attacks) if attacks > 0 else 0.0,
                }
            )
        for side in ("RL", "ENEMY"):
            grouped[side].sort(
                key=lambda x: (float(x.get("damage", 0.0)), int(x.get("kills", 0))),
                reverse=True,
            )

        by_side = {}
        for side in ("RL", "ENEMY"):
            entries = grouped[side]
            total_attacks = sum(int(u.get("attacks", 0)) for u in entries)
            total_damage = sum(float(u.get("damage", 0.0)) for u in entries)
            total_kills = sum(int(u.get("kills", 0)) for u in entries)
            by_side[side] = {
                "unit_count": len(entries),
                "total_attacks": total_attacks,
                "total_damage": total_damage,
                "total_kills": total_kills,
                "damage_per_attack": (total_damage / total_attacks) if total_attacks > 0 else 0.0,
            }

        return {
            "by_side": by_side,
            "by_unit": grouped,
        }

    def strategy_analysis(self):
        l2 = compute_option_performance(self.results) or {}
        l3 = compute_formation_performance(self.results) or {}
        mapping = normalize_strategy_option_map(
            build_strategy_option_map(self.results)
        ) or {}
        objective_transition_matrix = (
            self.mission_metrics().get("objective_transition_matrix", {}) or {}
        )
        return {
            "l2_policy_performance": l2,
            "l3_policy_performance": l3,
            "strategy_to_option_map": mapping,
            "objective_transition_matrix": objective_transition_matrix,
        }

    # -------------------------------------------------
    # PRINT REPORT
    # -------------------------------------------------
    def print_report(self):

        self._section("GLOBAL", color="cyan")
        summary = self.summary()
        score_win_rate = summary.get("win_score_rate", summary.get("win_rate", 0.0))
        true_win_rate = summary.get("true_win_rate", 0.0)
        draw_rate = summary.get("draw_rate", 0.0)
        loss_rate = summary.get("loss_rate", 0.0)
        print(f"episodes: {summary.get('episodes', 0)}")
        print(f"score_win_rate_objective(draw=0.5): {score_win_rate:.3f}")
        print(f"true_win_rate_objective(only_vittoria): {true_win_rate:.3f}")
        print(f"draw_rate: {draw_rate:.3f}")
        print(f"loss_rate: {loss_rate:.3f}")
        print(f"draws: {summary.get('draws', 0)}")
        print(f"losses: {summary.get('losses', 0)}")
        print(f"avg_vp: {summary.get('avg_vp', 0.0):.3f}")
        print(f"avg_steps: {summary.get('avg_steps', 0.0):.1f}")

        self._subsection("WIN RATE BY END REASON", color="blue")
        for reason, rate in summary.get("win_rate_by_end_reason", {}).items():
            count = summary.get("end_reason_counts", {}).get(reason, 0)
            print(f"{reason}: score_win_rate_objective(draw=0.5)={rate:.3f} episodes={count}")

        self._subsection("RL RESULT COUNTS", color="blue")
        for label, count in summary.get("rl_result_counts", {}).items():
            print(f"{label}: {count}")

        # Canonical categorical outcome bucket (avoids duplicate with victory_level_counts).
        self._subsection("TRACKED RESULT COUNTS", color="blue")
        for label, count in summary.get("tracked_result_counts", {}).items():
            print(f"{label}: {count}")

        self._subsection("CAPTURED OBJECTIVES (FINAL)", color="blue")
        for captured, count in summary.get("captured_final_counts", {}).items():
            print(f"captured={captured}: {count}")

        self._section("COMBAT", color="magenta")
        print(self.combat_metrics())

        self._section("ADVANCED", color="magenta")
        for k, v in self.advanced_metrics().items():
            print(f"{k}: {v:.3f}")

        self._section("POLICY ALIGNMENT", color="magenta")
        align = self.policy_alignment()
        print(f"forced_ratio: {align['forced_ratio']:.3f} ({align['forced_steps']}/{align['decisions']})")
        print(
            "composite_usage:"
            f" available_actions={align.get('composite_available_count', 0)}"
            f" selected={align.get('composite_selected_count', 0)}"
            f" available_decisions={align.get('composite_available_decisions', 0)}"
            f" select_rate_when_available={align.get('composite_selection_rate_when_available', 0.0):.3f}"
        )

        self._section("MISSION METRICS", color="yellow")
        mission = self.mission_metrics()
        print(f"vp_contact_rate: {mission['vp_contact_rate']:.3f}")
        cpt = mission.get("capture_pressure_turn")
        print(f"capture_pressure_turn: {cpt:.2f}" if isinstance(cpt, (int, float)) else "capture_pressure_turn: n/a")
        print(f"strategy_stuck_ratio: {mission['strategy_stuck_ratio']:.3f}")
        print(f"unit_concentration_index: {mission['unit_concentration_index']:.3f}")
        vp_entry_opps = mission.get("vp_entry_opportunities", 0)
        vp_entry_taken = mission.get("vp_entries_taken", 0)
        vp_entry_conv = mission.get("vp_entry_conversion_rate")
        vp_entry_miss = mission.get("vp_entry_missed_rate")
        print(f"vp_entry_opportunities: {vp_entry_opps}")
        print(f"vp_entries_taken: {vp_entry_taken}")
        print(
            f"vp_entry_conversion_rate: {vp_entry_conv:.3f}"
            if isinstance(vp_entry_conv, (int, float)) else "vp_entry_conversion_rate: n/a"
        )
        print(
            f"vp_entry_missed_rate: {vp_entry_miss:.3f}"
            if isinstance(vp_entry_miss, (int, float)) else "vp_entry_missed_rate: n/a"
        )
        print(f"invalid_action_rate: {mission.get('invalid_action_rate', 0.0):.3f}")
        print(f"fallback_rate: {mission.get('fallback_rate', 0.0):.3f}")
        print(f"wait_recovery_sb3_backstep_rate: {mission.get('wait_recovery_sb3_backstep_rate', 0.0):.3f}")
        source_mix_counts = mission.get("source_mix_counts", {}) or {}
        source_mix_rates = mission.get("source_mix_rates", {}) or {}
        if source_mix_counts:
            print(
                "source_mix_counts: "
                + ", ".join(
                    f"{k}:{source_mix_counts.get(k, 0)}"
                    for k in ("sb3_kept", "planner_override", "finalizer_override")
                    if k in source_mix_counts
                )
            )
            print(
                "source_mix_rates: "
                + ", ".join(
                    f"{k}:{float(source_mix_rates.get(k, 0.0)):.3f}"
                    for k in ("sb3_kept", "planner_override", "finalizer_override")
                    if k in source_mix_rates
                )
            )
            source_mix_capture_rates = mission.get("source_mix_capture_event_rates", {}) or {}
            if source_mix_capture_rates:
                print(
                    "source_mix_capture_event_rates: "
                    + ", ".join(
                        f"{k}:{float(source_mix_capture_rates.get(k, 0.0)):.3f}"
                        for k in ("sb3_kept", "planner_override", "finalizer_override")
                        if k in source_mix_capture_rates
                    )
                )
            finalizer_reason_counts = mission.get("finalizer_override_reason_counts", {}) or {}
            finalizer_reason_rates = mission.get("finalizer_override_reason_rates", {}) or {}
            if finalizer_reason_counts:
                top_reasons = sorted(
                    finalizer_reason_counts.items(),
                    key=lambda kv: int(kv[1]),
                    reverse=True,
                )[:10]
                pretty_reasons = ", ".join(
                    f"{k}:{int(v)} ({float(finalizer_reason_rates.get(k, 0.0)):.3f})"
                    for k, v in top_reasons
                )
                print(f"finalizer_override_reasons(top): {pretty_reasons}")
        print(f"avg_legal_actions_per_decision: {mission.get('avg_legal_actions_per_decision', 0.0):.3f}")
        print(f"mean_action_catalog_gen_ms: {mission.get('mean_action_catalog_gen_ms', 0.0):.3f}")
        legal_by_side = mission.get("avg_legal_actions_per_decision_by_side", {}) or {}
        if legal_by_side:
            pretty_legal = ", ".join(
                f"{k}:{float(v):.2f}" for k, v in sorted(legal_by_side.items(), key=lambda kv: str(kv[0]))
            )
            print(f"avg_legal_actions_per_decision_by_side: {pretty_legal}")
        gen_ms_by_side = mission.get("mean_action_catalog_gen_ms_by_side", {}) or {}
        if gen_ms_by_side:
            pretty_gen = ", ".join(
                f"{k}:{float(v):.3f}" for k, v in sorted(gen_ms_by_side.items(), key=lambda kv: str(kv[0]))
            )
            print(f"mean_action_catalog_gen_ms_by_side: {pretty_gen}")
        print(f"vp_net_progress: {mission.get('vp_net_progress', 0.0):.3f}")
        print(f"position_reversal_rate: {mission.get('position_reversal_rate', 0.0):.3f}")
        print(f"vp_control_turns_share: {mission.get('vp_control_turns_share', 0.0):.3f}")
        print(f"capture_attempt_success_rate: {mission.get('capture_attempt_success_rate', 0.0):.3f}")
        print(f"capture_attempted: {mission.get('capture_attempted', 0)}")
        print(f"capture_committed: {mission.get('capture_committed', 0)}")
        print(f"capture_cancelled_by_finalizer: {mission.get('capture_cancelled_by_finalizer', 0)}")
        print(
            f"capture_cancelled_by_finalizer_rate: "
            f"{mission.get('capture_cancelled_by_finalizer_rate', 0.0):.3f}"
        )
        cancel_reasons = mission.get("capture_cancelled_by_finalizer_reason_counts", {}) or {}
        if cancel_reasons:
            pretty_cancel = ", ".join(
                f"{k}:{v}" for k, v in sorted(cancel_reasons.items(), key=lambda kv: kv[1], reverse=True)
            )
            print(f"capture_cancelled_by_finalizer_reasons: {pretty_cancel}")
        p50 = mission.get("first_vp_entry_turn_p50")
        p90 = mission.get("first_vp_entry_turn_p90")
        print(f"first_vp_entry_turn_p50: {p50:.2f}" if isinstance(p50, (int, float)) else "first_vp_entry_turn_p50: n/a")
        print(f"first_vp_entry_turn_p90: {p90:.2f}" if isinstance(p90, (int, float)) else "first_vp_entry_turn_p90: n/a")
        print(f"capture_conversion_after_contact: {mission.get('capture_conversion_after_contact', 0.0):.3f}")
        print(f"plan_progress_rate: {mission.get('plan_progress_rate', 0.0):.3f}")
        print(f"coordination_gain: {mission.get('coordination_gain', 0.0):.3f}")
        print(f"capture_intent_persistence: {mission.get('capture_intent_persistence', 0.0):.3f}")
        print(f"attack_opportunity_cost_near_vp: {mission.get('attack_opportunity_cost_near_vp', 0.0):.3f}")
        print(f"vp_control_auc: {mission.get('vp_control_auc', 0.0):.3f}")
        print(f"fallback_to_attack_rate_in_capture: {mission.get('fallback_to_attack_rate_in_capture', 0.0):.3f}")
        reasons = mission.get("capture_fallback_reason_counts", {}) or {}
        if reasons:
            pretty = ", ".join(f"{k}:{v}" for k, v in sorted(reasons.items(), key=lambda kv: kv[1], reverse=True))
            print(f"capture_fallback_reasons: {pretty}")
        block_profile = mission.get("capture_move_block_profile", {}) or {}
        if block_profile:
            pretty_block = ", ".join(f"{k}:{v}" for k, v in sorted(block_profile.items(), key=lambda kv: kv[1], reverse=True))
            print(f"capture_move_block_profile: {pretty_block}")
        print(f"capture_emergency_override_rate: {mission.get('capture_emergency_override_rate', 0.0):.3f}")
        print(f"capture_legal_override_rate: {mission.get('capture_legal_override_rate', 0.0):.3f}")
        print(f"capture_emergency_override_count: {mission.get('capture_emergency_override_count', 0)}")
        print(f"capture_legal_override_count: {mission.get('capture_legal_override_count', 0)}")
        print(f"capture_progress_available_rate: {mission.get('capture_progress_available_rate', 0.0):.3f}")
        print(f"capture_suspected_progress_miss_rate: {mission.get('capture_suspected_progress_miss_rate', 0.0):.3f}")
        print(f"capture_progress_available_count: {mission.get('capture_progress_available_count', 0)}")
        print(f"capture_suspected_progress_miss_count: {mission.get('capture_suspected_progress_miss_count', 0)}")
        print(f"capture_progress_candidate_total: {mission.get('capture_progress_candidate_total', 0)}")
        print(f"capture_equal_candidate_total: {mission.get('capture_equal_candidate_total', 0)}")
        print(f"capture_increase_candidate_total: {mission.get('capture_increase_candidate_total', 0)}")
        print(f"capture_move_candidates_total: {mission.get('capture_move_candidates_total', 0)}")
        print(f"capture_reversal_filtered_total: {mission.get('capture_reversal_filtered_total', 0)}")
        print(f"vp_stepin_legal_count: {mission.get('vp_stepin_legal_count', 0)}")
        print(f"vp_stepin_selected_count: {mission.get('vp_stepin_selected_count', 0)}")
        print(f"vp_stepin_selection_rate: {mission.get('vp_stepin_selection_rate', 0.0):.3f}")
        p50_hold = mission.get("vp_control_after_entry_turns_p50")
        p90_hold = mission.get("vp_control_after_entry_turns_p90")
        print(f"vp_control_after_entry_turns_p50: {p50_hold:.2f}" if isinstance(p50_hold, (int, float)) else "vp_control_after_entry_turns_p50: n/a")
        print(f"vp_control_after_entry_turns_p90: {p90_hold:.2f}" if isinstance(p90_hold, (int, float)) else "vp_control_after_entry_turns_p90: n/a")
        stepin_reasons = mission.get("vp_stepin_block_reason_counts", {}) or {}
        if stepin_reasons:
            pretty_stepin = ", ".join(f"{k}:{v}" for k, v in sorted(stepin_reasons.items(), key=lambda kv: kv[1], reverse=True))
            print(f"vp_stepin_block_reasons: {pretty_stepin}")
        print(f"vp_no_legal_stepin_near_count: {mission.get('vp_no_legal_stepin_near_count', 0)}")
        print(f"vp_opening_attack_candidates_total: {mission.get('vp_opening_attack_candidates_total', 0)}")
        print(f"stepin_legal_mask_count: {mission.get('stepin_legal_mask_count', 0)}")
        print(f"stepin_forced_option_count: {mission.get('stepin_forced_option_count', 0)}")
        selected_move_reasons = mission.get("capture_selected_move_reason_counts", {}) or {}
        if selected_move_reasons:
            pretty_selected = ", ".join(f"{k}:{v}" for k, v in sorted(selected_move_reasons.items(), key=lambda kv: kv[1], reverse=True))
            print(f"capture_selected_move_reasons: {pretty_selected}")
        print(f"attack_fallback_to_move_count: {mission.get('attack_fallback_to_move_count', 0)}")
        attack_fallback_reasons = mission.get("attack_fallback_reason_counts", {}) or {}
        if attack_fallback_reasons:
            pretty_attack_fallback = ", ".join(f"{k}:{v}" for k, v in sorted(attack_fallback_reasons.items(), key=lambda kv: kv[1], reverse=True))
            print(f"attack_fallback_reasons: {pretty_attack_fallback}")
        per_unit_attempts = mission.get("per_unit_vp_entry_attempts", {}) or {}
        per_unit_success = mission.get("per_unit_vp_entry_success", {}) or {}
        if per_unit_attempts:
            merged = []
            for uid, attempts in per_unit_attempts.items():
                succ = int(per_unit_success.get(uid, 0))
                merged.append((uid, int(attempts), succ))
            merged.sort(key=lambda x: x[1], reverse=True)
            pretty_units = ", ".join(f"{uid}:{succ}/{att}" for uid, att, succ in merged[:10])
            print(f"per_unit_vp_entry_success(top): {pretty_units}")
        override_reasons = mission.get("capture_override_reason_counts", {}) or {}
        if override_reasons:
            pretty_override = ", ".join(f"{k}:{v}" for k, v in sorted(override_reasons.items(), key=lambda kv: kv[1], reverse=True))
            print(f"capture_override_reasons: {pretty_override}")
        print(f"l3_capture_forced_rate: {mission.get('l3_capture_forced_rate', 0.0):.3f}")
        print(f"l3_capture_forced_count: {mission.get('l3_capture_forced_count', 0)}")
        l3_force_reasons = mission.get("l3_capture_force_reason_counts", {}) or {}
        if l3_force_reasons:
            pretty_l3 = ", ".join(f"{k}:{v}" for k, v in sorted(l3_force_reasons.items(), key=lambda kv: kv[1], reverse=True))
            print(f"l3_capture_force_reasons: {pretty_l3}")
        print(f"post_open_window_followup_advance_count: {mission.get('post_open_window_followup_advance_count', 0)}")
        print(f"post_open_window_followup_success_count: {mission.get('post_open_window_followup_success_count', 0)}")
        print(f"post_open_window_followup_success_rate: {mission.get('post_open_window_followup_success_rate', 0.0):.3f}")
        print(
            "multi_unit_contribution:"
            f" atk_units_mean={mission.get('multi_unit_contribution', {}).get('attack_units_mean', 0.0):.2f}"
            f" dmg_units_mean={mission.get('multi_unit_contribution', {}).get('damage_units_mean', 0.0):.2f}"
        )
        stability = str(mission.get("stability_status", "unknown")).lower()
        stability_color = "green" if stability == "green" else ("yellow" if stability == "yellow" else "red")
        print(f"stability_status: {self._c(stability, color=stability_color, bold=True)}")
        capture_ready = bool(mission.get("capture_readiness", False))
        readiness_txt = "true" if capture_ready else "false"
        readiness_color = "green" if capture_ready else "red"
        print(f"capture_readiness: {self._c(readiness_txt, color=readiness_color, bold=True)}")
        self._section("PLANNING (P4.1 diagnostics)", color="yellow")
        print(f"intent_commitment_rate: {mission.get('intent_commitment_rate', mission.get('intent_commitment_rate_stub', 0.0)):.3f}")
        print(f"role_diversity_index: {mission.get('role_diversity_index', mission.get('role_diversity_index_stub', 0.0)):.3f}")
        plan_roles = mission.get("plan_role_counts_stub", {}) or {}
        if plan_roles:
            pretty_roles = ", ".join(f"{k}:{v}" for k, v in sorted(plan_roles.items(), key=lambda kv: kv[1], reverse=True))
            print(f"plan_role_counts_stub: {pretty_roles}")
        plan_fallback = mission.get("plan_fallback_reason_counts", {}) or {}
        if plan_fallback:
            pretty_fallback = ", ".join(f"{k}:{v}" for k, v in sorted(plan_fallback.items(), key=lambda kv: kv[1], reverse=True))
            print(f"plan_fallback_reason_counts: {pretty_fallback}")
        role_unknown = mission.get("plan_role_unknown_reason_counts", {}) or {}
        if role_unknown:
            pretty_unknown = ", ".join(f"{k}:{v}" for k, v in sorted(role_unknown.items(), key=lambda kv: kv[1], reverse=True))
            print(f"plan_role_unknown_reason_counts: {pretty_unknown}")
        capture_branches = mission.get("capture_branch_counts", {}) or {}
        if capture_branches:
            pretty_branch = ", ".join(f"{k}:{v}" for k, v in sorted(capture_branches.items(), key=lambda kv: kv[1], reverse=True))
            print(f"capture_branch_counts: {pretty_branch}")
        near_vp_l2 = mission.get("near_vp_l2_transition_counts", {}) or {}
        if near_vp_l2:
            top = sorted(near_vp_l2.items(), key=lambda kv: kv[1], reverse=True)[:8]
            pretty_l2 = ", ".join(f"{k}:{v}" for k, v in top)
            print(f"near_vp_l2_transition_counts(top): {pretty_l2}")
        near_vp_l2_by_l3 = mission.get("near_vp_l2_transition_by_l3_counts", {}) or {}
        if near_vp_l2_by_l3:
            top_l3 = sorted(near_vp_l2_by_l3.items(), key=lambda kv: kv[1], reverse=True)[:8]
            pretty_l3 = ", ".join(f"{k}:{v}" for k, v in top_l3)
            print(f"near_vp_l2_transition_by_l3_counts(top): {pretty_l3}")
        print(f"budget_compliance_rate: {mission.get('budget_compliance_rate', 1.0):.3f}")
        print(f"budget_violation_rate: {mission.get('budget_violation_rate', 0.0):.3f}")
        print(f"budget_violation_count: {mission.get('budget_violation_count', 0)}")
        budget_remaining = mission.get("budget_remaining_by_role", {}) or {}
        if budget_remaining:
            pretty_budget_remaining = ", ".join(
                f"{k}:{v}" for k, v in sorted(budget_remaining.items(), key=lambda kv: str(kv[0]))
            )
            print(f"budget_remaining_by_role: {pretty_budget_remaining}")
        print(f"turn_first_contact: {mission.get('turn_first_contact', None)}")
        print(f"turn_first_progress: {mission.get('turn_first_progress', None)}")
        print(f"turn_first_capture: {mission.get('turn_first_capture', None)}")
        print(f"contact_to_progress_delay: {mission.get('contact_to_progress_delay', None)}")
        print(f"progress_to_capture_delay: {mission.get('progress_to_capture_delay', None)}")
        print(f"latency_invalid_order_count: {mission.get('latency_invalid_order_count', 0)}")
        print(f"latency_missing_progress_count: {mission.get('latency_missing_progress_count', 0)}")
        print(f"latency_missing_capture_count: {mission.get('latency_missing_capture_count', 0)}")
        reward_components = mission.get("reward_component_means", {}) or {}
        if reward_components:
            top_reward_components = sorted(
                reward_components.items(),
                key=lambda kv: abs(float(kv[1])),
                reverse=True,
            )[:10]
            pretty_reward = ", ".join(f"{k}:{float(v):.3f}" for k, v in top_reward_components)
            print(f"reward_component_means(top): {pretty_reward}")
        print(
            "lote_e:"
            f" attack_cost_near_vp={mission.get('lote_e_attack_opportunity_cost_near_vp_norm', 0.0):.3f}"
            f" capture_window_open_rate={mission.get('lote_e_capture_window_open_rate', 0.0):.3f}"
            f" expected_vp_swing={mission.get('lote_e_expected_vp_swing_if_advance', 0.0):.3f}"
            f" expected_trade_attack={mission.get('lote_e_expected_trade_if_attack', 0.0):.3f}"
        )

        # ---------------- L2 ----------------
        self._section("L2 POLICY PERFORMANCE", color="cyan")
        for k, v in sorted(
            compute_option_performance(self.results).items(),
            key=lambda x: x[1]["usage"],
            reverse=True
        ):
            print(f"{k}: usage={v['usage']} dmg/atk={v['damage_per_attack']:.3f}")

        # ---------------- L3 ----------------
        self._section("L3 POLICY PERFORMANCE", color="cyan")
        for k, v in sorted(
            compute_formation_performance(self.results).items(),
            key=lambda x: x[1]["usage"],
            reverse=True
        ):
            print(f"{k}: usage={v['usage']} dmg/atk={v['damage_per_attack']:.3f}")

        # ---------------- mapping ----------------
        self._section("STRATEGY -> OPTION", color="cyan")

        mapping = normalize_strategy_option_map(
            build_strategy_option_map(self.results)
        )

        for strat, opts in mapping.items():
            print(f"\n{strat}:")
            for opt, (count, ratio) in opts.items():
                print(f"  {opt}: {count} ({ratio:.2%})")

        # ---------------- ✅ NUEVO ----------------
        self._section("ACTION EXECUTION (REAL)", color="blue")

        actions = self.action_execution()

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

        # ----------------- DIAGNOSTIC: raw action class names -----------------
        self._section("RAW ACTION_CLASS COUNTS (diagnostic)", color="gray")
        counts = getattr(self, "_action_class_counts", {})
        if not counts:
            print("(no action class data)")
        else:
            for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:40]:
                print(f"  {k}: {v}")

        # ---------------- UNITS ----------------
        self._section("UNIT ANALYSIS (L1)", color="blue")

        units = aggregate_units(self.results)
        print_all_units(units, self.rl_side)