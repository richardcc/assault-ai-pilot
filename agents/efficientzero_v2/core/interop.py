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
    "MuZeroVOECAdapter",
    "EZV2VOECAdapter",
    "RunManifest",
    "EfficientZeroConfig",
    "load_efficientzero_config",
]


_DEFAULT_OBJECTIVE_SIGNAL_CFG: dict[str, Any] = {
    "opportunity_near_vp_max_dist": 2.5,
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
    "capture_bonus": 0.62,
    "vp_capture_bonus_per_hex": 1.12,
    "vp_net_gain_bonus": 0.30,
    "vp_net_loss_penalty": 0.20,
    "objective_progress_bonus_per_hex": 0.72,
    "objective_no_progress_penalty": 0.40,
    "objective_no_progress_attack_penalty": 0.44,
    "reaction_fire_miss_penalty": 0.08,
    "idle_penalty": -0.08,
    "idle_with_options_multiplier": 3.0,
    "terminal_win_bonus": 0.20,
    "terminal_draw_bonus": 0.02,
    "terminal_loss_penalty": 0.20,
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "selfplay": {
        "reward_shaping": _DEFAULT_REWARD_SHAPING_CFG,
    },
    "train": {
        "objective_loss_weight": 0.12,
        "objective_target_mode": "progress",
        "objective_pos_weight": 5.6,
        "objective_opportunity_max_dist": 2.5,
        "objective_signal": _DEFAULT_OBJECTIVE_SIGNAL_CFG,
        "objective_head": _DEFAULT_OBJECTIVE_HEAD_CFG,
        "objective_reporting": _DEFAULT_OBJECTIVE_REPORTING_CFG,
    }
}

# Backward-compatible alias to avoid touching call sites.
MuZeroVOECAdapter = EZV2VOECAdapter


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
