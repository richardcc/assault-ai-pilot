import json
import random
import yaml
import os
from pathlib import Path
import numpy as np
import torch

from assault_model.actions.status import WaitAction
from assault_model.map.hex_utils import safe_hex_distance

from assault_sim.rl.state_encoder import encode_state
from assault_sim.rewards.progressive_reward import ProgressiveReward
from assault_sim.contracts.training_contracts import normalize_plan_state
from assault_sim.decision.role_mapper import resolve_role_with_reason


DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"

_TRAIN_LEAN_INFO_KEYS = {
    "unit_id",
    "actor_side",
    "l2_option",
    "l3_strategy",
    "action_class",
    "action_type",
    "is_wait",
    "turn",
    "rl_damage",
    "enemy_damage",
    "rl_kills",
    "enemy_kills",
    "rl_attacks",
    "enemy_attacks",
    "objective_captured_delta",
    "objective_dist_before",
    "objective_dist_after",
    "actor_on_vp_after",
    "actor_vp_owned_by_rl_before",
    "actor_captured_vp_now",
    "plan_intent",
    "plan_unit_role",
    "plan_role_unknown_reason",
    "capture_branch",
    "plan_focus_vp_id",
    "plan_stage",
    "plan_replan_reason",
    "plan_commitment_age",
    "plan_focus_switched",
    "plan_stuck_steps",
    "plan_last_progress",
    "plan_planned_target",
    "plan_last_failure_reason",
    "plan_team_focus_vp_id",
    "plan_team_turn_plan_progress",
    "plan_team_units_committed",
    "plan_advanced_enabled",
    "plan_advanced_horizon",
    "plan_step_id",
    "plan_budget_state",
    "plan_budget_violation_count",
    "plan_budget_violation_delta",
    "plan_fallback_reason",
    "plan_progress_stub",
    "intent_alignment_stub",
    "action_finalized_reason",
    "l3_sampled",
    "l3_effective",
    "l3_executed",
    "unit_stuck_steps_norm",
    "plan_commitment_age_norm",
    "intent_alignment_last_k",
    "last_failure_reason_onehot",
    "team_turn_plan_progress_norm",
    "team_units_committed_norm",
    "team_focus_vp_set",
    "done",
    # Keep objective outcome essentials for lightweight post-train diagnostics.
    "objective_result_kind",
    "objective_result_text",
}


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return


# -------------------------------------------------
def _min_dist_fast(units_a, units_b):
    best = 999

    for a in units_a:
        for b in units_b:
            d = safe_hex_distance(a.position, b.position)
            if d < best:
                best = d
                if best <= 1:
                    return best
    return best


# -------------------------------------------------
class TrainingEnv:

    def __init__(
        self,
        sim_env,
        env_config_path: Path,
        rl_side: str,
        scenario_override=None,
        reward_fn=None,   # ✅ NUEVO
        seed: int | None = None,
        train_lean: bool = False,
    ):
        self.sim = sim_env
        self.rl_side = rl_side
        self.base_seed = seed
        self.reset_count = 0

        with open(env_config_path, "r", encoding="utf-8") as f:
            if str(env_config_path).lower().endswith(".json"):
                self.env_config = json.load(f)
            else:
                self.env_config = yaml.safe_load(f)

        env_cfg = self.env_config.get("environment", {})
        self.max_steps = env_cfg.get("max_steps", self.env_config.get("max_steps", None))

        self.scenario_override = scenario_override
        self.current_step = 0

        self.reward_fn = reward_fn or ProgressiveReward(rl_side)
        self.train_lean = bool(train_lean)

        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.enemy_attacks = 0
        self.enemy_damage = 0
        self.enemy_kills = 0

        self._vp_hexes = set()
        self._last_action_type = "wait"
        self._unit_stuck_steps = {}
        self._unit_last_focus_vp = {}
        self._unit_plan_commitment_age = {}
        self._unit_intent_alignment_hist = {}
        self._unit_last_failure_reason = {}

    def _lote_d_failure_onehot(self, reason: str):
        r = str(reason or "").lower()
        blocked = 1.0 if ("blocked" in r or "no_move" in r or "no_progress" in r) else 0.0
        high_risk = 1.0 if ("risk" in r) else 0.0
        forced = 1.0 if ("forced" in r or "hard_gate" in r) else 0.0
        no_legal_progress = 1.0 if ("no_legal_progress" in r or "all_moves_increase_distance" in r) else 0.0
        return [blocked, high_risk, forced, no_legal_progress]

    def _update_lote_d_memory(self, info: dict):
        unit_id = str(info.get("unit_id") or "")
        if not unit_id:
            return 0.0, 0.0, 0.0, [0.0, 0.0, 0.0, 0.0]

        progress = float(info.get("plan_progress_stub", 0.0) or 0.0)
        prev_stuck = int(self._unit_stuck_steps.get(unit_id, 0))
        stuck_now = 0 if progress > 0.0 else prev_stuck + 1
        self._unit_stuck_steps[unit_id] = stuck_now
        unit_stuck_steps_norm = float(np.clip(stuck_now / 5.0, 0.0, 1.0))

        focus_now = str(info.get("plan_focus_vp_id") or "")
        focus_prev = str(self._unit_last_focus_vp.get(unit_id, ""))
        if focus_now and focus_now == focus_prev:
            age = int(self._unit_plan_commitment_age.get(unit_id, 0)) + 1
        elif focus_now:
            age = 1
        else:
            age = 0
        self._unit_plan_commitment_age[unit_id] = age
        self._unit_last_focus_vp[unit_id] = focus_now
        plan_commitment_age_norm = float(np.clip(age / 5.0, 0.0, 1.0))

        align = 1.0 if float(info.get("intent_alignment_stub", 0.0) or 0.0) >= 1.0 else 0.0
        hist = list(self._unit_intent_alignment_hist.get(unit_id, []))
        hist.append(align)
        if len(hist) > 4:
            hist = hist[-4:]
        self._unit_intent_alignment_hist[unit_id] = hist
        intent_alignment_last_k = float(sum(hist)) / float(max(1, len(hist)))

        last_reason = str(info.get("capture_fallback_reason", "") or self._unit_last_failure_reason.get(unit_id, ""))
        if str(info.get("capture_fallback_reason", "")).strip():
            self._unit_last_failure_reason[unit_id] = str(info.get("capture_fallback_reason"))
        last_failure_reason_onehot = self._lote_d_failure_onehot(last_reason)
        team_turn_plan_progress_norm = float(
            np.clip(float(info.get("plan_team_turn_plan_progress", 0) or 0) / 3.0, 0.0, 1.0)
        )
        team_units_committed_norm = float(
            np.clip(float(info.get("plan_team_units_committed", 0) or 0) / 6.0, 0.0, 1.0)
        )
        team_focus_vp_set = 1.0 if str(info.get("plan_team_focus_vp_id", "") or "").strip() else 0.0

        return (
            unit_stuck_steps_norm,
            plan_commitment_age_norm,
            intent_alignment_last_k,
            last_failure_reason_onehot,
            team_turn_plan_progress_norm,
            team_units_committed_norm,
            team_focus_vp_set,
        )

    def _objectives_captured_for_side(self, state, side: str) -> int:
        if state is None or not side:
            return 0
        points = getattr(getattr(state, "victory", None), "points", []) or []
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        ownership = side_to_ownership.get(str(side).upper())
        if ownership is None:
            return 0
        captured = 0
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == ownership:
                captured += 1
        return captured

    def _objective_outcome_result(self, state):
        outcomes = getattr(self.sim.scenario, "victory_outcomes", None) or {}
        metric = str(outcomes.get("metric", "")).strip()
        timing = str(outcomes.get("timing", "")).strip()
        tracked_side = str(outcomes.get("tracked_side", "")).strip().upper()
        table = outcomes.get("table", [])
        if metric != "objectives_captured" or timing != "end_of_last_turn" or not tracked_side or not table:
            return None
        captured = self._objectives_captured_for_side(state, tracked_side)
        for row in table:
            if not isinstance(row, dict):
                continue
            cap = row.get("captured", {}) or {}
            try:
                min_cap = int(cap.get("min", -10**9))
                max_cap = int(cap.get("max", 10**9))
            except Exception:
                continue
            if min_cap <= captured <= max_cap:
                return row
        return None

    def _nearest_unsecured_objective_distance(self, state, unit, tracked_side: str):
        if state is None or unit is None or unit.position is None or not tracked_side:
            return None
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        tracked_ownership = side_to_ownership.get(str(tracked_side).upper())
        if tracked_ownership is None:
            return None

        best = None
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            # "Unsecured" for tracked side = VP not currently owned by tracked side.
            if hs is not None and hs.ownership == tracked_ownership:
                continue
            d = safe_hex_distance(unit.position, vp.hex_coords)
            if best is None or d < best:
                best = d
        return best

    # -------------------------------------------------
    @property
    def state(self):
        return self.sim.game_state

    # -------------------------------------------------
    def reset(self):
        if self.base_seed is not None:
            current_seed = int(self.base_seed) + self.reset_count
            random.seed(current_seed)
            np.random.seed(current_seed)
            torch.manual_seed(current_seed)
            self.reset_count += 1

        state = self.sim.reset()

        self.current_step = 0
        self.reward_fn.reset(state)

        self.rl_attacks = 0
        self.rl_damage = 0
        self.rl_kills = 0

        self.enemy_attacks = 0
        self.enemy_damage = 0
        self.enemy_kills = 0

        self._vp_hexes.clear()
        self._last_action_type = "wait"
        self._unit_stuck_steps.clear()
        self._unit_last_focus_vp.clear()
        self._unit_plan_commitment_age.clear()
        self._unit_intent_alignment_hist.clear()
        self._unit_last_failure_reason.clear()

        own_activated_ratio, enemy_activated_ratio = self._activation_ratios(state)

        return encode_state(
            state,
            unit=None,
            rl_side=self.rl_side,
            max_turns=self.sim.scenario.max_turns,
            scenario=self.sim.scenario,
            own_activated_ratio=own_activated_ratio,
            enemy_activated_ratio=enemy_activated_ratio,
            last_action_type=self._last_action_type,
            focus_vp_progress_last_step=0.0,
            focus_vp_id=None,
            role_quota_remaining_norm=1.0,
            unit_stuck_steps_norm=0.0,
            plan_commitment_age_norm=0.0,
            intent_alignment_last_k=0.0,
            last_failure_reason_onehot=[0.0, 0.0, 0.0, 0.0],
        )

    # -------------------------------------------------
    def step(self, action):

        state = self.sim.game_state

        actor = None
        actor_side = None
        rl_side_norm = str(self.rl_side).upper()

        if action is not None and hasattr(action, "unit_id"):
            actor = next(
                (u for u in state.units if u.unit_id == action.unit_id),
                None,
            )
            actor_side = actor.side if actor else None
        actor_side_norm = str(getattr(actor_side, "value", actor_side)).upper() if actor_side is not None else None

        if action is None:
            action = WaitAction("SYSTEM")

        is_wait = isinstance(action, WaitAction)

        # -------------------------------------------------
        # SNAPSHOT BEFORE
        # -------------------------------------------------
        hp_before = {u.unit_id: u.hp for u in state.units}
        alive_before = {u.unit_id: u.alive for u in state.units}
        side_to_ownership_before = getattr(state, "side_to_ownership", {}) or {}
        rl_ownership_before = side_to_ownership_before.get(str(self.rl_side).upper())
        vp_points_before = getattr(getattr(state, "victory", None), "points", []) or []
        vp_hexes_before = {vp.hex_coords for vp in vp_points_before}
        actor_pos_before = None
        actor_on_vp_before = False
        actor_vp_owned_by_rl_before = False
        if actor is not None and actor.position is not None:
            actor_pos_before = (actor.position.q, actor.position.r)
            actor_on_vp_before = actor_pos_before in vp_hexes_before
            if actor_on_vp_before:
                hs_before = state.hex_states.get(actor_pos_before)
                actor_vp_owned_by_rl_before = (
                    hs_before is not None and hs_before.ownership == rl_ownership_before
                )
        objective_cfg = getattr(self.sim.scenario, "victory_outcomes", None) or {}
        tracked_side = str(objective_cfg.get("tracked_side", "")).strip().upper()
        objective_rule_active = (
            str(objective_cfg.get("metric", "")).strip() == "objectives_captured"
            and str(objective_cfg.get("timing", "")).strip() == "end_of_last_turn"
            and bool(objective_cfg.get("table"))
            and bool(tracked_side)
        )
        captured_before = (
            self._objectives_captured_for_side(state, tracked_side)
            if objective_rule_active
            else 0
        )

        # -------------------------------------------------
        # STEP
        # -------------------------------------------------
        next_state, _, sim_done, _ = self.sim.step(action)

        action_name = action.__class__.__name__
        name = action_name.lower()

        # -------------------------------------------------
        # ACTION TYPE
        # -------------------------------------------------
        if is_wait:
            action_type = "wait"
        elif "close" in name:
            action_type = "direct"
        elif "assault" in name:
            action_type = "assault"
        elif "ranged" in name:
            action_type = "indirect"
        elif "move" in name:
            action_type = "move"
        else:
            action_type = "unknown"

        is_attack = action_type in ["direct", "indirect", "assault"]

        if DEBUG_TRACE:
            print(f"⚙️ ACTION: {action_name} -> {action_type}")

        # -------------------------------------------------
        # ✅ INFO (FIX AÑADIDO)
        # -------------------------------------------------
        if self.train_lean:
            info = {
                "unit_id": action.unit_id if hasattr(action, "unit_id") else None,
                "actor_side": actor_side_norm,
                "l2_option": str(getattr(action, "rl_l2_option", "") or ""),
                "l3_strategy": str(getattr(action, "rl_l3_strategy", "") or ""),
                "rl_damage": 0,
                "rl_attacks": 0,
                "rl_kills": 0,
                "enemy_damage": 0,
                "enemy_attacks": 0,
                "enemy_kills": 0,
                "is_wait": is_wait,
                "action_type": action_type,
                "action_class": action.__class__.__name__,
                "turn": next_state.turn,
                "plan_intent": str(getattr(action, "rl_plan_intent", "UNKNOWN") or "UNKNOWN"),
                "plan_unit_role": str(getattr(action, "rl_plan_unit_role", "SCREEN") or "SCREEN"),
                "plan_role_unknown_reason": str(getattr(action, "rl_plan_role_unknown_reason", "") or ""),
                "capture_branch": str(getattr(action, "rl_capture_branch", "") or ""),
                "plan_focus_vp_id": getattr(action, "rl_plan_focus_vp_id", None),
                "plan_stage": str(getattr(action, "rl_plan_stage", "EXECUTE") or "EXECUTE"),
                "plan_replan_reason": str(getattr(action, "rl_plan_replan_reason", "") or ""),
                "plan_commitment_age": int(getattr(action, "rl_plan_commitment_age", 0) or 0),
                "plan_focus_switched": bool(getattr(action, "rl_plan_focus_switched", False)),
                "plan_stuck_steps": int(getattr(action, "rl_plan_stuck_steps", 0) or 0),
                "plan_last_progress": int(getattr(action, "rl_plan_last_progress", 0) or 0),
                "plan_planned_target": getattr(action, "rl_plan_planned_target", None),
                "plan_last_failure_reason": str(getattr(action, "rl_plan_last_failure_reason", "") or ""),
                "plan_team_focus_vp_id": getattr(action, "rl_plan_team_focus_vp_id", None),
                "plan_team_turn_plan_progress": int(getattr(action, "rl_plan_team_turn_plan_progress", 0) or 0),
                "plan_team_units_committed": int(getattr(action, "rl_plan_team_units_committed", 0) or 0),
                "plan_advanced_enabled": bool(getattr(action, "rl_plan_advanced_enabled", False)),
                "plan_advanced_horizon": int(getattr(action, "rl_plan_advanced_horizon", 0) or 0),
                "plan_step_id": int(getattr(action, "rl_plan_step_id", 0) or 0),
                "plan_budget_state": str(getattr(action, "rl_plan_budget_state", "UNBOUNDED") or "UNBOUNDED"),
                "plan_budget_remaining_by_role": dict(getattr(action, "rl_plan_budget_remaining_by_role", {}) or {}),
                "plan_budget_violation_count": int(getattr(action, "rl_plan_budget_violation_count", 0) or 0),
                "plan_budget_violation_delta": int(getattr(action, "rl_plan_budget_violation_delta", 0) or 0),
                "plan_fallback_reason": str(getattr(action, "rl_plan_fallback_reason", "") or ""),
                "plan_progress_stub": float(getattr(action, "rl_plan_progress_stub", 0.0) or 0.0),
                "intent_alignment_stub": float(getattr(action, "rl_plan_intent_alignment_stub", 0.0) or 0.0),
                "action_finalized_reason": str(
                    getattr(action, "rl_training_finalized_reason", "")
                    or getattr(action, "rl_eval_finalized_reason", "")
                    or ""
                ),
            }
        else:
            info = {
                "unit_id": action.unit_id if hasattr(action, "unit_id") else None,
                "action_id": getattr(action, "action_id", None),  # ✅ 💣 NUEVO
                "actor_side": actor_side_norm,
                "l2_option": getattr(action, "rl_l2_option", ""),
                "l3_strategy": getattr(action, "rl_l3_strategy", ""),
                "capture_fallback_to_attack": bool(getattr(action, "rl_capture_fallback_to_attack", False)),
                "capture_fallback_reason": str(getattr(action, "rl_capture_fallback_reason", "") or ""),
                "capture_move_block_profile": str(getattr(action, "rl_capture_move_block_profile", "") or ""),
                "capture_target_dist_before": getattr(action, "rl_capture_target_dist_before", None),
                "capture_target_dist_after": getattr(action, "rl_capture_target_dist_after", None),
                "capture_move_candidates_total": int(getattr(action, "rl_capture_move_candidates_total", 0) or 0),
                "capture_progress_candidates": int(getattr(action, "rl_capture_progress_candidates", 0) or 0),
                "capture_equal_candidates": int(getattr(action, "rl_capture_equal_candidates", 0) or 0),
                "capture_increase_candidates": int(getattr(action, "rl_capture_increase_candidates", 0) or 0),
                "capture_reversal_filtered": int(getattr(action, "rl_capture_reversal_filtered", 0) or 0),
                "capture_progress_available": bool(getattr(action, "rl_capture_progress_available", False)),
                "capture_selected_move_reason": str(getattr(action, "rl_capture_selected_move_reason", "") or ""),
                "capture_selected_dist_delta": getattr(action, "rl_capture_selected_dist_delta", None),
                "capture_suspected_progress_miss": bool(getattr(action, "rl_capture_suspected_progress_miss", False)),
                "attack_fallback_to_move": bool(getattr(action, "rl_attack_fallback_to_move", False)),
                "attack_fallback_reason": str(getattr(action, "rl_attack_fallback_reason", "") or ""),
                "vp_stepin_legal": bool(getattr(action, "rl_vp_stepin_legal", False)),
                "vp_stepin_selected": bool(getattr(action, "rl_vp_stepin_selected", False)),
                "vp_stepin_block_reason": str(getattr(action, "rl_vp_stepin_block_reason", "") or ""),
                "vp_nearest_uncaptured_dist": getattr(action, "rl_vp_nearest_uncaptured_dist", None),
                "vp_opening_attack_candidates_count": int(getattr(action, "rl_vp_opening_attack_candidates_count", 0) or 0),
                "capture_emergency_override": bool(getattr(action, "rl_capture_emergency_override", False)),
                "capture_legal_override": bool(getattr(action, "rl_capture_legal_override", False)),
                "capture_override_reason": str(getattr(action, "rl_capture_override_reason", "") or ""),
                "l3_capture_forced": bool(getattr(action, "rl_l3_capture_forced", False)),
                "l3_capture_force_reason": str(getattr(action, "rl_l3_capture_force_reason", "") or ""),
                "post_open_window_followup_advance": bool(getattr(action, "rl_post_open_window_followup_advance", False)),
                "post_open_window_followup_success": bool(getattr(action, "rl_post_open_window_followup_success", False)),
                "stepin_legal_mask": bool(getattr(action, "rl_stepin_legal_mask", False)),
                "stepin_forced_option": bool(getattr(action, "rl_stepin_forced_option", False)),
                "actor_unit_classification": (
                    str(getattr(getattr(actor, "unit_type", None), "classification", ""))
                    if actor is not None
                    else ""
                ),
                "rl_damage": 0,
                "rl_attacks": 0,
                "rl_kills": 0,
                "enemy_damage": 0,
                "enemy_attacks": 0,
                "enemy_kills": 0,
                "is_wait": is_wait,
                "action_type": action_type,
                "action_class": action.__class__.__name__,
                "turn": next_state.turn,
                "plan_intent": str(getattr(action, "rl_plan_intent", "UNKNOWN") or "UNKNOWN"),
                "plan_unit_role": str(getattr(action, "rl_plan_unit_role", "") or ""),
                "plan_role_unknown_reason": str(getattr(action, "rl_plan_role_unknown_reason", "") or ""),
                "capture_branch": str(getattr(action, "rl_capture_branch", "") or ""),
                "plan_focus_vp_id": getattr(action, "rl_plan_focus_vp_id", None),
                "plan_stage": str(getattr(action, "rl_plan_stage", "EXECUTE") or "EXECUTE"),
                "plan_replan_reason": str(getattr(action, "rl_plan_replan_reason", "") or ""),
                "plan_commitment_age": int(getattr(action, "rl_plan_commitment_age", 0) or 0),
                "plan_focus_switched": bool(getattr(action, "rl_plan_focus_switched", False)),
                "plan_stuck_steps": int(getattr(action, "rl_plan_stuck_steps", 0) or 0),
                "plan_last_progress": int(getattr(action, "rl_plan_last_progress", 0) or 0),
                "plan_planned_target": getattr(action, "rl_plan_planned_target", None),
                "plan_last_failure_reason": str(getattr(action, "rl_plan_last_failure_reason", "") or ""),
                "plan_team_focus_vp_id": getattr(action, "rl_plan_team_focus_vp_id", None),
                "plan_team_turn_plan_progress": int(getattr(action, "rl_plan_team_turn_plan_progress", 0) or 0),
                "plan_team_units_committed": int(getattr(action, "rl_plan_team_units_committed", 0) or 0),
                "plan_advanced_enabled": bool(getattr(action, "rl_plan_advanced_enabled", False)),
                "plan_advanced_horizon": int(getattr(action, "rl_plan_advanced_horizon", 0) or 0),
                "plan_step_id": int(getattr(action, "rl_plan_step_id", 0) or 0),
                "plan_budget_state": str(getattr(action, "rl_plan_budget_state", "UNBOUNDED") or "UNBOUNDED"),
                "plan_budget_remaining_by_role": dict(getattr(action, "rl_plan_budget_remaining_by_role", {}) or {}),
                "plan_budget_violation_count": int(getattr(action, "rl_plan_budget_violation_count", 0) or 0),
                "plan_budget_violation_delta": int(getattr(action, "rl_plan_budget_violation_delta", 0) or 0),
                "plan_fallback_reason": str(getattr(action, "rl_plan_fallback_reason", "") or ""),
                "plan_progress_stub": float(getattr(action, "rl_plan_progress_stub", 0.0) or 0.0),
                "intent_alignment_stub": float(getattr(action, "rl_plan_intent_alignment_stub", 0.0) or 0.0),
                "action_finalized_reason": str(
                    getattr(action, "rl_training_finalized_reason", "")
                    or getattr(action, "rl_eval_finalized_reason", "")
                    or ""
                ),
            }
        if not str(info.get("plan_unit_role") or "").strip():
            inferred_role, _ = resolve_role_with_reason(
                state,
                actor,
                str(info.get("plan_intent", "UNKNOWN") or "UNKNOWN"),
            )
            info["plan_unit_role"] = str(inferred_role or "SCREEN")
        info["l3_sampled"] = str(getattr(action, "rl_l3_strategy", "") or "")
        info["l3_effective"] = str(getattr(action, "rl_l3_strategy", "") or "")
        info["l3_executed"] = str(getattr(action, "rl_l3_strategy", "") or "")

        # -------------------------------------------------
        # ATTACKS
        # -------------------------------------------------
        if is_attack:
            if actor_side_norm == rl_side_norm:
                self.rl_attacks += 1
                info["rl_attacks"] += 1
            else:
                self.enemy_attacks += 1
                info["enemy_attacks"] += 1

        # -------------------------------------------------
        # SNAPSHOT AFTER
        # -------------------------------------------------
        hp_after = {u.unit_id: u.hp for u in next_state.units}
        alive_after = {u.unit_id: u.alive for u in next_state.units}
        side_to_ownership_after = getattr(next_state, "side_to_ownership", {}) or {}
        rl_ownership_after = side_to_ownership_after.get(str(self.rl_side).upper())
        vp_points_after = getattr(getattr(next_state, "victory", None), "points", []) or []
        vp_hexes_after = {vp.hex_coords for vp in vp_points_after}
        actor_after = next(
            (u for u in next_state.units if actor is not None and u.unit_id == actor.unit_id),
            None,
        )
        actor_pos_after = None
        actor_on_vp_after = False
        actor_vp_owned_by_rl_after = False
        if actor_after is not None and actor_after.position is not None:
            actor_pos_after = (actor_after.position.q, actor_after.position.r)
            actor_on_vp_after = actor_pos_after in vp_hexes_after
            if actor_on_vp_after:
                hs_after = next_state.hex_states.get(actor_pos_after)
                actor_vp_owned_by_rl_after = (
                    hs_after is not None and hs_after.ownership == rl_ownership_after
                )
        actor_captured_vp_now = (
            actor_on_vp_after
            and actor_vp_owned_by_rl_after
            and not actor_vp_owned_by_rl_before
        )
        objective_dist_before = (
            self._nearest_unsecured_objective_distance(state, actor, tracked_side)
            if objective_rule_active
            else None
        )
        objective_dist_after = (
            self._nearest_unsecured_objective_distance(next_state, actor_after, tracked_side)
            if objective_rule_active
            else None
        )
        captured_after = (
            self._objectives_captured_for_side(next_state, tracked_side)
            if objective_rule_active
            else 0
        )

        # -------------------------------------------------
        # DAMAGE & KILLS
        # -------------------------------------------------
        for uid, before_hp in hp_before.items():
            after_hp = hp_after.get(uid, before_hp)
            damage = max(0, before_hp - after_hp)

            if damage == 0:
                continue

            if is_attack:
                if actor_side == self.rl_side:
                    self.rl_damage += damage
                    info["rl_damage"] += damage
                else:
                    self.enemy_damage += damage
                    info["enemy_damage"] += damage

            if alive_before[uid] and not alive_after.get(uid, True):
                if is_attack:
                    if actor_side == self.rl_side:
                        self.rl_kills += 1
                        info["rl_kills"] += 1
                    else:
                        self.enemy_kills += 1
                        info["enemy_kills"] += 1

        # -------------------------------------------------
        # ✅ DISTANCIA AL ENEMIGO (antes/después)
        # Reactiva el shaping de aproximación/presión en la recompensa.
        # Se mide la distancia de la unidad que actúa a su enemigo más
        # cercano, antes y después de aplicar la acción.
        # -------------------------------------------------
        pre_dist = None
        post_dist = None

        if actor is not None and actor_side_norm == rl_side_norm:
            enemies_before = [
                u for u in state.units
                if u.alive and u.side != self.rl_side and u.position is not None
            ]
            if actor.position is not None and enemies_before:
                pre_dist = min(
                    safe_hex_distance(actor.position, e.position)
                    for e in enemies_before
                )

            actor_after = next(
                (u for u in next_state.units if u.unit_id == actor.unit_id),
                None,
            )
            enemies_after = [
                u for u in next_state.units
                if u.alive and u.side != self.rl_side and u.position is not None
            ]
            if (
                actor_after is not None
                and actor_after.position is not None
                and enemies_after
            ):
                post_dist = min(
                    safe_hex_distance(actor_after.position, e.position)
                    for e in enemies_after
                )

        # -------------------------------------------------
        # REWARD
        # -------------------------------------------------
        if actor_side_norm == rl_side_norm:
            reward = self.reward_fn.compute(
                state=state,
                next_state=next_state,
                action=action,
                active=actor,
                info=info,
                pre_dist=pre_dist,
                post_dist=post_dist,
            )
            if not self.train_lean:
                reward_components = {}
                try:
                    reward_components = dict(self.reward_fn.get_last_reward_components() or {})
                except Exception:
                    reward_components = {}
                info["reward_components"] = reward_components
                info["reward_component_raw_total"] = float(reward_components.get("raw_total", 0.0) or 0.0)
                info["reward_component_clipped_total"] = float(reward_components.get("clipped_total", reward) or reward)
                info["reward_component_unattributed"] = float(reward_components.get("unattributed", 0.0) or 0.0)
                info["reward_component_capture_near_vp_advance_no_conversion_penalty"] = float(
                    reward_components.get("capture_near_vp_advance_no_conversion_penalty", 0.0) or 0.0
                )
                info["reward_component_capture_post_contact_progress_move_bonus"] = float(
                    reward_components.get("capture_post_contact_progress_move_bonus", 0.0) or 0.0
                )
        else:
            reward = 0.0

        # -------------------------------------------------
        # DONE
        # -------------------------------------------------
        self.current_step += 1
        done = sim_done

        if self.max_steps and self.current_step >= self.max_steps:
            done = True

        info["done"] = done
        info["objective_captured_delta"] = captured_after - captured_before
        info["actor_on_vp_after"] = actor_on_vp_after
        info["actor_vp_owned_by_rl_before"] = actor_vp_owned_by_rl_before
        info["actor_captured_vp_now"] = actor_captured_vp_now
        info["objective_dist_before"] = objective_dist_before
        info["objective_dist_after"] = objective_dist_after
        if not self.train_lean:
            info["objective_rule_active"] = objective_rule_active
            info["objective_tracked_side"] = tracked_side if objective_rule_active else None
            info["objective_captured_before"] = captured_before
            info["objective_captured_after"] = captured_after
            info["actor_on_vp_before"] = actor_on_vp_before
            info["actor_vp_owned_by_rl_after"] = actor_vp_owned_by_rl_after
        if objective_dist_before is not None and objective_dist_after is not None:
            try:
                plan_progress = float(objective_dist_before) - float(objective_dist_after)
            except Exception:
                plan_progress = 0.0
        else:
            plan_progress = 0.0
        info["plan_progress_stub"] = max(-1.0, min(1.0, plan_progress))
        strategy_name = str(info.get("l3_strategy", "") or "").upper()
        plan_intent = str(info.get("plan_intent", "UNKNOWN") or "UNKNOWN").upper()
        info["intent_alignment_stub"] = 1.0 if (strategy_name and strategy_name == plan_intent) else 0.0
        (
            unit_stuck_steps_norm,
            plan_commitment_age_norm,
            intent_alignment_last_k,
            last_failure_reason_onehot,
            team_turn_plan_progress_norm,
            team_units_committed_norm,
            team_focus_vp_set,
        ) = self._update_lote_d_memory(info)
        info["unit_stuck_steps_norm"] = unit_stuck_steps_norm
        info["plan_commitment_age_norm"] = plan_commitment_age_norm
        info["intent_alignment_last_k"] = intent_alignment_last_k
        info["last_failure_reason_onehot"] = list(last_failure_reason_onehot)
        info["team_turn_plan_progress_norm"] = team_turn_plan_progress_norm
        info["team_units_committed_norm"] = team_units_committed_norm
        info["team_focus_vp_set"] = team_focus_vp_set
        if not self.train_lean:
            info["plan_state"] = normalize_plan_state(
                {
                    "intent": info.get("plan_intent"),
                    "unit_role": info.get("plan_unit_role"),
                    "focus_vp_id": info.get("plan_focus_vp_id"),
                    "plan_step_id": info.get("plan_step_id"),
                    "budget_state": info.get("plan_budget_state"),
                    "budget_remaining_by_role": info.get("plan_budget_remaining_by_role"),
                    "budget_violation_count": info.get("plan_budget_violation_count"),
                    "plan_progress_stub": info.get("plan_progress_stub"),
                    "intent_alignment_stub": info.get("intent_alignment_stub"),
                }
            )
            # P4.2 Lote E (observability-only): lightweight diagnostics for eval reports.
            try:
                expected_vp_swing_if_advance = 0.0
                if objective_dist_before is not None and objective_dist_after is not None:
                    expected_vp_swing_if_advance = max(-1.0, min(1.0, (float(objective_dist_before) - float(objective_dist_after)) / 3.0))
                expected_trade_if_attack = 0.0
                if is_attack:
                    expected_trade_if_attack = max(
                        -1.0,
                        min(1.0, (float(info.get("rl_damage", 0) or 0) - float(info.get("enemy_damage", 0) or 0)) / 5.0),
                    )
                if objective_dist_before is not None and float(objective_dist_before) <= 2.0:
                    attack_opportunity_cost_near_vp_norm = max(
                        0.0,
                        min(1.0, (expected_vp_swing_if_advance - expected_trade_if_attack + 1.0) / 2.0),
                    )
                else:
                    attack_opportunity_cost_near_vp_norm = 0.0
                capture_window_open = 1.0 if (
                    bool(info.get("actor_captured_vp_now", False))
                    or (
                        bool(info.get("actor_on_vp_after", False))
                        and not bool(info.get("actor_vp_owned_by_rl_before", False))
                    )
                ) else 0.0
                info["attack_opportunity_cost_near_vp_norm"] = float(attack_opportunity_cost_near_vp_norm)
                info["capture_window_open"] = float(capture_window_open)
                info["expected_vp_swing_if_advance"] = float(expected_vp_swing_if_advance)
                info["expected_trade_if_attack"] = float(expected_trade_if_attack)
            except Exception:
                info["attack_opportunity_cost_near_vp_norm"] = 0.0
                info["capture_window_open"] = 0.0
                info["expected_vp_swing_if_advance"] = 0.0
                info["expected_trade_if_attack"] = 0.0
            if objective_rule_active:
                row = self._objective_outcome_result(next_state)
                result_text = str((row or {}).get("result", "")).strip()
                result_l = result_text.lower()
                if "vittoria totale" in result_l or result_l == "vittoria":
                    result_kind = "victory"
                elif "pareggio" in result_l or "draw" in result_l:
                    result_kind = "draw"
                elif "sconfitta" in result_l or "defeat" in result_l or "lose" in result_l:
                    result_kind = "defeat"
                else:
                    result_kind = "unknown"
                info["objective_result_text"] = result_text
                info["objective_result_kind"] = result_kind

        if self.train_lean:
            # Keep only fields required by reward/obs shaping and core training telemetry.
            info = {k: v for k, v in info.items() if k in _TRAIN_LEAN_INFO_KEYS}

        self._last_action_type = action_type
        own_activated_ratio, enemy_activated_ratio = self._activation_ratios(next_state)

        return (
            encode_state(
                next_state,
                unit=None,
                rl_side=self.rl_side,
                max_turns=self.sim.scenario.max_turns,
                scenario=self.sim.scenario,
                own_activated_ratio=own_activated_ratio,
                enemy_activated_ratio=enemy_activated_ratio,
                last_action_type=self._last_action_type,
                focus_vp_progress_last_step=float(info.get("plan_progress_stub", 0.0) or 0.0),
                focus_vp_id=info.get("plan_focus_vp_id"),
                role_quota_remaining_norm=1.0,
                unit_stuck_steps_norm=float(info.get("unit_stuck_steps_norm", 0.0) or 0.0),
                plan_commitment_age_norm=float(info.get("plan_commitment_age_norm", 0.0) or 0.0),
                intent_alignment_last_k=float(info.get("intent_alignment_last_k", 0.0) or 0.0),
                last_failure_reason_onehot=list(info.get("last_failure_reason_onehot", [0.0, 0.0, 0.0, 0.0]) or [0.0, 0.0, 0.0, 0.0]),
                team_turn_plan_progress_norm=float(info.get("team_turn_plan_progress_norm", 0.0) or 0.0),
                team_units_committed_norm=float(info.get("team_units_committed_norm", 0.0) or 0.0),
                team_focus_vp_set=float(info.get("team_focus_vp_set", 0.0) or 0.0),
            ),
            reward,
            done,
            info,
        )

    def _activation_ratios(self, state):
        runtime = getattr(self.sim, "runtime", None)
        activated_units = getattr(runtime, "activated_units", set()) or set()
        rl_side_norm = str(self.rl_side).upper()

        own_alive = [
            u for u in (state.units or [])
            if getattr(u, "alive", True) and str(getattr(u, "side", "")).upper() == rl_side_norm
        ]
        enemy_alive = [
            u for u in (state.units or [])
            if getattr(u, "alive", True) and str(getattr(u, "side", "")).upper() != rl_side_norm
        ]

        own_activated = sum(1 for u in own_alive if u.unit_id in activated_units)
        enemy_activated = sum(1 for u in enemy_alive if u.unit_id in activated_units)

        own_ratio = own_activated / max(1, len(own_alive))
        enemy_ratio = enemy_activated / max(1, len(enemy_alive))
        return float(own_ratio), float(enemy_ratio)