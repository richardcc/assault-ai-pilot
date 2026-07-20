from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

from agents.efficientzero_v2.core.adapter_voec import EZV2VOECAdapter
from agents.efficientzero_v2.core.observability import EventBus, JsonlWriter, RunManifest

__all__ = [
    "EventBus",
    "JsonlWriter",
    "EZV2VOECAdapter",
    "RunManifest",
    "EfficientZeroConfig",
    "load_efficientzero_config",
]


_DEFAULT_OBJECTIVE_SIGNAL_CFG: dict[str, Any] = {
    "opportunity_near_vp_max_dist": 3,
}

_DEFAULT_OBJECTIVE_HEAD_CFG: dict[str, Any] = {
    "progress_positive_threshold": 0.0,
}

_DEFAULT_OBJECTIVE_REPORTING_CFG: dict[str, Any] = {
    "conversion_window_steps_after_progress": 2,
    "near_vp_max_dist": 2.0,
    "strong_progress_delta_threshold": 2.0,
    "high_confidence_prob_threshold": 0.60,
    "high_confidence_margin_threshold": 0.25,
    "assault_advantage_prob_threshold": 0.55,
    "assault_advantage_margin_threshold": 0.20,
    "assault_advantage_legal_count_threshold": 6,
    "assault_advantage_cover_max": 0.35,
    "assault_advantage_min_score": 2,
    "decision_flip_legal_count_tolerance": 2,
}

_DEFAULT_REWARD_SHAPING_CFG: dict[str, Any] = {
    "terminal_scale": 1.0,
    "damage_weight": 0.05,
    "kill_weight": 0.40,
    "vp_action_bonus": 0.14,
    "capture_bonus": 0.70,
    "vp_capture_bonus_per_hex": 1.20,
    "vp_net_gain_bonus": 0.30,
    "vp_net_loss_penalty": 0.20,
    "objective_progress_bonus_per_hex": 0.95,
    "objective_team_progress_bonus_per_hex": 0.60,
    "objective_progress_cap_abs": 1.0,
    "objective_team_progress_cap_abs": 1.5,
    "objective_no_progress_penalty": 0.46,
    "objective_no_progress_attack_penalty": 0.40,
    "reaction_fire_miss_penalty": 0.08,
    "reaction_fire_soft_signal_enabled": True,
    "reaction_fire_soft_signal_weight": 0.04,
    "reaction_fire_soft_signal_expected_damage_scale": 4.0,
    "reaction_exposure_component_enabled": True,
    "reaction_exposure_component_weight": 0.08,
    "reaction_exposure_component_cap_abs": 0.20,
    "global_strategy_soft_enabled": True,
    "global_strategy_vp_control_net_gain_weight": 0.08,
    "global_strategy_units_in_vp_ring_weight": 0.04,
    "global_strategy_enemy_vp_threat_reduced_weight": 0.05,
    "global_strategy_sustained_vp_advantage_weight": 0.02,
    "global_strategy_role_consistency_weight": 0.03,
    "global_strategy_setup_convert_weight": 0.03,
    "global_strategy_vp_ring_radius": 2,
    "global_strategy_enemy_threat_radius": 3,
    "global_strategy_sustained_advantage_min_turns": 2,
    "global_strategy_total_cap_abs": 0.15,
    "vp_horizon_soft_enabled": True,
    "vp_horizon_soft_weight": 0.02,
    "vp_horizon_soft_cap_steps": 8.0,
    "enemy_threat_component_enabled": False,
    "enemy_threat_component_weight": 0.01,
    "enemy_threat_component_horizon_steps": 6.0,
    "enemy_threat_component_cap_abs": 0.03,
    "enemy_threat_component_immediate_capture_bonus": 0.40,
    "mobility_opportunity_cost_component_enabled": False,
    "mobility_opportunity_cost_component_weight": 0.01,
    "mobility_opportunity_cost_component_cap_abs": 0.02,
    "cross_unit_synergy_component_enabled": False,
    "cross_unit_synergy_component_weight": 0.01,
    "cross_unit_synergy_component_cap_abs": 0.02,
    "obs_enemy_vp_threat_radius": 6,
    "obs_vp_ownership_ttl_cap": 8,
    "idle_penalty": -0.08,
    "idle_with_options_multiplier": 3.0,
    "terminal_win_bonus": 0.20,
    "terminal_draw_bonus": 0.02,
    "terminal_loss_penalty": 0.20,
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "selfplay": {
        "mcts_q_clip_abs": 20.0,
        "mcts_min_root_visits_per_action": 0,
        "mcts_min_root_visits_top_n": 0,
        "mcts_q_root_normalization_mode": "adaptive_minmax",
        "mcts_q_root_normalization_strength": 0.40,
        "mcts_vp_tiebreak_epsilon": 0.02,
        "mcts_q_flat_spread_epsilon": 1.0e-6,
        "mcts_vp_flat_q_score_epsilon": 0.02,
        "mcts_vp_flat_q_min_progress": 0.0,
        "mcts_chance_mode": "off",
        "mcts_chance_samples_per_expansion": 1,
        "mcts_chance_value_noise_std": 0.0,
        "mcts_success_prob_enabled": False,
        "mcts_success_prob_alpha": 0.0,
        "mcts_success_prob_center": 0.5,
        "mcts_success_prob_scale": 0.5,
        "mcts_success_prob_centered_clip_abs": 1.0,
        "mcts_success_prob_expected_damage_scale": 4.0,
        "unit_prefilter_enabled": False,
        "unit_prefilter_replan_enabled": False,
        "unit_prefilter_top_k": 1,
        "unit_prefilter_vp_progress_weight": 1.0,
        "unit_prefilter_capture_opportunity_weight": 2.0,
        "unit_prefilter_threat_weight": 0.25,
        "reward_shaping": _DEFAULT_REWARD_SHAPING_CFG,
    },
    "train": {
        "objective_loss_weight": 0.12,
        "objective_target_mode": "progress",
        "objective_pos_weight": 6.8,
        "objective_opportunity_max_dist": 3,
        "aux_objective_enabled": False,
        "aux_objective_loss_weight": 0.0,
        "aux_intent_loss_weight": 0.5,
        "aux_multi_vp_loss_weight": 0.5,
        "aux_multi_vp_feature_dim": 4,
        "aux_intent_classes": 8,
        "objective_signal": _DEFAULT_OBJECTIVE_SIGNAL_CFG,
        "objective_head": _DEFAULT_OBJECTIVE_HEAD_CFG,
        "objective_reporting": _DEFAULT_OBJECTIVE_REPORTING_CFG,
    }
}


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base or {})
    for key, value in dict(override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(dict(out.get(key, {}) or {}), dict(value or {}))
        else:
            out[key] = value
    return out


@dataclass(frozen=True)
class EfficientZeroConfig:
    raw: Dict[str, Any]

    @property
    def paths(self) -> Dict[str, Any]:
        return self.raw["paths"]

    @property
    def scenario(self) -> Dict[str, Any]:
        return self.raw["scenario"]

    @property
    def model(self) -> Dict[str, Any]:
        return self.raw["model"]

    @property
    def selfplay(self) -> Dict[str, Any]:
        return self.raw["selfplay"]

    @property
    def train(self) -> Dict[str, Any]:
        return self.raw["train"]


def load_efficientzero_config(path: str | Path):
    """
    Local EZv2 config loader with merged defaults.
    """
    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw = _deep_merge_dict(_DEFAULT_CONFIG, dict(loaded or {}))
    return EfficientZeroConfig(raw=dict(raw))
