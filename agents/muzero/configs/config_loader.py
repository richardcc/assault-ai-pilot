from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

_DEFAULT_OBJECTIVE_SIGNAL_CFG: dict[str, Any] = {
    "opportunity_near_vp_max_dist": 2.0,
}

_DEFAULT_OBJECTIVE_HEAD_CFG: dict[str, Any] = {
    "progress_positive_threshold": 0.0,
}

_DEFAULT_OBJECTIVE_REPORTING_CFG: dict[str, Any] = {
    "near_vp_max_dist": 2.0,
    "strong_progress_delta_threshold": 2.0,
    "high_confidence_prob_threshold": 0.60,
    "high_confidence_margin_threshold": 0.25,
    "assault_advantage_prob_threshold": 0.55,
    "assault_advantage_margin_threshold": 0.20,
    "assault_advantage_cover_max": 0.35,
    "assault_advantage_min_score": 3,
    "decision_flip_legal_count_tolerance": 2,
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "train": {
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
class MuZeroConfig:
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


def load_muzero_config(path: Path) -> MuZeroConfig:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw = _deep_merge_dict(_DEFAULT_CONFIG, dict(loaded or {}))
    return MuZeroConfig(raw=dict(raw))
