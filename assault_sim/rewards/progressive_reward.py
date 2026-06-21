import math

from .base_reward import BaseReward
from assault_model.actions.status import WaitAction
from pathlib import Path
from assault_sim.config.reward_config import RewardConfig, load_reward_config


class ProgressiveReward(BaseReward):

    def __init__(self, rl_side=None, config: RewardConfig | None = None, config_path: Path | None = None):
        super().__init__(rl_side)
        self.rl_side = rl_side
        self.last_action = None
        self.cfg = config or load_reward_config(config_path)

        # -------------------------------
        # METRICS (DEBUG / ANALYTICS)
        # -------------------------------
        self.trade_sum = 0.0
        self.trade_count = 0

        self.bad_attacks = 0
        self.total_attacks = 0

        self.damage_given_total = 0
        self.damage_taken_total = 0
        self.vp_hold_streak_by_unit = {}
        self.capture_no_progress_streak_by_unit = {}
        self.attack_count_by_unit = {}
        self.damage_by_unit = {}
        self.strategy_counts = {}
        self.strategy_total = 0
        self.capture_staging_streak_by_unit = {}

    # -------------------------------------------------
    def reset(self, state):
        super().reset(state)
        self.last_action = None
        self.vp_hold_streak_by_unit = {}
        self.capture_no_progress_streak_by_unit = {}
        self.attack_count_by_unit = {}
        self.damage_by_unit = {}
        self.strategy_counts = {}
        self.strategy_total = 0
        self.capture_staging_streak_by_unit = {}

    # -------------------------------------------------
    def compute(
        self,
        *,
        state,
        next_state,
        action,
        active,
        info,
        pre_dist,
        post_dist
    ) -> float:

        info = info or {}
        reward = 0.0

        # -------------------------------
        # CORE DATA
        # -------------------------------
        damage = info.get("rl_damage", 0)
        damage_taken = info.get("enemy_damage", 0)
        killed = info.get("rl_kills", 0) > 0

        action_class = info.get("action_class", "")
        l2 = info.get("l2_option", "")
        l3 = str(info.get("l3_strategy", "") or "").upper()
        if l3:
            self.strategy_total += 1
            self.strategy_counts[l3] = int(self.strategy_counts.get(l3, 0)) + 1

        is_attack = bool(info.get("is_attack", False)) or l2 == "ATTACK" or "ATTACK" in action_class.upper()
        action_class_u = str(action_class).upper()
        is_indirect_attack = "INDIRECT" in action_class_u
        unit_id = info.get("unit_id")
        unit_classification = str(info.get("actor_unit_classification", "") or "").upper()

        # =================================================
        # METRICS TRACKING (no reward impact)
        # =================================================
        self.damage_given_total += damage
        self.damage_taken_total += damage_taken

        trade = damage - damage_taken

        if is_attack:
            self.trade_sum += trade
            self.trade_count += 1

            if damage_taken > damage:
                self.bad_attacks += 1

            self.total_attacks += 1
            if unit_id:
                self.attack_count_by_unit[unit_id] = int(self.attack_count_by_unit.get(unit_id, 0)) + 1
                self.damage_by_unit[unit_id] = float(self.damage_by_unit.get(unit_id, 0.0)) + float(damage)

        # =================================================
        # 🔥 CORE: COMBAT QUALITY (balanced)
        # =================================================
        if is_attack:

            # Main signal (stable scaling)
            reward += trade * self.cfg.trade_weight

            # Penalize bad trades
            if trade < 0:
                reward -= self.cfg.bad_trade_penalty

            # Reward good trades (controlled)
            elif trade > 0:
                reward += self.cfg.good_trade_base_bonus + (trade * self.cfg.good_trade_scale_bonus)

            # Avoid useless attacks
            if damage == 0:
                reward -= self.cfg.zero_damage_attack_penalty

            # 🔥 small base cost to attack (encourage selectivity)
            reward -= self.cfg.attack_base_cost
            if "INDIRECT_FIRE_UNIT" in unit_classification:
                reward += self.cfg.indirect_attack_bonus
                if is_indirect_attack and damage > 0:
                    reward += self.cfg.indirect_effective_hit_bonus

        else:
            # Reward avoiding bad combat
            if trade < 0:
                reward += self.cfg.non_attack_bad_trade_bonus

        # =================================================
        # ✅ KILL
        # =================================================
        if killed:
            reward += self.cfg.kill_bonus

        # =================================================
        # ✅ POSITIONING
        # =================================================
        if pre_dist is not None and post_dist is not None:

            if post_dist < pre_dist:
                reward += self.cfg.move_closer_bonus

            if post_dist <= 2:
                reward += self.cfg.in_range_bonus

        # =================================================
        # ✅ RETREAT (important under disadvantage)
        # =================================================
        if l2 == "RETREAT":

            reward += self.cfg.retreat_bonus

            if damage_taken == 0:
                reward += self.cfg.retreat_no_damage_bonus

        # =================================================
        # ✅ PASSIVITY CONTROL
        # =================================================
        if l2 == "HOLD" and not is_attack:
            reward -= self.cfg.hold_non_attack_penalty

        # =================================================
        # ✅ PRESSURE CONTROL (forces decisions)
        # =================================================
        if (
            pre_dist is not None
            and pre_dist <= self.cfg.pressure_distance_threshold
            and not is_attack
            and l2 != "RETREAT"
        ):
            reward -= self.cfg.pressure_penalty

        # =================================================
        # ✅ ACTION PENALTIES
        # =================================================
        if isinstance(action, WaitAction):
            reward -= self.cfg.wait_penalty

        # =================================================
        # ✅ L3/L2 COHERENCE SHAPING (anti-collapse)
        # =================================================
        if l3 == "ATTRIT":
            if is_attack:
                reward += self.cfg.l3_attrit_attack_bonus
            elif l2 == "ADVANCE":
                reward -= self.cfg.l3_attrit_advance_penalty

        if l3 == "DENY":
            if is_attack:
                reward += self.cfg.l3_deny_attack_bonus
            elif l2 == "ADVANCE":
                close_pressure = pre_dist is not None and float(pre_dist) <= float(self.cfg.pressure_distance_threshold)
                if close_pressure:
                    reward -= self.cfg.l3_deny_advance_penalty

        if self.last_action == action_class:
            reward -= self.cfg.repeat_action_penalty

        self.last_action = action_class

        # =================================================
        # ✅ OBJECTIVES (VP)
        # =================================================
        objective_rule_active = bool(info.get("objective_rule_active", False))
        objective_tracked_side = str(info.get("objective_tracked_side") or "").upper()
        objective_delta = int(info.get("objective_captured_delta", 0))
        rl_side_norm = str(self.rl_side).upper()

        def _captured_objectives_for_side(game_state, side: str) -> int:
            if game_state is None or not side:
                return 0
            points = getattr(getattr(game_state, "victory", None), "points", []) or []
            side_to_ownership = getattr(game_state, "side_to_ownership", {}) or {}
            ownership = side_to_ownership.get(side)
            if ownership is None:
                return 0
            captured = 0
            for vp in points:
                hs = game_state.hex_states.get(vp.hex_coords)
                if hs is not None and hs.ownership == ownership:
                    captured += 1
            return captured

        if objective_rule_active and objective_tracked_side:
            # If RL trains the tracked side, reward captures; otherwise reward denying captures.
            if rl_side_norm == objective_tracked_side:
                reward += objective_delta * self.cfg.vp_delta_weight
                points = getattr(getattr(next_state, "victory", None), "points", []) or []
                total_objectives = len(points)
                captured_after = _captured_objectives_for_side(next_state, objective_tracked_side)
                objectives_pending = total_objectives > 0 and captured_after < total_objectives
                if total_objectives > 0:
                    target_ratio = max(0.0, min(1.0, float(self.cfg.objective_control_target_ratio)))
                    target_min = max(1, int(math.ceil(float(total_objectives) * target_ratio)))
                    shortfall = max(0, target_min - int(captured_after))
                    if shortfall > 0:
                        reward -= shortfall * self.cfg.objective_shortfall_step_penalty
                if l3 == "CAPTURE" and objectives_pending:
                    reward += self.cfg.capture_strategy_bonus
                elif l3 == "PRESERVE" and objectives_pending:
                    reward -= self.cfg.preserve_when_objectives_pending_penalty
                if l3 == "CAPTURE":
                    if l2 == "RETREAT":
                        reward -= self.cfg.capture_retreat_penalty
                    elif l2 in {"ADVANCE", "FLANK"}:
                        reward += self.cfg.capture_advance_bonus
                    # Penalize CAPTURE plans that collapse into attack due to no move progress.
                    if (
                        bool(info.get("capture_fallback_to_attack", False))
                        and str(info.get("capture_fallback_reason", "") or "") == "no_progress_move_available"
                    ):
                        reward -= self.cfg.capture_fallback_attack_penalty
                objective_dist_before = info.get("objective_dist_before")
                objective_dist_after = info.get("objective_dist_after")
                if objective_dist_before is not None and objective_dist_after is not None:
                    try:
                        d_before = float(objective_dist_before)
                        d_after = float(objective_dist_after)
                        if d_after < d_before:
                            reward += (d_before - d_after) * self.cfg.objective_approach_bonus
                            if l3 == "CAPTURE" and unit_id:
                                self.capture_no_progress_streak_by_unit[unit_id] = 0
                        elif d_after > d_before:
                            reward -= (d_after - d_before) * self.cfg.objective_move_away_penalty
                            if l3 == "CAPTURE" and unit_id:
                                streak = int(self.capture_no_progress_streak_by_unit.get(unit_id, 0)) + 1
                                self.capture_no_progress_streak_by_unit[unit_id] = streak
                                reward -= min(4, streak) * self.cfg.capture_no_progress_penalty
                        elif l3 == "CAPTURE" and unit_id:
                            streak = int(self.capture_no_progress_streak_by_unit.get(unit_id, 0)) + 1
                            self.capture_no_progress_streak_by_unit[unit_id] = streak
                            reward -= min(3, streak) * (self.cfg.capture_no_progress_penalty * 0.75)
                    except Exception:
                        pass
                # Staging bonus: reward phased approach when CAPTURE advances unit into
                # short objective distance, even before immediate capture.
                if (
                    l3 == "CAPTURE"
                    and objective_dist_after is not None
                    and float(objective_dist_after) <= 2.0
                    and not bool(info.get("actor_captured_vp_now", False))
                ):
                    reward += self.cfg.capture_staging_bonus
                if l3 == "CAPTURE" and unit_id:
                    move_profile = str(info.get("capture_move_block_profile", "") or "")
                    no_progress = (
                        int(info.get("objective_captured_delta", 0)) <= 0
                        and not bool(info.get("actor_captured_vp_now", False))
                        and objective_dist_before is not None
                        and objective_dist_after is not None
                        and float(objective_dist_after) >= float(objective_dist_before)
                    )
                    if move_profile == "objective_staging_move" and no_progress:
                        s = int(self.capture_staging_streak_by_unit.get(unit_id, 0)) + 1
                        self.capture_staging_streak_by_unit[unit_id] = s
                        reward -= min(5, s) * self.cfg.capture_staging_repeat_penalty
                    else:
                        self.capture_staging_streak_by_unit[unit_id] = 0
                # Mild anti-passivity when CAPTURE keeps moving/holding without
                # damage nor objective progress for consecutive decisions.
                if l3 == "CAPTURE" and unit_id:
                    made_progress = int(info.get("objective_captured_delta", 0)) > 0
                    if objective_dist_before is not None and objective_dist_after is not None:
                        try:
                            made_progress = made_progress or (float(objective_dist_after) < float(objective_dist_before))
                        except Exception:
                            pass
                    dealt_damage = float(damage) > 0.0
                    if (not made_progress) and (not dealt_damage) and (not bool(info.get("actor_captured_vp_now", False))):
                        idle_streak = int(self.capture_no_progress_streak_by_unit.get(unit_id, 0)) + 1
                        self.capture_no_progress_streak_by_unit[unit_id] = idle_streak
                        reward -= min(4, idle_streak) * self.cfg.capture_idle_no_progress_penalty
                    else:
                        self.capture_no_progress_streak_by_unit[unit_id] = 0
                # Late-turn pressure: if tracked side still below campaign target
                # captures in late game, apply growing penalty.
                if (
                    l3 == "CAPTURE"
                    and int(info.get("turn", 0)) >= int(self.cfg.late_capture_turn_threshold)
                ):
                    try:
                        target_min = int(self.cfg.late_capture_target_min)
                        shortfall = max(0, target_min - int(captured_after))
                        if shortfall > 0:
                            reward -= shortfall * self.cfg.late_capture_penalty
                    except Exception:
                        pass
                if (
                    l2 == "HOLD"
                    and not bool(info.get("actor_captured_vp_now", False))
                    and info.get("objective_dist_after") is not None
                    and float(info.get("objective_dist_after")) <= 2.0
                ):
                    reward -= self.cfg.objective_near_hold_penalty
                # Explicit VP-entry shaping to avoid repeated "near but no step-in".
                if bool(info.get("vp_stepin_selected", False)):
                    reward += self.cfg.vp_stepin_selected_bonus
                if str(info.get("vp_stepin_block_reason", "") or "") == "no_legal_stepin_near_vp":
                    reward -= self.cfg.vp_stepin_missed_near_penalty
            else:
                reward -= objective_delta * self.cfg.vp_delta_weight
                # For non-tracked sides, also reward proactively capturing objectives,
                # not only passively denying tracked-side captures.
                own_before = _captured_objectives_for_side(state, rl_side_norm)
                own_after = _captured_objectives_for_side(next_state, rl_side_norm)
                own_delta = own_after - own_before
                reward += own_delta * self.cfg.vp_delta_weight

        # Dense objective shaping: immediate local signal around VP interaction.
        # Helps avoid "good combat but no captures" plateaus.
        if bool(info.get("actor_captured_vp_now", False)):
            reward += self.cfg.vp_delta_weight * 0.5
            if unit_id:
                self.capture_no_progress_streak_by_unit[unit_id] = 0
        elif bool(info.get("actor_vp_owned_by_rl_after", False)) and bool(info.get("actor_on_vp_after", False)):
            reward += self.cfg.vp_delta_weight * self.cfg.capture_vp_presence_bonus
            unit_id = info.get("unit_id")
            if unit_id:
                prev = int(self.vp_hold_streak_by_unit.get(unit_id, 0))
                streak = prev + 1
                self.vp_hold_streak_by_unit[unit_id] = streak
                reward += min(3, streak) * self.cfg.capture_vp_hold_streak_bonus
                reward += self.cfg.vp_control_after_entry_bonus
        elif bool(info.get("actor_vp_owned_by_rl_before", False)) and not bool(info.get("actor_vp_owned_by_rl_after", False)):
            reward -= self.cfg.vp_delta_weight * 0.25
            unit_id = info.get("unit_id")
            if unit_id:
                self.vp_hold_streak_by_unit[unit_id] = 0
        else:
            unit_id = info.get("unit_id")
            if unit_id:
                self.vp_hold_streak_by_unit[unit_id] = 0

        if hasattr(state, "vp_tracker") and state.vp_tracker:
            if hasattr(next_state, "vp_tracker") and next_state.vp_tracker:
                side_to_ownership_prev = getattr(state, "side_to_ownership", {}) or {}
                side_to_ownership_next = getattr(next_state, "side_to_ownership", {}) or {}
                prev_owner_key = side_to_ownership_prev.get(self.rl_side)
                next_owner_key = side_to_ownership_next.get(self.rl_side)
                prev_vp = (
                    state.vp_tracker.score.get(prev_owner_key, 0)
                    if prev_owner_key is not None
                    else 0
                )
                new_vp = (
                    next_state.vp_tracker.score.get(next_owner_key, 0)
                    if next_owner_key is not None
                    else 0
                )

                reward += (new_vp - prev_vp) * self.cfg.vp_delta_weight

        # Reward early entry into VP tiles to break late-entry draw lock.
        if (
            bool(info.get("actor_on_vp_after", False))
            and not bool(info.get("actor_on_vp_before", False))
            and int(info.get("turn", 9999)) <= int(self.cfg.early_vp_entry_turn_bonus_cutoff)
        ):
            reward += self.cfg.early_vp_entry_bonus

        # Penalize collapse to a single L3 strategy for long stretches.
        if self.strategy_total >= int(self.cfg.strategy_dominance_min_decisions):
            dominant = max(self.strategy_counts.values()) if self.strategy_counts else 0
            dominance_share = dominant / max(1, self.strategy_total)
            if dominance_share > float(self.cfg.strategy_dominance_threshold):
                excess = dominance_share - float(self.cfg.strategy_dominance_threshold)
                reward -= excess * self.cfg.strategy_dominance_penalty

        # Anti-concentration: gently reward contributions from units that are
        # currently not dominating total RL damage output.
        if is_attack and damage > 0 and unit_id:
            total_dmg = sum(float(v) for v in self.damage_by_unit.values())
            unit_dmg = float(self.damage_by_unit.get(unit_id, 0.0))
            if total_dmg > 0:
                share = unit_dmg / total_dmg
                if share < 0.55:
                    reward += self.cfg.anti_concentration_bonus * (0.55 - share)
                if share > float(self.cfg.dominant_unit_share_threshold):
                    reward -= (
                        (share - float(self.cfg.dominant_unit_share_threshold))
                        * self.cfg.dominant_unit_share_penalty
                    )

        # =================================================
        # ✅ ENDGAME
        # =================================================
        if getattr(next_state, "done", False):
            winner = getattr(next_state, "winner", None)

            if winner == self.rl_side:
                reward += self.cfg.win_bonus
            elif winner is not None:
                reward -= self.cfg.lose_penalty

            if objective_rule_active and objective_tracked_side:
                # Terminal shaping aligned with objective_outcomes table semantics.
                # Uses tracked-side campaign result text, not only winner side.
                result_kind = str(info.get("objective_result_kind") or "").lower()
                rl_is_tracked = rl_side_norm == objective_tracked_side
                if result_kind == "victory":
                    reward += self.cfg.win_bonus * (0.75 if rl_is_tracked else -0.75)
                elif result_kind == "defeat":
                    reward += self.cfg.lose_penalty * (-0.75 if rl_is_tracked else 0.75)
                    if rl_is_tracked:
                        points = getattr(getattr(next_state, "victory", None), "points", []) or []
                        total_objectives = len(points)
                        if total_objectives > 0:
                            captured_after = _captured_objectives_for_side(next_state, objective_tracked_side)
                            target_ratio = max(0.0, min(1.0, float(self.cfg.objective_control_target_ratio)))
                            target_min = max(1, int(math.ceil(float(total_objectives) * target_ratio)))
                            shortfall = max(0, target_min - int(captured_after))
                            if shortfall > 0:
                                reward -= shortfall * self.cfg.objective_shortfall_terminal_penalty
                elif result_kind == "draw":
                    reward += 0.0
                else:
                    # Keep winner-based shaping as fallback when table label is unknown.
                    if winner is None:
                        reward += 0.0
                    elif str(self.rl_side).upper() == str(winner).upper():
                        reward += self.cfg.win_bonus * 0.5
                    else:
                        reward -= self.cfg.lose_penalty * 0.5

        # =================================================
        # ✅ TIME PENALTY
        # =================================================
        reward -= self.cfg.time_penalty

        return max(min(reward, self.cfg.max_reward), self.cfg.min_reward)