from collections import defaultdict
import time
import numpy as np
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction
from assault_model.map.terrain_config import terrain_config
from assault_sim.contracts.training_contracts import EvalResult
from assault_sim.evaluation.metrics_tracker import MetricsTracker
from assault_sim.engine.match_runner import MatchRunner
from assault_sim.evaluation.advanced_metrics import AdvancedMetrics


class Evaluator:

    def __init__(
        self,
        env,
        rl_controller,
        rl_side: str,
        max_steps: int = 300,
    ):
        self.env = env
        self.controller = rl_controller
        self.rl_side = rl_side
        self.max_steps = max_steps

    # -------------------------------------------------
    # RUN SINGLE EPISODE
    # -------------------------------------------------
    def _can_enter_uncaptured_vp_now(self, state, unit) -> bool:
        if state is None or unit is None or getattr(unit, "position", None) is None:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        own_ownership = self._ownership_for_side(state, getattr(unit, "side", None))
        vp_hexes = {vp.hex_coords for vp in points}
        actions = ActionCatalog(state, unit, terrain_config).actions()
        for a in actions:
            if getattr(getattr(a, "action_type", None), "category", None) != ActionCategory.MOVEMENT:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            end = path[-1]
            pos_t = (end.q, end.r)
            if pos_t not in vp_hexes:
                continue
            hs = state.hex_states.get(pos_t)
            if hs is None or hs.ownership != own_ownership:
                return True
        return False

    def _normalize_side_key(self, value) -> str:
        raw = getattr(value, "value", value)
        return str(raw or "").strip().upper()

    def _ownership_for_side(self, state, side):
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        key = self._normalize_side_key(side)
        if not key:
            return None
        direct = side_to_ownership.get(key)
        if direct is not None:
            return direct
        for k, v in side_to_ownership.items():
            if self._normalize_side_key(k) == key:
                return v
        return None

    def _captured_objectives_for_side(self, state, side) -> int:
        if state is None or not side:
            return 0
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return 0
        own_ownership = self._ownership_for_side(state, side)
        if own_ownership is None:
            return 0
        captured = 0
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                captured += 1
        return captured

    def run_episode(self):
        advanced_metrics = AdvancedMetrics()

        sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)

        # -------------------------------------------------
        # POLICY TRACKING
        # -------------------------------------------------
        option_counts = defaultdict(int)
        formation_counts = defaultdict(int)
        strategy_option_map = defaultdict(lambda: defaultdict(int))

        reward_trace = []
        decision_trace_counts = defaultdict(int)
        sampled_option_counts = defaultdict(int)
        resolved_option_counts = defaultdict(int)
        forced_steps = 0
        rl_decisions = 0
        schema_version = None
        vp_contact_steps = 0
        vp_hold_steps = 0
        first_vp_contact_step = None
        vp_entry_opportunities = 0
        vp_entries_taken = 0
        vp_progress_sum = 0.0
        vp_progress_count = 0
        near_vp_attack_events = 0
        near_vp_attack_missed_capture = 0
        reversal_events = 0
        reversal_checks = 0
        pos_prev_by_unit = {}
        pos_prevprev_by_unit = {}
        fallback_to_attack_in_capture = 0
        capture_fallback_reason_counts = defaultdict(int)
        capture_move_block_profile_counts = defaultdict(int)
        capture_emergency_override_count = 0
        capture_legal_override_count = 0
        capture_override_reason_counts = defaultdict(int)
        l3_capture_forced_count = 0
        l3_capture_force_reason_counts = defaultdict(int)
        post_open_window_followup_advance_count = 0
        post_open_window_followup_success_count = 0
        capture_progress_available_count = 0
        capture_suspected_progress_miss_count = 0
        capture_progress_candidate_total = 0
        capture_equal_candidate_total = 0
        capture_increase_candidate_total = 0
        capture_move_candidates_total = 0
        capture_reversal_filtered_total = 0
        capture_selected_move_reason_counts = defaultdict(int)
        attack_fallback_to_move_count = 0
        attack_fallback_reason_counts = defaultdict(int)
        vp_stepin_legal_count = 0
        vp_stepin_selected_count = 0
        vp_stepin_block_reason_counts = defaultdict(int)
        vp_no_legal_stepin_near_count = 0
        stepin_legal_mask_count = 0
        stepin_forced_option_count = 0
        vp_opening_attack_candidates_total = 0
        per_unit_vp_entry_attempts = defaultdict(int)
        per_unit_vp_entry_success = defaultdict(int)
        vp_control_after_entry_turns = []
        _vp_control_streak_after_entry = None
        capture_attempts = 0
        capture_success = 0
        capture_attempted_total = 0
        capture_committed_total = 0
        capture_cancelled_by_finalizer_total = 0
        capture_cancelled_by_finalizer_reason_counts = defaultdict(int)
        vp_control_advantage_steps = 0
        first_vp_entry_step = None
        first_progress_step = None
        latency_invalid_order_count = 0
        latency_missing_progress_count = 0
        latency_missing_capture_count = 0
        contact_events = 0
        contact_to_capture_success = 0
        last_l3_by_unit = {}
        capture_persistence_num = 0
        capture_persistence_den = 0
        near_vp_decisions = 0
        near_vp_attack_decisions = 0
        near_vp_progress_move_decisions = 0
        vp_control_count_sum = 0
        vp_control_count_steps = 0
        composite_available_count = 0
        composite_selected_count = 0
        composite_available_decisions = 0
        plan_stub_decisions = 0
        plan_stub_intent_aligned = 0
        plan_role_counts = defaultdict(int)
        plan_role_unknown_reason_counts = defaultdict(int)
        capture_branch_counts = defaultdict(int)
        near_vp_l2_transition_counts = defaultdict(int)
        near_vp_l2_transition_by_l3_counts = defaultdict(int)
        plan_focus_switch_count = 0
        plan_replan_reason_counts = defaultdict(int)
        plan_last_failure_reason_counts = defaultdict(int)
        plan_fallback_reason_counts = defaultdict(int)
        budget_remaining_by_role_last = {}
        budget_violation_count_last = 0
        budget_violation_total = 0
        budget_decision_count = 0
        plan_stage_counts = defaultdict(int)
        action_finalize_reason_counts = defaultdict(int)
        l3_transition_counts = defaultdict(int)
        lote_e_attack_cost_vals = []
        lote_e_capture_window_vals = []
        lote_e_expected_vp_swing_vals = []
        lote_e_expected_trade_vals = []
        invalid_action_count = 0
        fallback_action_count = 0
        wait_recovery_sb3_backstep_count = 0
        reward_component_sums = defaultdict(float)
        reward_component_counts = defaultdict(int)
        plan_stuck_steps_vals = []
        plan_steps_since_progress_vals = []
        plan_planned_target_set_count = 0
        plan_planned_target_switch_count = 0
        _plan_prev_target_by_unit = {}
        plan_team_turn_progress_vals = []
        plan_team_units_committed_vals = []
        plan_team_focus_vp_set_count = 0
        plan_advanced_enabled_count = 0
        plan_advanced_horizon_vals = []
        source_mix_counts = defaultdict(int)
        source_mix_capture_events = defaultdict(int)
        legal_actions_total_by_side = defaultdict(int)
        legal_actions_decisions_by_side = defaultdict(int)
        legal_actions_gen_time_ms_total_by_side = defaultdict(float)

        # ✅ CRÍTICO → LOG REAL DE EVENTOS
        events_log = []

        obs = self.env.reset()
        sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)
        scenario = getattr(sim, "scenario", None) if sim is not None else None
        tracker = MetricsTracker(self.rl_side, scenario=scenario)
        if sim is not None and getattr(sim, "event_bus", None) is not None:
            sim.event_bus.subscribe(tracker)

        if hasattr(self.controller, "reset"):
            self.controller.reset()

        runner = MatchRunner(self.env, controller=self.controller)

        done = False
        steps = 0

        prev_state = sim.game_state if sim is not None else None
        final_state = prev_state

        # -------------------------------------------------
        # MAIN LOOP
        # -------------------------------------------------
        while not done:

            step = runner.step(self.controller, obs)

            if not step:
                break

            info = step.get("info", {}) or {}
            obs = step.get("obs")
            done = step.get("done", False)
            side = step.get("side")
            action = step.get("action")

            # If env info is sparse/empty, synthesize minimal action telemetry
            # so L1/action-execution metrics are still populated.
            if not info and side is not None and action is not None:
                action_class = action.__class__.__name__
                action_upper = action_class.upper()
                is_attack = any(k in action_upper for k in ("ATTACK", "ASSAULT", "FIRE", "SHOOT"))
                synthetic = {
                    "action_class": action_class,
                    "actor_side": side,
                    "unit_id": getattr(action, "unit_id", None),
                }
                if is_attack:
                    if side == self.rl_side:
                        synthetic["rl_attacks"] = 1
                    else:
                        synthetic["enemy_attacks"] = 1
                info = synthetic

            sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)
            state = sim.game_state if sim is not None else None

            if state is None:
                break

            final_state = state

            reward_trace.append(step.get("reward", 0.0))
            # Side asymmetry diagnostics: measure legal action catalog load by side.
            unit_id_for_diag = info.get("unit_id")
            if side is not None and unit_id_for_diag and prev_state is not None:
                try:
                    actor_before_diag = next(
                        (u for u in getattr(prev_state, "units", []) if u.unit_id == unit_id_for_diag),
                        None,
                    )
                    if actor_before_diag is not None:
                        side_key = str(getattr(side, "value", side) or "").upper() or "UNKNOWN"
                        t0 = time.perf_counter()
                        legal_actions = ActionCatalog(prev_state, actor_before_diag, terrain_config).actions()
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        legal_actions_total_by_side[side_key] += int(len(legal_actions or []))
                        legal_actions_decisions_by_side[side_key] += 1
                        legal_actions_gen_time_ms_total_by_side[side_key] += float(elapsed_ms)
                except Exception:
                    pass

            # -------------------------------------------------
            # ✅ EVENT CAPTURE (FIX REAL ROBUSTO)
            # -------------------------------------------------
            for key in ["attack_events", "events", "combat_events", "attacks"]:

                if key not in info:
                    continue

                for e in info[key]:

                    if not isinstance(e, dict):
                        continue

                    attack_type = (
                        e.get("attack_type")
                        or e.get("type")
                        or e.get("action")
                    )

                    if attack_type is None:
                        continue

                    events_log.append({
                        "type": "attack",
                        "attack_type": str(attack_type),
                        "damage": e.get("damage", 0),
                        "attacker": e.get("attacker"),
                        "target": e.get("target"),
                    })
                
            # end for key in ...

            # -------------------------------------------------
            # FALLBACK: synthesize an event from info fields
            # if no explicit event lists are provided by the env
            # -------------------------------------------------
            action_type = info.get("action_type")
            rl_dmg = info.get("rl_damage", 0)
            enemy_dmg = info.get("enemy_damage", 0)
            rl_atk = info.get("rl_attacks", 0)
            enemy_atk = info.get("enemy_attacks", 0)

            is_attack_action = action_type in ("direct", "indirect", "assault")

            if is_attack_action and (rl_dmg or enemy_dmg or rl_atk or enemy_atk):
                # determine attacker side for this step
                atk_side = side

                atk_damage = 0
                if atk_side == self.rl_side:
                    atk_damage = rl_dmg
                else:
                    atk_damage = enemy_dmg

                # normalize attack type
                atk_type_norm = None
                if action_type == "indirect":
                    atk_type_norm = "INDIRECT"
                elif action_type in ("direct", "assault"):
                    atk_type_norm = "DIRECT"
                else:
                    atk_type_norm = str(action_type).upper() if action_type else "OTHER"

                events_log.append({
                    "type": "attack",
                    "attack_type": atk_type_norm,
                    "damage": atk_damage,
                    "attacker": info.get("unit_id"),
                    "target": info.get("target_id") or info.get("target"),
                })

            # -------------------------------------------------
            # POLICY TRACKING
            # -------------------------------------------------
            if side == self.rl_side:
                unit_id = info.get("unit_id")
                actor_before = None
                actor_after = None
                if unit_id and prev_state is not None:
                    actor_before = next(
                        (u for u in getattr(prev_state, "units", []) if u.unit_id == unit_id),
                        None,
                    )
                if unit_id and state is not None:
                    actor_after = next(
                        (u for u in getattr(state, "units", []) if u.unit_id == unit_id),
                        None,
                    )
                captured_before_cnt = self._captured_objectives_for_side(prev_state, self.rl_side)
                captured_after_cnt = self._captured_objectives_for_side(state, self.rl_side)
                objective_delta_real = captured_after_cnt - captured_before_cnt
                can_enter_vp_now = bool(actor_before is not None and self._can_enter_uncaptured_vp_now(prev_state, actor_before))
                if can_enter_vp_now:
                    vp_entry_opportunities += 1
                    if unit_id:
                        per_unit_vp_entry_attempts[str(unit_id)] += 1
                # Count taken entries from real objective-control delta first.
                if (
                    objective_delta_real > 0
                    or int(info.get("objective_captured_delta", 0)) > 0
                    or bool(info.get("actor_captured_vp_now", False))
                    or (
                        bool(info.get("actor_on_vp_after", False))
                        and not bool(info.get("actor_vp_owned_by_rl_before", False))
                    )
                ):
                    vp_entries_taken += 1
                    if unit_id:
                        per_unit_vp_entry_success[str(unit_id)] += 1
                    if _vp_control_streak_after_entry is not None:
                        vp_control_after_entry_turns.append(int(_vp_control_streak_after_entry))
                    _vp_control_streak_after_entry = 0
                if (
                    first_vp_entry_step is None
                    and (
                        objective_delta_real > 0
                        or (
                            bool(info.get("actor_on_vp_after", False))
                            and not bool(info.get("actor_vp_owned_by_rl_before", False))
                        )
                    )
                ):
                    first_vp_entry_step = steps + 1

                option = getattr(self.controller, "current_option", None)
                if option is not None:
                    option_counts[option.name] += 1

                trace = getattr(self.controller, "last_decision_trace", None)
                if trace is not None:
                    rl_decisions += 1
                    sampled_option_counts[trace.sampled_option] += 1
                    resolved_option_counts[trace.resolved_option] += 1
                    decision_trace_counts[f"{trace.sampled_option}->{trace.executed_option}"] += 1
                    try:
                        near_vp_dist = info.get("objective_dist_before", None)
                        if near_vp_dist is not None and float(near_vp_dist) <= 2.0:
                            action_class = str(info.get("action_class", "") or "UNKNOWN")
                            l3_name = str(info.get("l3_strategy", "") or "UNKNOWN").upper()
                            near_vp_l2_transition_counts[
                                f"{trace.sampled_option}->{trace.resolved_option}->{action_class}"
                            ] += 1
                            near_vp_l2_transition_by_l3_counts[
                                f"{l3_name}:{trace.sampled_option}->{trace.resolved_option}->{action_class}"
                            ] += 1
                    except Exception:
                        pass
                    schema_version = getattr(trace, "schema_version", None)
                    if trace.was_forced:
                        forced_steps += 1

                # Composite action diagnostics: availability vs selection.
                if actor_before is not None and prev_state is not None:
                    try:
                        avail_actions = ActionCatalog(prev_state, actor_before, terrain_config).actions()
                        available_now = sum(
                            1 for a in avail_actions
                            if isinstance(a, (MoveThenFireAction, FireThenMoveAction))
                        )
                        composite_available_count += int(available_now)
                        if available_now > 0:
                            composite_available_decisions += 1
                    except Exception:
                        pass
                if isinstance(action, (MoveThenFireAction, FireThenMoveAction)):
                    composite_selected_count += 1

                strategy = getattr(self.controller, "current_strategy", None)

                if strategy is not None:
                    formation = strategy.name
                    formation_counts[formation] += 1

                    if option is not None:
                        strategy_option_map[formation][option.name] += 1
                plan_role = str(info.get("plan_unit_role", "") or "UNKNOWN").upper()
                plan_role_counts[plan_role] += 1
                role_unknown_reason = str(info.get("plan_role_unknown_reason", "") or "")
                if role_unknown_reason:
                    plan_role_unknown_reason_counts[role_unknown_reason] += 1
                capture_branch = str(info.get("capture_branch", "") or "")
                if capture_branch:
                    capture_branch_counts[capture_branch] += 1
                if bool(info.get("plan_focus_switched", False)):
                    plan_focus_switch_count += 1
                try:
                    stuck_steps_now = int(info.get("plan_stuck_steps", 0) or 0)
                    plan_stuck_steps_vals.append(float(max(0, stuck_steps_now)))
                except Exception:
                    pass
                try:
                    step_id_now = int(info.get("plan_step_id", 0) or 0)
                    last_progress_now = int(info.get("plan_last_progress", 0) or 0)
                    if step_id_now > 0 and last_progress_now > 0:
                        plan_steps_since_progress_vals.append(float(max(0, step_id_now - last_progress_now)))
                except Exception:
                    pass
                planned_target_raw = info.get("plan_planned_target", None)
                planned_target = None
                if isinstance(planned_target_raw, (list, tuple)) and len(planned_target_raw) >= 2:
                    try:
                        planned_target = (int(planned_target_raw[0]), int(planned_target_raw[1]))
                    except Exception:
                        planned_target = None
                if planned_target is not None:
                    plan_planned_target_set_count += 1
                uid_plan = str(info.get("unit_id", "") or "")
                if uid_plan:
                    prev_target = _plan_prev_target_by_unit.get(uid_plan)
                    if planned_target is not None and prev_target is not None and planned_target != prev_target:
                        plan_planned_target_switch_count += 1
                    _plan_prev_target_by_unit[uid_plan] = planned_target
                try:
                    plan_team_turn_progress_vals.append(
                        float(max(0, int(info.get("plan_team_turn_plan_progress", 0) or 0)))
                    )
                except Exception:
                    pass
                try:
                    plan_team_units_committed_vals.append(
                        float(max(0, int(info.get("plan_team_units_committed", 0) or 0)))
                    )
                except Exception:
                    pass
                if str(info.get("plan_team_focus_vp_id", "") or "").strip():
                    plan_team_focus_vp_set_count += 1
                if bool(info.get("plan_advanced_enabled", False)):
                    plan_advanced_enabled_count += 1
                try:
                    plan_advanced_horizon_vals.append(
                        float(max(0, int(info.get("plan_advanced_horizon", 0) or 0)))
                    )
                except Exception:
                    pass
                stage = str(info.get("plan_stage", "") or "UNKNOWN").upper()
                plan_stage_counts[stage] += 1
                replan_reason = str(info.get("plan_replan_reason", "") or "")
                if replan_reason:
                    plan_replan_reason_counts[replan_reason] += 1
                last_failure_reason = str(info.get("plan_last_failure_reason", "") or "")
                if last_failure_reason:
                    plan_last_failure_reason_counts[last_failure_reason] += 1
                fallback_reason = str(info.get("plan_fallback_reason", "") or "")
                if fallback_reason:
                    plan_fallback_reason_counts[fallback_reason] += 1
                reward_components = info.get("reward_components", {}) or {}
                if isinstance(reward_components, dict):
                    for k, v in reward_components.items():
                        try:
                            reward_component_sums[str(k)] += float(v)
                            reward_component_counts[str(k)] += 1
                        except Exception:
                            continue
                plan_budget_state = str(info.get("plan_budget_state", "UNBOUNDED") or "UNBOUNDED").upper()
                if plan_budget_state in {"BUDGETED", "EXHAUSTED"}:
                    budget_decision_count += 1
                remaining_raw = info.get("plan_budget_remaining_by_role", {}) or {}
                if isinstance(remaining_raw, dict):
                    budget_remaining_by_role_last = {
                        str(k): int(v) for k, v in remaining_raw.items() if isinstance(v, (int, float))
                    }
                budget_violation_count_last = int(info.get("plan_budget_violation_count", 0) or 0)
                budget_violation_total += int(info.get("plan_budget_violation_delta", 0) or 0)
                finalize_reason = str(info.get("action_finalized_reason", "") or "")
                if finalize_reason:
                    action_finalize_reason_counts[finalize_reason] += 1
                    if finalize_reason != "ok":
                        fallback_action_count += 1
                    if finalize_reason in {"not_in_catalog", "empty_action_id", "non_displacement"}:
                        invalid_action_count += 1
                    if finalize_reason == "wait_recovery_sb3_backstep":
                        wait_recovery_sb3_backstep_count += 1
                l3_sampled = str(info.get("l3_sampled", "") or "")
                l3_effective = str(info.get("l3_effective", "") or "")
                l3_executed = str(info.get("l3_executed", "") or "")
                if l3_sampled or l3_effective or l3_executed:
                    l3_transition_counts[f"{l3_sampled}->{l3_effective}->{l3_executed}"] += 1
                planner_overrode = bool(info.get("stepin_forced_option", False)) or bool(
                    info.get("l3_capture_forced", False)
                )
                if finalize_reason and finalize_reason != "ok":
                    source_bucket = "finalizer_override"
                elif planner_overrode:
                    source_bucket = "planner_override"
                else:
                    source_bucket = "sb3_kept"
                source_mix_counts[source_bucket] += 1
                if int(objective_delta_real) > 0:
                    source_mix_capture_events[source_bucket] += 1
                try:
                    plan_stub_intent_aligned += int(float(info.get("intent_alignment_stub", 0.0)) >= 1.0)
                except Exception:
                    pass
                plan_stub_decisions += 1
                try:
                    lote_e_attack_cost_vals.append(float(info.get("attack_opportunity_cost_near_vp_norm", 0.0) or 0.0))
                    lote_e_capture_window_vals.append(float(info.get("capture_window_open", 0.0) or 0.0))
                    lote_e_expected_vp_swing_vals.append(float(info.get("expected_vp_swing_if_advance", 0.0) or 0.0))
                    lote_e_expected_trade_vals.append(float(info.get("expected_trade_if_attack", 0.0) or 0.0))
                except Exception:
                    pass
                if str(info.get("l3_strategy", "") or "").upper() == "CAPTURE":
                    capture_attempted_total += 1
                    if finalize_reason == "ok":
                        capture_committed_total += 1
                    else:
                        capture_cancelled_by_finalizer_total += 1
                        cancel_reason = str(finalize_reason or "unknown")
                        if "->" in cancel_reason:
                            cancel_reason = cancel_reason.split("->", 1)[0]
                        capture_cancelled_by_finalizer_reason_counts[cancel_reason] += 1
                    capture_attempts += 1
                    if (
                        objective_delta_real > 0
                        or
                        int(info.get("objective_captured_delta", 0)) > 0
                        or bool(info.get("actor_captured_vp_now", False))
                        or (
                            bool(info.get("actor_on_vp_after", False))
                            and not bool(info.get("actor_vp_owned_by_rl_before", False))
                        )
                    ):
                        capture_success += 1
                    if bool(info.get("capture_fallback_to_attack", False)):
                        fallback_to_attack_in_capture += 1
                        reason = str(info.get("capture_fallback_reason", "") or "unknown")
                        capture_fallback_reason_counts[reason] += 1
                    block_profile = str(info.get("capture_move_block_profile", "") or "unknown")
                    capture_move_block_profile_counts[block_profile] += 1
                    if bool(info.get("capture_emergency_override", False)):
                        capture_emergency_override_count += 1
                    if bool(info.get("capture_legal_override", False)):
                        capture_legal_override_count += 1
                    override_reason = str(info.get("capture_override_reason", "") or "")
                    if override_reason:
                        capture_override_reason_counts[override_reason] += 1
                    if bool(info.get("l3_capture_forced", False)):
                        l3_capture_forced_count += 1
                    l3_force_reason = str(info.get("l3_capture_force_reason", "") or "")
                    if l3_force_reason:
                        l3_capture_force_reason_counts[l3_force_reason] += 1
                    if bool(info.get("post_open_window_followup_advance", False)):
                        post_open_window_followup_advance_count += 1
                    if bool(info.get("post_open_window_followup_success", False)):
                        post_open_window_followup_success_count += 1
                    if bool(info.get("capture_progress_available", False)):
                        capture_progress_available_count += 1
                    if bool(info.get("capture_suspected_progress_miss", False)):
                        capture_suspected_progress_miss_count += 1
                    capture_progress_candidate_total += int(info.get("capture_progress_candidates", 0) or 0)
                    capture_equal_candidate_total += int(info.get("capture_equal_candidates", 0) or 0)
                    capture_increase_candidate_total += int(info.get("capture_increase_candidates", 0) or 0)
                    capture_move_candidates_total += int(info.get("capture_move_candidates_total", 0) or 0)
                    capture_reversal_filtered_total += int(info.get("capture_reversal_filtered", 0) or 0)
                    selected_reason = str(info.get("capture_selected_move_reason", "") or "")
                    if selected_reason:
                        capture_selected_move_reason_counts[selected_reason] += 1
                        if (
                            first_progress_step is None
                            and first_vp_contact_step is not None
                            and selected_reason == "objective_progress_move"
                        ):
                            first_progress_step = steps + 1
                if bool(info.get("attack_fallback_to_move", False)):
                    attack_fallback_to_move_count += 1
                af_reason = str(info.get("attack_fallback_reason", "") or "")
                if af_reason:
                    attack_fallback_reason_counts[af_reason] += 1
                    if bool(info.get("vp_stepin_legal", False)):
                        vp_stepin_legal_count += 1
                    if bool(info.get("vp_stepin_selected", False)):
                        vp_stepin_selected_count += 1
                    stepin_reason = str(info.get("vp_stepin_block_reason", "") or "")
                    if stepin_reason:
                        vp_stepin_block_reason_counts[stepin_reason] += 1
                    if stepin_reason == "no_legal_stepin_near_vp":
                        vp_no_legal_stepin_near_count += 1
                    if bool(info.get("stepin_legal_mask", False)):
                        stepin_legal_mask_count += 1
                    if bool(info.get("stepin_forced_option", False)):
                        stepin_forced_option_count += 1
                    vp_opening_attack_candidates_total += int(info.get("vp_opening_attack_candidates_count", 0) or 0)
                if unit_id:
                    curr_l3 = str(info.get("l3_strategy", "") or "").upper()
                    prev_l3 = last_l3_by_unit.get(unit_id)
                    if prev_l3 == "CAPTURE":
                        capture_persistence_den += 1
                        if curr_l3 == "CAPTURE":
                            capture_persistence_num += 1
                    last_l3_by_unit[unit_id] = curr_l3
                if (
                    bool(info.get("actor_on_vp_after", False))
                    or bool(info.get("actor_captured_vp_now", False))
                    or int(info.get("objective_captured_delta", 0)) > 0
                ):
                    vp_contact_steps += 1
                    if first_vp_contact_step is None:
                        first_vp_contact_step = steps + 1
                if bool(info.get("actor_on_vp_after", False)) and bool(info.get("actor_vp_owned_by_rl_after", False)):
                    vp_hold_steps += 1
                dist_before = info.get("objective_dist_before")
                dist_after = info.get("objective_dist_after")
                if (
                    bool(info.get("actor_on_vp_after", False))
                    or (dist_after is not None and float(dist_after) <= 1.0)
                ):
                    contact_events += 1
                    if (
                        bool(info.get("actor_captured_vp_now", False))
                        or int(info.get("objective_captured_delta", 0)) > 0
                    ):
                        contact_to_capture_success += 1
                if dist_before is not None and dist_after is not None:
                    try:
                        vp_progress_sum += float(dist_before) - float(dist_after)
                        vp_progress_count += 1
                        if (
                            first_progress_step is None
                            and first_vp_contact_step is not None
                            and float(dist_after) < float(dist_before)
                        ):
                            first_progress_step = steps + 1
                    except Exception:
                        pass

                l2_opt = str(info.get("l2_option", "")).upper()
                action_class_u = str(info.get("action_class", "")).upper()
                is_attack = l2_opt == "ATTACK" or "ATTACK" in action_class_u or "ASSAULT" in action_class_u
                if is_attack and dist_before is not None:
                    try:
                        if float(dist_before) <= 2.0:
                            near_vp_attack_events += 1
                            if can_enter_vp_now and not bool(info.get("actor_on_vp_after", False)):
                                near_vp_attack_missed_capture += 1
                    except Exception:
                        pass
                if dist_before is not None and dist_after is not None:
                    try:
                        if float(dist_before) <= 2.0:
                            near_vp_decisions += 1
                            if is_attack:
                                near_vp_attack_decisions += 1
                            if (not is_attack) and (float(dist_after) < float(dist_before)):
                                near_vp_progress_move_decisions += 1
                    except Exception:
                        pass

                if unit_id and actor_after is not None and getattr(actor_after, "position", None) is not None:
                    pos_now = (actor_after.position.q, actor_after.position.r)
                    if unit_id in pos_prev_by_unit and unit_id in pos_prevprev_by_unit:
                        reversal_checks += 1
                        if pos_now == pos_prevprev_by_unit[unit_id] and pos_now != pos_prev_by_unit[unit_id]:
                            reversal_events += 1
                    pos_prevprev_by_unit[unit_id] = pos_prev_by_unit.get(unit_id, pos_now)
                    pos_prev_by_unit[unit_id] = pos_now

                if state is not None:
                    side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
                    points = getattr(getattr(state, "victory", None), "points", []) or []
                    own_ownership = self._ownership_for_side(state, self.rl_side)
                    own = 0
                    other = 0
                    for vp in points:
                        hs = state.hex_states.get(vp.hex_coords)
                        if hs is None:
                            continue
                        if hs.ownership == own_ownership:
                            own += 1
                        elif hs.ownership is not None:
                            other += 1
                    vp_control_count_sum += own
                    vp_control_count_steps += 1
                    if own > other:
                        vp_control_advantage_steps += 1
                    if _vp_control_streak_after_entry is not None:
                        if own > 0:
                            _vp_control_streak_after_entry += 1
                        else:
                            vp_control_after_entry_turns.append(int(_vp_control_streak_after_entry))
                            _vp_control_streak_after_entry = None

            # -------------------------------------------------
            # DISTANCE
            # -------------------------------------------------
            pre_dist = None

            if hasattr(state, "units"):

                rl_units = [u for u in state.units if u.side == self.rl_side and u.alive]
                enemy_units = [u for u in state.units if u.side != self.rl_side and u.alive]

                dists = []

                for u in rl_units:
                    for e in enemy_units:
                        if u.position and e.position:
                            dists.append(safe_hex_distance(u.position, e.position))

                if dists:
                    pre_dist = min(dists)

            # -------------------------------------------------
            # CORE METRICS
            # -------------------------------------------------
            tracker.track_damage(info, state, prev_state)
            tracker.track_state(state)
            tracker.step()

            # -------------------------------------------------
            # ADVANCED METRICS
            # -------------------------------------------------
            advanced_metrics.update(info, pre_dist)

            prev_state = state
            steps += 1

            if steps >= self.max_steps:
                break

        if _vp_control_streak_after_entry is not None:
            vp_control_after_entry_turns.append(int(_vp_control_streak_after_entry))

        # -------------------------------------------------
        # BUILD RESULT
        # -------------------------------------------------
        result = tracker.build_result(final_state)

        result["steps"] = steps
        result["episode_length"] = steps
        result["avg_reward"] = float(np.mean(reward_trace)) if reward_trace else 0.0

        # -------------------------------------------------
        # POLICY TRACKING
        # -------------------------------------------------
        result["option_counts"] = dict(option_counts)
        result["formation_counts"] = dict(formation_counts)

        result["strategy_option_map"] = {
            strat: dict(opts) for strat, opts in strategy_option_map.items()
        }
        result["decision_alignment"] = {
            "trace_schema_version": schema_version if rl_decisions > 0 else None,
            "forced_steps": forced_steps,
            "rl_decisions": rl_decisions,
            "forced_ratio": (forced_steps / max(1, rl_decisions)),
            "sampled_option_counts": dict(sampled_option_counts),
            "resolved_option_counts": dict(resolved_option_counts),
            "sampled_to_executed_counts": dict(decision_trace_counts),
            "composite_available_count": int(composite_available_count),
            "composite_selected_count": int(composite_selected_count),
            "composite_available_decisions": int(composite_available_decisions),
            "composite_selection_rate_when_available": (
                float(composite_selected_count) / max(1, int(composite_available_decisions))
            ),
            "l3_transition_counts": dict(l3_transition_counts),
        }

        # -------------------------------------------------
        # ✅ GUARDAR EVENTOS (CLAVE)
        # -------------------------------------------------
        result["events"] = events_log

        # -------------------------------------------------
        # ADVANCED METRICS
        # -------------------------------------------------
        result["advanced"] = advanced_metrics.to_dict()
        role_total = sum(int(v) for v in plan_role_counts.values())
        role_diversity_index_stub = 0.0
        if role_total > 0:
            hhi = 0.0
            for count in plan_role_counts.values():
                p = float(count) / float(role_total)
                hhi += p * p
            role_diversity_index_stub = max(0.0, 1.0 - hhi)
        total_contacts = vp_contact_steps + vp_hold_steps
        vp_entry_conversion_rate = (
            (vp_entries_taken / vp_entry_opportunities)
            if vp_entry_opportunities > 0 else None
        )
        vp_entry_missed_rate = (
            1.0 - vp_entry_conversion_rate
            if vp_entry_conversion_rate is not None else None
        )
        contact_to_progress_delay = None
        progress_to_capture_delay = None
        if first_vp_contact_step is None:
            latency_missing_progress_count += 1
            latency_missing_capture_count += 1
        else:
            if first_progress_step is None:
                latency_missing_progress_count += 1
            elif first_progress_step < first_vp_contact_step:
                latency_invalid_order_count += 1
            else:
                contact_to_progress_delay = int(first_progress_step - first_vp_contact_step)
            if first_vp_entry_step is None:
                latency_missing_capture_count += 1
            elif first_progress_step is None:
                latency_missing_progress_count += 1
            elif first_vp_entry_step < first_progress_step:
                latency_invalid_order_count += 1
            else:
                progress_to_capture_delay = int(first_vp_entry_step - first_progress_step)
        result["mission"] = {
            "vp_contact_steps": vp_contact_steps,
            "vp_hold_steps": vp_hold_steps,
            "vp_contact_rate": (total_contacts / max(1, rl_decisions)),
            "first_vp_contact_turn": first_vp_contact_step,
            "vp_entry_opportunities": vp_entry_opportunities,
            "vp_entries_taken": vp_entries_taken,
            "vp_entry_conversion_rate": vp_entry_conversion_rate,
            "vp_entry_missed_rate": vp_entry_missed_rate,
            "vp_net_progress": (vp_progress_sum / max(1, vp_progress_count)),
            "position_reversal_rate": (reversal_events / max(1, reversal_checks)),
            "attack_near_vp_instead_of_capture_rate": (
                near_vp_attack_missed_capture / max(1, near_vp_attack_events)
            ),
            "vp_control_turns_share": (vp_control_advantage_steps / max(1, rl_decisions)),
            "capture_attempt_success_rate": (capture_success / max(1, capture_attempts)),
            "capture_attempted": int(capture_attempted_total),
            "capture_committed": int(capture_committed_total),
            "capture_cancelled_by_finalizer": int(capture_cancelled_by_finalizer_total),
            "capture_cancelled_by_finalizer_rate": (
                float(capture_cancelled_by_finalizer_total) / max(1.0, float(capture_attempted_total))
            ),
            "capture_cancelled_by_finalizer_reason_counts": dict(capture_cancelled_by_finalizer_reason_counts),
            "fallback_to_attack_rate_in_capture": (
                fallback_to_attack_in_capture / max(1, capture_attempts)
            ),
            "capture_fallback_reason_counts": dict(capture_fallback_reason_counts),
            "capture_move_block_profile": dict(capture_move_block_profile_counts),
            "capture_emergency_override_count": int(capture_emergency_override_count),
            "capture_legal_override_count": int(capture_legal_override_count),
            "capture_emergency_override_rate": (
                capture_emergency_override_count / max(1, capture_attempts)
            ),
            "capture_legal_override_rate": (
                capture_legal_override_count / max(1, capture_attempts)
            ),
            "capture_override_reason_counts": dict(capture_override_reason_counts),
            "l3_capture_forced_count": int(l3_capture_forced_count),
            "l3_capture_forced_rate": (
                l3_capture_forced_count / max(1, rl_decisions)
            ),
            "l3_capture_force_reason_counts": dict(l3_capture_force_reason_counts),
            "post_open_window_followup_advance_count": int(post_open_window_followup_advance_count),
            "post_open_window_followup_success_count": int(post_open_window_followup_success_count),
            "post_open_window_followup_success_rate": (
                post_open_window_followup_success_count / max(1, post_open_window_followup_advance_count)
            ),
            "capture_progress_available_count": int(capture_progress_available_count),
            "capture_suspected_progress_miss_count": int(capture_suspected_progress_miss_count),
            "capture_progress_candidate_total": int(capture_progress_candidate_total),
            "capture_equal_candidate_total": int(capture_equal_candidate_total),
            "capture_increase_candidate_total": int(capture_increase_candidate_total),
            "capture_move_candidates_total": int(capture_move_candidates_total),
            "capture_reversal_filtered_total": int(capture_reversal_filtered_total),
            "capture_progress_available_rate": (
                capture_progress_available_count / max(1, capture_attempts)
            ),
            "capture_suspected_progress_miss_rate": (
                capture_suspected_progress_miss_count / max(1, capture_attempts)
            ),
            "plan_commit_rate": (
                1.0 - (float(plan_focus_switch_count) / max(1, float(plan_stub_decisions)))
            ),
            "focus_switch_rate": (
                float(plan_focus_switch_count) / max(1, float(plan_stub_decisions))
            ),
            "plan_focus_switch_count": int(plan_focus_switch_count),
            "plan_stuck_steps_mean": (
                float(np.mean(plan_stuck_steps_vals)) if plan_stuck_steps_vals else 0.0
            ),
            "plan_stuck_steps_p90": (
                float(np.percentile(plan_stuck_steps_vals, 90)) if plan_stuck_steps_vals else 0.0
            ),
            "plan_steps_since_progress_mean": (
                float(np.mean(plan_steps_since_progress_vals)) if plan_steps_since_progress_vals else 0.0
            ),
            "plan_steps_since_progress_p90": (
                float(np.percentile(plan_steps_since_progress_vals, 90)) if plan_steps_since_progress_vals else 0.0
            ),
            "plan_planned_target_set_rate": (
                float(plan_planned_target_set_count) / max(1.0, float(plan_stub_decisions))
            ),
            "plan_planned_target_switch_count": int(plan_planned_target_switch_count),
            "plan_team_turn_progress_mean": (
                float(np.mean(plan_team_turn_progress_vals)) if plan_team_turn_progress_vals else 0.0
            ),
            "plan_team_units_committed_mean": (
                float(np.mean(plan_team_units_committed_vals)) if plan_team_units_committed_vals else 0.0
            ),
            "plan_team_focus_vp_set_rate": (
                float(plan_team_focus_vp_set_count) / max(1.0, float(plan_stub_decisions))
            ),
            "plan_advanced_enabled_rate": (
                float(plan_advanced_enabled_count) / max(1.0, float(plan_stub_decisions))
            ),
            "plan_advanced_horizon_mean": (
                float(np.mean(plan_advanced_horizon_vals)) if plan_advanced_horizon_vals else 0.0
            ),
            "plan_stage_counts": dict(plan_stage_counts),
            "plan_replan_reason_counts": dict(plan_replan_reason_counts),
            "plan_last_failure_reason_counts": dict(plan_last_failure_reason_counts),
            "plan_fallback_reason_counts": dict(plan_fallback_reason_counts),
            "plan_role_unknown_reason_counts": dict(plan_role_unknown_reason_counts),
            "capture_branch_counts": dict(capture_branch_counts),
            "near_vp_l2_transition_counts": dict(near_vp_l2_transition_counts),
            "near_vp_l2_transition_by_l3_counts": dict(near_vp_l2_transition_by_l3_counts),
            "budget_remaining_by_role": dict(budget_remaining_by_role_last),
            "budget_violation_count": int(max(budget_violation_count_last, budget_violation_total)),
            "budget_violation_rate": (
                float(budget_violation_total) / max(1.0, float(budget_decision_count))
            ),
            "budget_compliance_rate": (
                1.0 - (float(budget_violation_total) / max(1.0, float(budget_decision_count)))
            ),
            "action_finalize_reason_counts": dict(action_finalize_reason_counts),
            "invalid_action_count": int(invalid_action_count),
            "fallback_action_count": int(fallback_action_count),
            "wait_recovery_sb3_backstep_count": int(wait_recovery_sb3_backstep_count),
            "invalid_action_rate": (
                float(invalid_action_count) / max(1.0, float(rl_decisions))
            ),
            "fallback_rate": (
                float(fallback_action_count) / max(1.0, float(rl_decisions))
            ),
            "wait_recovery_sb3_backstep_rate": (
                float(wait_recovery_sb3_backstep_count) / max(1.0, float(rl_decisions))
            ),
            "source_mix_counts": dict(source_mix_counts),
            "source_mix_rates": {
                k: (float(v) / max(1.0, float(rl_decisions)))
                for k, v in source_mix_counts.items()
            },
            "source_mix_capture_event_counts": dict(source_mix_capture_events),
            "source_mix_capture_event_rates": {
                k: (float(source_mix_capture_events.get(k, 0)) / max(1.0, float(source_mix_counts.get(k, 0))))
                for k in source_mix_counts.keys()
            },
            "reward_component_means": {
                k: (float(reward_component_sums[k]) / max(1, int(reward_component_counts.get(k, 0))))
                for k in reward_component_sums.keys()
            },
            "plan_success_k": (
                float(vp_entries_taken) / max(1.0, float(vp_entry_opportunities))
            ),
            "plan_latency_to_progress": (
                float(first_vp_entry_step) if first_vp_entry_step is not None else None
            ),
            "turn_first_contact": int(first_vp_contact_step) if first_vp_contact_step is not None else None,
            "turn_first_progress": int(first_progress_step) if first_progress_step is not None else None,
            "turn_first_capture": int(first_vp_entry_step) if first_vp_entry_step is not None else None,
            "contact_to_progress_delay": contact_to_progress_delay,
            "progress_to_capture_delay": progress_to_capture_delay,
            "latency_invalid_order_count": int(latency_invalid_order_count),
            "latency_missing_progress_count": int(latency_missing_progress_count),
            "latency_missing_capture_count": int(latency_missing_capture_count),
            "capture_progress_candidate_mean": (
                capture_progress_candidate_total / max(1, capture_attempts)
            ),
            "capture_selected_move_reason_counts": dict(capture_selected_move_reason_counts),
            "attack_fallback_to_move_count": int(attack_fallback_to_move_count),
            "attack_fallback_reason_counts": dict(attack_fallback_reason_counts),
            "vp_stepin_legal_count": int(vp_stepin_legal_count),
            "vp_stepin_selected_count": int(vp_stepin_selected_count),
            "vp_stepin_selection_rate": (
                vp_stepin_selected_count / max(1, vp_stepin_legal_count)
            ),
            "vp_stepin_block_reason_counts": dict(vp_stepin_block_reason_counts),
            "vp_no_legal_stepin_near_count": int(vp_no_legal_stepin_near_count),
            "stepin_legal_mask_count": int(stepin_legal_mask_count),
            "stepin_forced_option_count": int(stepin_forced_option_count),
            "vp_opening_attack_candidates_total": int(vp_opening_attack_candidates_total),
            "vp_control_after_entry_turns": list(vp_control_after_entry_turns),
            "per_unit_vp_entry_attempts": dict(per_unit_vp_entry_attempts),
            "per_unit_vp_entry_success": dict(per_unit_vp_entry_success),
            "first_vp_entry_turn": first_vp_entry_step,
            "contact_events": contact_events,
            "contact_to_capture_success": contact_to_capture_success,
            "capture_conversion_after_contact": (
                contact_to_capture_success / max(1, contact_events)
            ),
            "plan_progress_rate": (
                capture_progress_available_count / max(1, capture_attempts)
            ),
            "coordination_gain": (
                (contact_to_capture_success / max(1, contact_events))
                - (near_vp_attack_decisions / max(1, near_vp_attack_decisions + near_vp_progress_move_decisions))
            ),
            "capture_intent_persistence": (
                capture_persistence_num / max(1, capture_persistence_den)
            ),
            "attack_opportunity_cost_near_vp": (
                near_vp_attack_decisions / max(1, near_vp_attack_decisions + near_vp_progress_move_decisions)
            ),
            "vp_control_auc": (
                vp_control_count_sum / max(1, vp_control_count_steps)
            ),
            "avg_legal_actions_per_decision_by_side": {
                k: (float(legal_actions_total_by_side.get(k, 0)) / max(1.0, float(legal_actions_decisions_by_side.get(k, 0))))
                for k in legal_actions_decisions_by_side.keys()
            },
            "mean_action_catalog_gen_ms_by_side": {
                k: (
                    float(legal_actions_gen_time_ms_total_by_side.get(k, 0.0))
                    / max(1.0, float(legal_actions_decisions_by_side.get(k, 0)))
                )
                for k in legal_actions_decisions_by_side.keys()
            },
            "avg_legal_actions_per_decision": (
                float(sum(legal_actions_total_by_side.values()))
                / max(1.0, float(sum(legal_actions_decisions_by_side.values())))
            ),
            "mean_action_catalog_gen_ms": (
                float(sum(legal_actions_gen_time_ms_total_by_side.values()))
                / max(1.0, float(sum(legal_actions_decisions_by_side.values())))
            ),
            "intent_commitment_rate_stub": (
                plan_stub_intent_aligned / max(1, plan_stub_decisions)
            ),
            "role_diversity_index_stub": role_diversity_index_stub,
            "intent_commitment_rate": (
                plan_stub_intent_aligned / max(1, plan_stub_decisions)
            ),
            "role_diversity_index": role_diversity_index_stub,
            "plan_role_counts_stub": dict(plan_role_counts),
            "lote_e_attack_opportunity_cost_near_vp_norm": (
                float(np.mean(lote_e_attack_cost_vals)) if lote_e_attack_cost_vals else 0.0
            ),
            "lote_e_capture_window_open_rate": (
                float(np.mean(lote_e_capture_window_vals)) if lote_e_capture_window_vals else 0.0
            ),
            "lote_e_expected_vp_swing_if_advance": (
                float(np.mean(lote_e_expected_vp_swing_vals)) if lote_e_expected_vp_swing_vals else 0.0
            ),
            "lote_e_expected_trade_if_attack": (
                float(np.mean(lote_e_expected_trade_vals)) if lote_e_expected_trade_vals else 0.0
            ),
        }

        typed_result = EvalResult.from_dict(result)
        return typed_result.to_dict()

    # -------------------------------------------------
    # MULTI EPISODE
    # -------------------------------------------------
    def evaluate(self, episodes: int):

        results = []

        for ep in range(episodes):

            try:
                result = self.run_episode()
                results.append(result)

            except Exception as e:
                print(f"❌ ERROR in episode {ep}: {e}")

        return results