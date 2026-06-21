from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack


from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.config.movement_tactical_config import load_movement_tactical_config
from assault_sim.decision.option_executor.combat import OptionExecutorCombatMixin
from assault_sim.decision.option_executor.capture import OptionExecutorCaptureMixin
from assault_sim.decision.option_executor.state import OptionExecutorStateMixin
from assault_model.map.hex_utils import safe_hex_distance
import copy


_MOVE_CFG = load_movement_tactical_config()


class OptionExecutor(OptionExecutorCaptureMixin, OptionExecutorCombatMixin, OptionExecutorStateMixin):
    _ALLOWED_OPTIONS_BY_STRATEGY = {
        StrategicIntent.CAPTURE: {TacticalOption.ADVANCE, TacticalOption.FLANK, TacticalOption.ATTACK},
        StrategicIntent.DENY: {TacticalOption.ADVANCE, TacticalOption.ATTACK, TacticalOption.HOLD},
        StrategicIntent.ATTRIT: {TacticalOption.ATTACK, TacticalOption.FLANK, TacticalOption.ADVANCE},
        StrategicIntent.PRESERVE: {TacticalOption.RETREAT, TacticalOption.HOLD, TacticalOption.ADVANCE},
    }


    def __init__(
        self,
        heuristic_controller,
        avoid_bad_trades: bool = False,
        adv_threshold: float = -0.5,
        capture_guardrails_enabled: bool = True,
        diagnostic_force_capture_only: bool = False,
    ):
        self.heuristic = heuristic_controller
        self._MOVE_CFG = _MOVE_CFG
        # When True, block attacks whose combat advantage is below adv_threshold.
        self.avoid_bad_trades = avoid_bad_trades
        # Minimum combat advantage required to consider an attack.
        self.adv_threshold = adv_threshold
        self.capture_guardrails_enabled = bool(capture_guardrails_enabled)
        self.diagnostic_force_capture_only = bool(diagnostic_force_capture_only)
        # Position history per unit to reduce A->B->A oscillations.
        self._prev_pos_by_unit = {}
        self._prevprev_pos_by_unit = {}
        # Per-unit retreat streak guardrail.
        self._retreat_streak_by_unit = {}
        # Per-unit CAPTURE staging streak (used to break lateral loops).
        self._capture_staging_streak_by_unit = {}
        # Per-unit streak of near-VP states without legal step-in.
        self._capture_no_stepin_near_streak_by_unit = {}
        # Anti-spam throttle for opening-window forced attacks.
        self._capture_open_window_last_seq_by_unit = {}
        # Per-unit follow-up ADVANCE after lane-opening attack.
        self._capture_open_window_pending_followup_by_unit = {}
        # Cooldown when opening attacks are judged low-quality.
        self._capture_open_window_cooldown_until_seq_by_unit = {}
        self._capture_open_window_cooldown_steps = 2
        self._capture_decision_seq = 0
        # Monotonic step id to trace plan evolution.
        self._plan_step_seq = 0
        # P4.3c: lightweight per-turn capture budget (side, turn) -> counters.
        self._capture_budget_by_side_turn = {}
        self._capture_budget_required_advances = 2
        # Per-turn L3 CAPTURE quota by side to prevent strategic collapse.
        self._l3_capture_quota_by_side_turn = {}
        self._l3_capture_quota_required = 1
        # Per-state action catalog cache to avoid repeated legal-path recomputation.
        self._action_catalog_cache_state_key = None
        self._action_catalog_cache = {}
        # Short-lived CAPTURE focus lock to reduce VP target ping-pong.
        self._capture_focus_lock_by_unit = {}
        self._capture_focus_ttl_steps = 3
        # Per-turn cap for non-progress ATTACK fallback reposition (v6):
        # allow only a small number to avoid reopening ATTACK->ADVANCE drift.
        self._attack_reposition_budget_by_side_turn = {}
        self._attack_reposition_budget_per_turn = 1
        self._attack_reposition_budget_near_vp_per_turn = 3

    def _plan_unit_role(self, state, unit, strategy: StrategicIntent | None) -> str:
        if unit is None:
            return "UNKNOWN"
        if state is None:
            if strategy == StrategicIntent.PRESERVE:
                return "RESERVE"
            if strategy == StrategicIntent.DENY:
                return "HOLD_VP"
            return "UNKNOWN"
        local_role = self._local_role_kind(state, unit)
        if local_role == "SUPPORT":
            return "SUPPORT_FIRE"
        if local_role == "ASSAULT":
            return "ASSAULT"
        if strategy == StrategicIntent.PRESERVE:
            return "RESERVE"
        if strategy == StrategicIntent.DENY:
            return "HOLD_VP"
        if strategy == StrategicIntent.CAPTURE:
            return "SCREEN"
        return "UNKNOWN"

    def _tag_action(
        self,
        action,
        option: TacticalOption,
        strategy: StrategicIntent | None,
        planner_context=None,
        state=None,
        unit=None,
        budget_state: str = "UNBOUNDED",
        emergency_override: bool = False,
        legal_override: bool = False,
        override_reason: str = "",
        l3_capture_forced: bool = False,
        l3_capture_force_reason: str = "",
    ):
        if action is None:
            return None
        # Copy only the chosen action to keep ActionCatalog cache objects immutable.
        action = copy.deepcopy(action)
        action.rl_l2_option = option.name
        action.rl_l3_strategy = strategy.name if strategy is not None else None
        if not hasattr(action, "rl_l3_capture_forced"):
            action.rl_l3_capture_forced = False
        if not hasattr(action, "rl_l3_capture_force_reason"):
            action.rl_l3_capture_force_reason = ""
        if not hasattr(action, "rl_capture_fallback_to_attack"):
            action.rl_capture_fallback_to_attack = False
        if not hasattr(action, "rl_capture_fallback_reason"):
            action.rl_capture_fallback_reason = ""
        if not hasattr(action, "rl_capture_move_block_profile"):
            action.rl_capture_move_block_profile = ""
        if not hasattr(action, "rl_capture_target_dist_before"):
            action.rl_capture_target_dist_before = None
        if not hasattr(action, "rl_capture_target_dist_after"):
            action.rl_capture_target_dist_after = None
        if not hasattr(action, "rl_capture_move_candidates_total"):
            action.rl_capture_move_candidates_total = 0
        if not hasattr(action, "rl_capture_progress_candidates"):
            action.rl_capture_progress_candidates = 0
        if not hasattr(action, "rl_capture_equal_candidates"):
            action.rl_capture_equal_candidates = 0
        if not hasattr(action, "rl_capture_increase_candidates"):
            action.rl_capture_increase_candidates = 0
        if not hasattr(action, "rl_capture_reversal_filtered"):
            action.rl_capture_reversal_filtered = 0
        if not hasattr(action, "rl_capture_progress_available"):
            action.rl_capture_progress_available = False
        if not hasattr(action, "rl_capture_selected_move_reason"):
            action.rl_capture_selected_move_reason = ""
        if not hasattr(action, "rl_capture_selected_dist_delta"):
            action.rl_capture_selected_dist_delta = None
        if not hasattr(action, "rl_attack_fallback_to_move"):
            action.rl_attack_fallback_to_move = False
        if not hasattr(action, "rl_attack_fallback_reason"):
            action.rl_attack_fallback_reason = ""
        if not hasattr(action, "rl_capture_suspected_progress_miss"):
            action.rl_capture_suspected_progress_miss = False
        if not hasattr(action, "rl_vp_stepin_legal"):
            action.rl_vp_stepin_legal = False
        if not hasattr(action, "rl_vp_stepin_selected"):
            action.rl_vp_stepin_selected = False
        if not hasattr(action, "rl_vp_stepin_block_reason"):
            action.rl_vp_stepin_block_reason = ""
        if not hasattr(action, "rl_vp_nearest_uncaptured_dist"):
            action.rl_vp_nearest_uncaptured_dist = None
        if not hasattr(action, "rl_vp_opening_attack_candidates_count"):
            action.rl_vp_opening_attack_candidates_count = 0
        if not hasattr(action, "rl_post_open_window_followup_advance"):
            action.rl_post_open_window_followup_advance = False
        if not hasattr(action, "rl_post_open_window_followup_success"):
            action.rl_post_open_window_followup_success = False
        prev_emergency = bool(getattr(action, "rl_capture_emergency_override", False))
        prev_legal = bool(getattr(action, "rl_capture_legal_override", False))
        prev_reason = str(getattr(action, "rl_capture_override_reason", "") or "")
        action.rl_capture_emergency_override = bool(prev_emergency or emergency_override)
        action.rl_capture_legal_override = bool(prev_legal or legal_override)
        if override_reason:
            action.rl_capture_override_reason = str(override_reason)
        else:
            action.rl_capture_override_reason = prev_reason
        action.rl_l3_capture_forced = bool(getattr(action, "rl_l3_capture_forced", False) or l3_capture_forced)
        if l3_capture_force_reason:
            action.rl_l3_capture_force_reason = str(l3_capture_force_reason)
        plan_unit = unit
        if plan_unit is None and getattr(action, "unit_id", None) and state is not None:
            uid = getattr(action, "unit_id", None)
            plan_unit = next((u for u in getattr(state, "units", []) if getattr(u, "unit_id", None) == uid), None)
        planner_intent = str(getattr(planner_context, "intent", "") or "").upper()
        planner_stage = str(getattr(planner_context, "stage", "") or "").upper()
        planner_focus_vp = getattr(planner_context, "focus_vp_id", None)
        planner_replan_reason = str(getattr(planner_context, "replan_reason", "") or "")
        planner_commit_age = int(getattr(planner_context, "commitment_age", 0) or 0)
        planner_focus_switched = bool(getattr(planner_context, "focus_switched", False))
        planner_side = str(getattr(planner_context, "side", "") or "")
        action.rl_plan_intent = planner_intent or self._plan_intent_name(strategy)
        action.rl_plan_unit_role = self._plan_unit_role(state, plan_unit, strategy)
        action.rl_plan_focus_vp_id = planner_focus_vp if planner_focus_vp else self._plan_focus_vp_id(state, plan_unit)
        action.rl_plan_step_id = self._next_plan_step_id()
        action.rl_plan_stage = planner_stage or "EXECUTE"
        action.rl_plan_side = planner_side
        action.rl_plan_replan_reason = planner_replan_reason
        action.rl_plan_commitment_age = planner_commit_age
        action.rl_plan_focus_switched = planner_focus_switched
        action.rl_plan_budget_state = str(budget_state or "UNBOUNDED")
        action.rl_plan_progress_stub = 0.0
        l3 = str(getattr(action, "rl_l3_strategy", "") or "").upper()
        action.rl_plan_intent_alignment_stub = 1.0 if (l3 and action.rl_plan_intent == l3) else 0.0
        # Keep short-lived target commitment during CAPTURE to reduce target ping-pong.
        if strategy == StrategicIntent.CAPTURE and unit is not None:
            focus_hex = self._objective_target_hex(state, unit)
            if focus_hex is not None:
                before = getattr(action, "rl_capture_target_dist_before", None)
                after = getattr(action, "rl_capture_target_dist_after", None)
                made_progress = (
                    isinstance(before, (int, float))
                    and isinstance(after, (int, float))
                    and float(after) < float(before)
                )
                ttl = self._capture_focus_ttl_steps + (1 if made_progress else 0)
                self._set_capture_focus_lock(unit, focus_hex, ttl=ttl)
        uid = getattr(action, "unit_id", None)
        if uid:
            if option == TacticalOption.RETREAT:
                self._retreat_streak_by_unit[uid] = int(self._retreat_streak_by_unit.get(uid, 0)) + 1
            else:
                self._retreat_streak_by_unit[uid] = 0
        return action

    # -------------------------------------------------
    def execute(
        self,
        state,
        unit,
        option: TacticalOption,
        attack_mode: int | None = None,
        strategy: StrategicIntent | None = None,
        objective_tracked_side: str | None = None,
        planner_context=None,
    ):

        if unit is None:
            return WaitAction("SYSTEM")
        self._tick_capture_focus_lock(unit)
        self._update_position_history(unit)
        self._prepare_action_cache(state)
        planner_managed = planner_context is not None
        planner_stage = str(getattr(planner_context, "stage", "") or "").upper()
        if planner_stage == "STEP_IN" and strategy != StrategicIntent.CAPTURE:
            strategy = StrategicIntent.CAPTURE
            if option in (TacticalOption.HOLD, TacticalOption.RETREAT):
                option = TacticalOption.ADVANCE
        elif planner_stage == "HOLD" and strategy == StrategicIntent.CAPTURE and option == TacticalOption.RETREAT:
            option = TacticalOption.HOLD
        tracked_side_norm = self._normalize_side_key(objective_tracked_side)
        unit_side_norm = self._normalize_side_key(getattr(unit, "side", None))
        attacker_context = bool(tracked_side_norm) and unit_side_norm == tracked_side_norm
        defender_context = bool(tracked_side_norm) and unit_side_norm != tracked_side_norm
        objectives_pending = self._has_uncaptured_objective_for_side(state, unit.side)
        capture_emergency = self._is_capture_emergency(state, unit)
        nearest_vp_d_for_force = self._nearest_uncaptured_vp_dist(state, unit)
        near_objective_force_ctx = (
            nearest_vp_d_for_force is not None
            and float(nearest_vp_d_for_force) <= 2.0
        )
        aggressive_l3_forced = False
        l3_capture_forced_reason = ""
        if (
            self.diagnostic_force_capture_only
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
            aggressive_l3_forced = True
            l3_capture_forced_reason = "diagnostic_force_capture_only"
        if (
            objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
            and near_objective_force_ctx
            and strategy == StrategicIntent.PRESERVE
            and strategy != StrategicIntent.CAPTURE
        ):
            strategy = StrategicIntent.CAPTURE
            aggressive_l3_forced = True
            if not l3_capture_forced_reason:
                l3_capture_forced_reason = "aggressive_l3_capture_force"
        turn_now = int(getattr(state, "turn", 0))
        if (
            objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
            and near_objective_force_ctx
        ):
            quota = self._l3_capture_quota_slot(unit.side, turn_now)
            quota["decision_count"] = int(quota.get("decision_count", 0)) + 1
            need_capture = int(quota.get("capture_count", 0)) < int(quota.get("required_capture", 0))
            if need_capture and strategy in (StrategicIntent.PRESERVE, StrategicIntent.CAPTURE):
                strategy = StrategicIntent.CAPTURE
                aggressive_l3_forced = True
                l3_capture_forced_reason = "minimum_capture_intent_quota"
            if strategy == StrategicIntent.CAPTURE:
                quota["capture_count"] = int(quota.get("capture_count", 0)) + 1

        if not self.capture_guardrails_enabled:
            option = self._resolve_option_for_strategy(state, unit, option, strategy)
            option = self._apply_local_role_bias(state, unit, option, strategy)

            def _tag_no_guard(action_to_tag, chosen_option: TacticalOption):
                return self._tag_action(
                    action_to_tag,
                    chosen_option,
                    strategy,
                    planner_context=planner_context,
                    state=state,
                    unit=unit,
                    budget_state="UNBOUNDED",
                    emergency_override=bool(capture_emergency),
                    legal_override=bool(aggressive_l3_forced),
                    override_reason=(l3_capture_forced_reason if aggressive_l3_forced else ""),
                    l3_capture_forced=bool(aggressive_l3_forced),
                    l3_capture_force_reason=(l3_capture_forced_reason if aggressive_l3_forced else ""),
                )

            if option == TacticalOption.ATTACK:
                allow_move_fallback = bool(
                    strategy == StrategicIntent.CAPTURE and self._has_uncaptured_objective(state, unit)
                )
                return _tag_no_guard(
                    self._execute_attack(state, unit, attack_mode, allow_move_fallback=allow_move_fallback),
                    option
                )
            if option == TacticalOption.ADVANCE:
                return _tag_no_guard(self._move_closer(state, unit, capture_strict=False), option)
            if option == TacticalOption.FLANK:
                return _tag_no_guard(self._flank_move(state, unit), option)
            if option == TacticalOption.RETREAT:
                action = self.heuristic.choose_action(state, unit, option)
                if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                    return _tag_no_guard(WaitAction(unit.unit_id), option)
                return _tag_no_guard(action or WaitAction(unit.unit_id), option)
            if option == TacticalOption.HOLD:
                actions = self._get_unit_actions(state, unit)
                attacks = [a for a in actions if self._is_attack_action(a)]
                if attacks:
                    best = self._best_attack(attacks, state=state, unit=unit)
                    return _tag_no_guard(best if best else attacks[0], option)
                return _tag_no_guard(WaitAction(unit.unit_id), option)
            return _tag_no_guard(WaitAction(unit.unit_id), option)

        # Mission guardrail: when objectives are still pending, avoid being stuck
        # in PRESERVE unless this unit is in a genuine emergency.
        if (
            strategy == StrategicIntent.PRESERVE
            and objectives_pending
            and not capture_emergency
            and not planner_managed
            and (not tracked_side_norm or attacker_context)
            and near_objective_force_ctx
        ):
            strategy = StrategicIntent.CAPTURE
        # If we're behind on objectives, force CAPTURE intent (unless emergency).
        if (
            strategy in (StrategicIntent.PRESERVE, StrategicIntent.ATTRIT, StrategicIntent.DENY)
            and objectives_pending
            and self._is_behind_on_objectives(state, unit.side)
            and not capture_emergency
            and not planner_managed
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # If objectives are still pending, avoid over-defensive DENY loops and
        # push capture intent unless this unit is in a genuine emergency.
        if (
            strategy == StrategicIntent.DENY
            and objectives_pending
            and not capture_emergency
            and not planner_managed
            and (not tracked_side_norm or attacker_context)
            and near_objective_force_ctx
            and not self._has_immediate_attack(state, unit)
        ):
            strategy = StrategicIntent.CAPTURE
        # Scenario role guardrail:
        # if this side is the defender (not tracked in objective table),
        # avoid CAPTURE loops and bias to DENY.
        if defender_context and strategy == StrategicIntent.CAPTURE:
            strategy = StrategicIntent.DENY

        # Deterministic CAPTURE controller to avoid reward-driven local loops.
        # Hard gate: in CAPTURE, if a VP entry is immediately available, force it.
        if (
            strategy == StrategicIntent.CAPTURE
            and objectives_pending
            and not capture_emergency
        ):
            step_into_vp = self._best_step_into_uncaptured_vp(state, unit)
            if step_into_vp is not None:
                d_before = self._nearest_uncaptured_vp_dist(state, unit)
                step_into_vp.rl_capture_fallback_reason = "hard_gate_step_into_uncaptured_vp"
                step_into_vp.rl_capture_move_block_profile = "hard_gate_step_into_uncaptured_vp"
                step_into_vp.rl_capture_target_dist_before = d_before
                step_into_vp.rl_capture_target_dist_after = 0
                self._attach_vp_entry_debug(step_into_vp, True, True, "")
                return self._tag_action(
                    step_into_vp,
                    TacticalOption.ADVANCE,
                    strategy,
                    planner_context=planner_context,
                    state=state,
                    unit=unit,
                    legal_override=True,
                    override_reason="hard_gate_step_into_uncaptured_vp",
                    l3_capture_forced=bool(aggressive_l3_forced),
                    l3_capture_force_reason=(l3_capture_forced_reason if aggressive_l3_forced else ""),
                )

        if (
            strategy == StrategicIntent.CAPTURE
            and objectives_pending
        ):
            action, chosen_option = self._capture_priority_action(state, unit, attack_mode)
            return self._tag_action(
                action,
                chosen_option,
                strategy,
                planner_context=planner_context,
                state=state,
                unit=unit,
                l3_capture_forced=bool(aggressive_l3_forced),
                l3_capture_force_reason=(l3_capture_forced_reason if aggressive_l3_forced else ""),
            )

        option = self._resolve_option_for_strategy(state, unit, option, strategy)
        option = self._apply_local_role_bias(state, unit, option, strategy)
        turn_now = int(getattr(state, "turn", 0))
        nearest_vp_d = self._nearest_uncaptured_vp_dist(state, unit)
        budgeted_context = (
            strategy == StrategicIntent.CAPTURE
            and objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
            and nearest_vp_d is not None
            and nearest_vp_d <= 3
        )
        # ATTRIT/DENY anti-collapse: if strategy asks for pressure and a legal
        # attack exists, avoid drifting to ADVANCE by default (outside strict
        # near-objective CAPTURE pressure contexts).
        if (
            strategy in (StrategicIntent.ATTRIT, StrategicIntent.DENY)
            and option == TacticalOption.ADVANCE
            and self._has_immediate_attack(state, unit)
            and not planner_managed
            and not budgeted_context
        ):
            option = TacticalOption.ATTACK

        legal_override_applied = False
        emergency_override_applied = bool(capture_emergency)
        override_reason = ""

        def _tag_with_budget(action_to_tag, chosen_option: TacticalOption):
            budget_state = "UNBOUNDED"
            if budgeted_context:
                slot = self._capture_budget_slot(unit.side, turn_now)
                slot["decision_count"] = int(slot.get("decision_count", 0)) + 1
                if chosen_option == TacticalOption.ADVANCE:
                    slot["advance_count"] = int(slot.get("advance_count", 0)) + 1
                budget_state = self._capture_budget_state_label(unit.side, turn_now, True)
            return self._tag_action(
                action_to_tag,
                chosen_option,
                strategy,
                planner_context=planner_context,
                state=state,
                unit=unit,
                budget_state=budget_state,
                emergency_override=emergency_override_applied,
                legal_override=legal_override_applied,
                override_reason=override_reason,
                l3_capture_forced=bool(aggressive_l3_forced),
                l3_capture_force_reason=(l3_capture_forced_reason if aggressive_l3_forced else ""),
            )

        def _stabilize_non_retreat_move(action_to_tag, chosen_option: TacticalOption):
            if action_to_tag is None:
                return action_to_tag
            if (
                chosen_option not in (TacticalOption.ADVANCE, TacticalOption.FLANK)
                or not objectives_pending
                or capture_emergency
            ):
                return action_to_tag
            path = getattr(action_to_tag, "path", None)
            end = path[-1] if path else None
            reversal = bool(end is not None and self._is_reversal_move(unit, end))
            low_threat = self._enemy_count_within(state, unit, radius=2) == 0
            if reversal and low_threat:
                nonlocal legal_override_applied, override_reason
                legal_override_applied = True
                override_reason = "advance_flank_reversal_blocked_low_threat"
                # Avoid returning WAIT here: in some runtime flows this can stall
                # AI progression. Prefer an alternative non-reversal movement.
                actions = self._get_unit_actions(state, unit)
                unit_pos = getattr(unit, "position", None)
                unit_pos_t = (
                    (getattr(unit_pos, "q", None), getattr(unit_pos, "r", None))
                    if unit_pos is not None
                    else None
                )
                moves = [a for a in actions if getattr(a, "path", None)]
                best_cand = None
                best_cand_dist = None
                for cand in moves:
                    cpath = getattr(cand, "path", None)
                    cend = cpath[-1] if cpath else None
                    if cend is None:
                        continue
                    cend_t = (getattr(cend, "q", None), getattr(cend, "r", None))
                    # Real displacement only; avoid pseudo-moves that keep position.
                    if unit_pos_t is not None and cend_t == unit_pos_t:
                        continue
                    if self._is_reversal_move(unit, cend):
                        continue
                    d_obj = self._nearest_uncaptured_vp_dist_from_pos(
                        state,
                        getattr(unit, "side", None),
                        cend,
                    )
                    d_val = float(d_obj) if d_obj is not None else 999.0
                    if best_cand is None or d_val < float(best_cand_dist):
                        best_cand = cand
                        best_cand_dist = d_val
                if best_cand is not None:
                    return best_cand
                # If no safe alternative exists, keep original action instead of WAIT
                # to preserve turn progression.
                return action_to_tag
            return action_to_tag

        def _replace_non_displacement_move(action_to_tag, chosen_option: TacticalOption):
            if action_to_tag is None:
                return action_to_tag
            if chosen_option not in (TacticalOption.ADVANCE, TacticalOption.FLANK, TacticalOption.RETREAT):
                return action_to_tag
            unit_pos = getattr(unit, "position", None)
            path = getattr(action_to_tag, "path", None)
            end = path[-1] if path else None
            if unit_pos is None or end is None:
                return action_to_tag
            same_hex = (
                getattr(end, "q", None) == getattr(unit_pos, "q", None)
                and getattr(end, "r", None) == getattr(unit_pos, "r", None)
            )
            if not same_hex:
                return action_to_tag

            nonlocal legal_override_applied, override_reason
            legal_override_applied = True
            override_reason = "non_displacement_move_wait_fallback"
            return WaitAction(unit.unit_id)

        if (
            self._has_uncaptured_objective(state, unit)
            and not capture_emergency
        ):
            # Hard priority: if a VP can be occupied now, do it before shooting.
            step_into_vp = self._best_step_into_uncaptured_vp(state, unit)
            if step_into_vp is not None:
                return _tag_with_budget(step_into_vp, TacticalOption.ADVANCE)
        # Hard temporal capture curriculum:
        # while objectives are pending, early episode/turn CAPTURE should advance
        # toward VP unless there is an emergency or a high-value VP attack.
        if (
            strategy == StrategicIntent.CAPTURE
            and self._has_uncaptured_objective(state, unit)
            and not capture_emergency
            and turn_now <= 8
            and not self._has_vp_attack_opportunity(state, unit)
        ):
            if option != TacticalOption.ADVANCE:
                legal_override_applied = True
                override_reason = "capture_early_turn_priority"
            option = TacticalOption.ADVANCE
        # P4.3b soft budget:
        # near VP and with pending objectives, avoid drifting to ATTACK/HOLD unless
        # the attack is directly VP-relevant or there is an emergency.
        if (
            objectives_pending
            and not capture_emergency
            and nearest_vp_d is not None
            and nearest_vp_d <= 3
            and option in (TacticalOption.ATTACK, TacticalOption.HOLD)
            and not self._has_vp_attack_opportunity(state, unit)
        ):
            legal_override_applied = True
            override_reason = "soft_budget_entry_first"
            option = TacticalOption.ADVANCE
        # P4.3c hard budget (light):
        # near VP, demand a minimum number of ADVANCE decisions per side/turn
        # unless there is an emergency or a VP-relevant attack.
        if budgeted_context:
            slot = self._capture_budget_slot(unit.side, turn_now)
            need_advances = int(slot.get("advance_count", 0)) < int(slot.get("required_advances", 0))
            if (
                need_advances
                and option in (TacticalOption.ATTACK, TacticalOption.HOLD, TacticalOption.RETREAT)
                and not self._has_vp_attack_opportunity(state, unit)
            ):
                legal_override_applied = True
                override_reason = "hard_budget_min_advances"
                option = TacticalOption.ADVANCE
        if (
            strategy in (StrategicIntent.CAPTURE, StrategicIntent.DENY)
            and option == TacticalOption.RETREAT
            and self._has_uncaptured_objective(state, unit)
            and not capture_emergency
        ):
            legal_override_applied = True
            override_reason = "retreat_blocked_pending_objectives"
            option = TacticalOption.ADVANCE
        if (
            option == TacticalOption.RETREAT
            and objectives_pending
            and not capture_emergency
            and self._enemy_count_within(state, unit, radius=2) <= 1
        ):
            # v16: avoid passive drift in Human-vs-AI when objectives are still
            # open and local pressure is low (even if opponent is also retreating).
            legal_override_applied = True
            override_reason = "retreat_blocked_low_threat_objective_pressure"
            option = TacticalOption.ADVANCE
        if (
            option == TacticalOption.RETREAT
            and objectives_pending
            and not capture_emergency
            and int(getattr(state, "turn", 0) or 0) <= 3
        ):
            # v18: opening-turn pressure lock. In early turns, do not retreat
            # while objectives remain pending unless there is a real emergency.
            legal_override_applied = True
            override_reason = "retreat_blocked_opening_turn_pressure"
            option = TacticalOption.ADVANCE
        if (
            strategy == StrategicIntent.PRESERVE
            and option in (TacticalOption.RETREAT, TacticalOption.HOLD, TacticalOption.ADVANCE)
            and not capture_emergency
            and self._has_immediate_attack(state, unit)
            and not budgeted_context
        ):
            # Keep PRESERVE, but avoid zero-pressure loops when a legal shot exists.
            option = TacticalOption.ATTACK
        # Hard stop to retreat loops: max 1 consecutive retreat per unit.
        uid = getattr(unit, "unit_id", None)
        if (
            option == TacticalOption.RETREAT
            and uid is not None
            and int(self._retreat_streak_by_unit.get(uid, 0)) >= 1
            and self._has_uncaptured_objective(state, unit)
            and not self._is_capture_emergency(state, unit)
        ):
            legal_override_applied = True
            override_reason = "retreat_streak_blocked"
            option = TacticalOption.ADVANCE

        # -------------------------------------------------
        # ✅ ATTACK
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            if (
                strategy == StrategicIntent.CAPTURE
                and self._has_uncaptured_objective(state, unit)
                and not self._is_capture_emergency(state, unit)
            ):
                # If close to VP and trying to camp-attack, force movement toward capture.
                if nearest_vp_d is not None and nearest_vp_d <= 2:
                    return _tag_with_budget(self._move_closer(state, unit, capture_strict=True), TacticalOption.ADVANCE)
            allow_move_fallback = bool(
                strategy == StrategicIntent.CAPTURE and self._has_uncaptured_objective(state, unit)
            )
            return _tag_with_budget(
                self._execute_attack(state, unit, attack_mode, allow_move_fallback=allow_move_fallback),
                option
            )

        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            advance_action = self._move_closer(state, unit, capture_strict=(strategy == StrategicIntent.CAPTURE))
            advance_action = _stabilize_non_retreat_move(advance_action, TacticalOption.ADVANCE)
            advance_action = _replace_non_displacement_move(advance_action, TacticalOption.ADVANCE)
            return _tag_with_budget(
                advance_action,
                option,
            )

        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            flank_action = self._flank_move(state, unit)
            flank_action = _stabilize_non_retreat_move(flank_action, TacticalOption.FLANK)
            flank_action = _replace_non_displacement_move(flank_action, TacticalOption.FLANK)
            return _tag_with_budget(flank_action, option)

        # -------------------------------------------------
        # ✅ RETREAT (NO ATAQUE)
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:

            action = self.heuristic.choose_action(state, unit, option)

            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                return _tag_with_budget(WaitAction(unit.unit_id), option)

            # Anti-oscillation guardrail for Human-vs-AI feel:
            # block immediate A->B->A retreat reversals when there is no emergency
            # and no close threat pressure. Prefer advancing instead.
            if (
                action is not None
                and objectives_pending
                and not capture_emergency
            ):
                path = getattr(action, "path", None)
                end = path[-1] if path else None
                reversal = bool(end is not None and self._is_reversal_move(unit, end))
                low_threat = self._enemy_count_within(state, unit, radius=2) == 0
                if reversal and low_threat:
                    legal_override_applied = True
                    override_reason = "retreat_reversal_blocked_low_threat"
                    return _tag_with_budget(
                        self._move_closer(
                            state,
                            unit,
                            capture_strict=(strategy == StrategicIntent.CAPTURE),
                        ),
                        TacticalOption.ADVANCE,
                    )

            final_retreat = _replace_non_displacement_move(action or WaitAction(unit.unit_id), TacticalOption.RETREAT)
            return _tag_with_budget(final_retreat, option)

        # -------------------------------------------------
        # ✅ HOLD (MEJORADO CON FALLBACK)
        # -------------------------------------------------
        if option == TacticalOption.HOLD:

            actions = self._get_unit_actions(state, unit)

            attacks = [
                a for a in actions
                if self._is_attack_action(a)
            ]

            if attacks:
                best = self._best_attack(attacks, state=state, unit=unit)
                return _tag_with_budget(best if best else attacks[0], option)
            # If there are relevant objectives to capture, avoid pure passivity.
            if self._objective_target_hex(state, unit) is not None:
                return _tag_with_budget(self._move_closer(state, unit), option)
            return _tag_with_budget(WaitAction(unit.unit_id), option)

        return _tag_with_budget(WaitAction(unit.unit_id), option)

    def _resolve_option_for_strategy(self, state, unit, option: TacticalOption, strategy: StrategicIntent | None):
        if strategy is None:
            return option
        allowed = self._ALLOWED_OPTIONS_BY_STRATEGY.get(strategy)
        if not allowed or option in allowed:
            return option

        # Strategy-constrained fallback option (deterministic).
        if strategy == StrategicIntent.CAPTURE:
            if self._has_uncaptured_objective(state, unit):
                return TacticalOption.ADVANCE
            return TacticalOption.ATTACK
        if strategy == StrategicIntent.DENY:
            return TacticalOption.ATTACK if self._has_uncaptured_objective(state, unit) else TacticalOption.HOLD
        if strategy == StrategicIntent.ATTRIT:
            return TacticalOption.ATTACK
        if strategy == StrategicIntent.PRESERVE:
            # Avoid endless fallback-retreat loops while objectives are pending.
            if self._has_uncaptured_objective(state, unit):
                return TacticalOption.ADVANCE
            return TacticalOption.RETREAT
        return option

    def _local_role_kind(self, state, unit) -> str:
        classification = str(getattr(getattr(unit, "unit_type", None), "classification", "")).upper()
        if "INDIRECT" in classification or "SUPPORT" in classification:
            return "SUPPORT"
        enemies = [u for u in state.units if u.alive and u.side != unit.side and u.position is not None]
        if not enemies or getattr(unit, "position", None) is None:
            return "MANEUVER"
        dmin = min(safe_hex_distance(unit.position, e.position) for e in enemies)
        if dmin <= 2:
            return "ASSAULT"
        return "MANEUVER"

    def _apply_local_role_bias(self, state, unit, option: TacticalOption, strategy: StrategicIntent | None) -> TacticalOption:
        if strategy is None:
            return option
        allowed = self._ALLOWED_OPTIONS_BY_STRATEGY.get(strategy, set())
        role = self._local_role_kind(state, unit)

        preferred = option
        if role == "SUPPORT":
            if strategy in (StrategicIntent.CAPTURE, StrategicIntent.DENY, StrategicIntent.ATTRIT):
                preferred = TacticalOption.ATTACK
            elif strategy == StrategicIntent.PRESERVE:
                preferred = TacticalOption.HOLD
        elif role == "ASSAULT":
            if strategy == StrategicIntent.PRESERVE:
                preferred = TacticalOption.ADVANCE if self._has_uncaptured_objective(state, unit) else TacticalOption.RETREAT
            elif strategy in (StrategicIntent.CAPTURE, StrategicIntent.ATTRIT):
                preferred = TacticalOption.ATTACK
        else:  # MANEUVER
            if strategy == StrategicIntent.CAPTURE:
                preferred = TacticalOption.ADVANCE
            elif strategy == StrategicIntent.ATTRIT:
                # Reduce passive drift under ATTRIT.
                preferred = TacticalOption.ATTACK

        if preferred in allowed:
            return preferred
        return option if option in allowed else self._resolve_option_for_strategy(state, unit, option, strategy)

    def _enemy_count_within(self, state, unit, radius: int = 2) -> int:
        if state is None or unit is None or getattr(unit, "position", None) is None:
            return 0
        cnt = 0
        for e in getattr(state, "units", []):
            if not getattr(e, "alive", False):
                continue
            if getattr(e, "side", None) == getattr(unit, "side", None):
                continue
            if getattr(e, "position", None) is None:
                continue
            if safe_hex_distance(unit.position, e.position) <= int(radius):
                cnt += 1
        return cnt

    def _attack_reposition_slot(self, side, turn: int, near_vp: bool = False):
        side_key = self._normalize_side_key(side)
        key = (side_key, int(turn))
        slot = self._attack_reposition_budget_by_side_turn.get(key)
        desired_limit = int(
            self._attack_reposition_budget_near_vp_per_turn
            if near_vp
            else self._attack_reposition_budget_per_turn
        )
        if slot is None:
            slot = {
                "used": 0,
                "limit": desired_limit,
            }
            self._attack_reposition_budget_by_side_turn[key] = slot
        else:
            # Dynamic budget can only widen in near-VP contexts during the same turn.
            slot["limit"] = max(int(slot.get("limit", 0)), desired_limit)
        return slot

    def _can_consume_attack_reposition_budget(self, side, turn: int, near_vp: bool = False) -> bool:
        slot = self._attack_reposition_slot(side, turn, near_vp=near_vp)
        return int(slot.get("used", 0)) < int(slot.get("limit", 0))

    def _consume_attack_reposition_budget(self, side, turn: int, near_vp: bool = False) -> None:
        slot = self._attack_reposition_slot(side, turn, near_vp=near_vp)
        slot["used"] = int(slot.get("used", 0)) + 1

    pass

