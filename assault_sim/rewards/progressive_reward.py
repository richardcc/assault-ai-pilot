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

        is_attack = bool(info.get("is_attack", False)) or l2 == "ATTACK" or "ATTACK" in action_class.upper()

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
            else:
                reward -= objective_delta * self.cfg.vp_delta_weight
                # For non-tracked sides, also reward proactively capturing objectives,
                # not only passively denying tracked-side captures.
                own_before = _captured_objectives_for_side(state, rl_side_norm)
                own_after = _captured_objectives_for_side(next_state, rl_side_norm)
                own_delta = own_after - own_before
                reward += own_delta * self.cfg.vp_delta_weight

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