from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RewardConfig:
    # Core combat quality
    trade_weight: float = 1.0
    bad_trade_penalty: float = 0.5
    good_trade_base_bonus: float = 0.4
    good_trade_scale_bonus: float = 0.25
    zero_damage_attack_penalty: float = 0.4
    attack_base_cost: float = 0.1
    non_attack_bad_trade_bonus: float = 0.2

    # Tactical shaping
    kill_bonus: float = 3.0
    move_closer_bonus: float = 0.05
    in_range_bonus: float = 0.05
    retreat_bonus: float = 0.6
    retreat_no_damage_bonus: float = 0.6
    hold_non_attack_penalty: float = 0.15
    pressure_penalty: float = 0.3
    pressure_distance_threshold: int = 3

    # Action regularization
    wait_penalty: float = 0.25
    repeat_action_penalty: float = 0.05
    action_finalization_fallback_penalty: float = 0.08
    invalid_action_finalization_penalty: float = 0.20
    wait_recovery_backstep_setup_penalty: float = 0.25
    setup_progress_bonus: float = 0.12

    # Objectives/endgame/time
    vp_delta_weight: float = 1.5
    objective_approach_bonus: float = 0.25
    objective_move_away_penalty: float = 0.12
    objective_near_hold_penalty: float = 0.2
    capture_retreat_penalty: float = 0.5
    capture_advance_bonus: float = 0.2
    capture_strategy_bonus: float = 0.12
    preserve_when_objectives_pending_penalty: float = 0.08
    capture_vp_presence_bonus: float = 0.15
    capture_vp_hold_streak_bonus: float = 0.14
    capture_no_progress_penalty: float = 0.12
    capture_fallback_attack_penalty: float = 0.25
    capture_staging_bonus: float = 0.08
    capture_idle_no_progress_penalty: float = 0.10
    capture_staging_repeat_penalty: float = 0.12
    vp_stepin_selected_bonus: float = 0.60
    vp_stepin_missed_near_penalty: float = 0.18
    vp_control_after_entry_bonus: float = 0.32
    early_vp_entry_turn_bonus_cutoff: int = 15
    early_vp_entry_bonus: float = 0.4
    late_capture_turn_threshold: int = 15
    late_capture_target_min: int = 4
    late_capture_penalty: float = 0.15
    objective_control_target_ratio: float = 0.9
    objective_shortfall_step_penalty: float = 0.28
    objective_shortfall_terminal_penalty: float = 1.8
    strategy_dominance_threshold: float = 0.80
    strategy_dominance_penalty: float = 0.05
    strategy_dominance_min_decisions: int = 25
    anti_concentration_bonus: float = 0.06
    dominant_unit_share_threshold: float = 0.70
    dominant_unit_share_penalty: float = 0.10
    indirect_attack_bonus: float = 0.03
    indirect_effective_hit_bonus: float = 0.1
    l3_attrit_attack_bonus: float = 0.25
    l3_attrit_advance_penalty: float = 0.18
    l3_deny_attack_bonus: float = 0.20
    l3_deny_advance_penalty: float = 0.14
    win_bonus: float = 5.0
    lose_penalty: float = 5.0
    time_penalty: float = 0.02

    # Post-clamp
    min_reward: float = -10.0
    max_reward: float = 10.0

    # Extra shaping layer (ShapedReward)
    shaped_zero_damage_penalty: float = 0.6
    shaped_good_trade_bonus: float = 0.2

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "RewardConfig":
        base = RewardConfig()
        merged = {**asdict(base), **payload}
        return RewardConfig(**merged)


def load_reward_config(path: Path | None = None) -> RewardConfig:
    if path is None:
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "assault_sim" / "config" / "reward_config.json"
    if not path.exists():
        return RewardConfig()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return RewardConfig.from_dict(data)

