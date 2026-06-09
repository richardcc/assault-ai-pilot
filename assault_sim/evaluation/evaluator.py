from collections import defaultdict
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
        enemy_controller,  # legacy (not used)
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
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        own_ownership = side_to_ownership.get(unit.side)
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
        capture_attempts = 0
        capture_success = 0
        vp_control_advantage_steps = 0
        first_vp_entry_step = None
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
                can_enter_vp_now = bool(actor_before is not None and self._can_enter_uncaptured_vp_now(prev_state, actor_before))
                if can_enter_vp_now:
                    vp_entry_opportunities += 1
                    if (
                        bool(info.get("actor_captured_vp_now", False))
                        or int(info.get("objective_captured_delta", 0)) > 0
                        or (
                            bool(info.get("actor_on_vp_after", False))
                            and not bool(info.get("actor_vp_owned_by_rl_before", False))
                        )
                    ):
                        vp_entries_taken += 1
                if (
                    first_vp_entry_step is None
                    and bool(info.get("actor_on_vp_after", False))
                    and not bool(info.get("actor_vp_owned_by_rl_before", False))
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
                if str(info.get("l3_strategy", "") or "").upper() == "CAPTURE":
                    capture_attempts += 1
                    if (
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
                    own_ownership = side_to_ownership.get(self.rl_side)
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
        }

        # -------------------------------------------------
        # ✅ GUARDAR EVENTOS (CLAVE)
        # -------------------------------------------------
        result["events"] = events_log

        # -------------------------------------------------
        # ADVANCED METRICS
        # -------------------------------------------------
        result["advanced"] = advanced_metrics.to_dict()
        total_contacts = vp_contact_steps + vp_hold_steps
        result["mission"] = {
            "vp_contact_steps": vp_contact_steps,
            "vp_hold_steps": vp_hold_steps,
            "vp_contact_rate": (total_contacts / max(1, rl_decisions)),
            "first_vp_contact_turn": first_vp_contact_step,
            "vp_entry_opportunities": vp_entry_opportunities,
            "vp_entries_taken": vp_entries_taken,
            "vp_entry_missed_rate": (
                (vp_entry_opportunities - vp_entries_taken) / max(1, vp_entry_opportunities)
            ),
            "vp_net_progress": (vp_progress_sum / max(1, vp_progress_count)),
            "position_reversal_rate": (reversal_events / max(1, reversal_checks)),
            "attack_near_vp_instead_of_capture_rate": (
                near_vp_attack_missed_capture / max(1, near_vp_attack_events)
            ),
            "vp_control_turns_share": (vp_control_advantage_steps / max(1, rl_decisions)),
            "capture_attempt_success_rate": (capture_success / max(1, capture_attempts)),
            "fallback_to_attack_rate_in_capture": (
                fallback_to_attack_in_capture / max(1, capture_attempts)
            ),
            "capture_fallback_reason_counts": dict(capture_fallback_reason_counts),
            "capture_move_block_profile": dict(capture_move_block_profile_counts),
            "first_vp_entry_turn": first_vp_entry_step,
            "capture_conversion_after_contact": (
                contact_to_capture_success / max(1, contact_events)
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