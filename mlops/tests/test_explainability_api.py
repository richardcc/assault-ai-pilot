"""
Unit and Integration Tests for Hexagonal Spatial Explainability API (IGNH / Grad-CAM).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import torch
import torch.nn as nn

from agents.efficientzero_v2.core.adapter_voec import EZV2Observation
from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.observation import observation_to_tensor
from mlops.reporting.explainability_api import (
    CHANNEL_GROUPS,
    build_obs_from_step_data,
    compute_hex_attribution,
    explain_replay_step,
)


class DummySimpleNet(nn.Module):
    """Minimal CNN conforming to initial_inference interface for testing."""

    def __init__(self, observation_channels: int = 38, action_dim: int = 32):
        super().__init__()
        self.observation_channels = observation_channels
        self.observation_height = 16
        self.observation_width = 16
        self.action_dim = action_dim

        self.representation_tower = nn.Sequential(
            nn.Conv2d(observation_channels, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 16, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.fc = nn.Linear(16 * 16 * 16, action_dim)

    def initial_inference(self, obs: torch.Tensor, return_aux: bool = False):
        feat = self.representation_tower(obs)
        flat = torch.flatten(feat, start_dim=1)
        logits = self.fc(flat)
        value = torch.zeros(obs.shape[0], 1)
        reward = torch.zeros(obs.shape[0], 1)
        if return_aux:
            return feat, logits, value, reward, {}
        return feat, logits, value, reward


def test_build_obs_from_step_data():
    step_data = {
        "step": 2,
        "turn": 2,
        "to_play": "AXIS",
        "action_id": "MOVE:GE_1:3:4",
        "units": [
            {
                "unit_id": "GE_1",
                "unit_key": "GE_RIFLES_43",
                "side": "AXIS",
                "q": 2,
                "r": 3,
                "hp": 4.0,
                "alive": True,
                "doctrine_role": "SPEARHEAD",
            }
        ],
        "vp_map": {"3,4": "AXIS", "5,5": "ALLIED"},
        "obs_terrain_cover_map": {"3,4": 0.50},
    }
    overlay = {
        "max_turns": 10,
        "map_cells": [
            {"q": 2, "r": 3, "terrain": "clear"},
            {"q": 3, "r": 4, "terrain": "woods"},
            {"q": 5, "r": 5, "terrain": "urban"},
        ],
        "vp_hexes": [
            {"q": 3, "r": 4, "value": 2.0},
            {"q": 5, "r": 5, "value": 3.0},
        ],
    }

    obs, coord_meta = build_obs_from_step_data(step_data, overlay)

    assert isinstance(obs, EZV2Observation)
    assert obs.turn == 2
    assert obs.to_play == "AXIS"
    assert obs.max_turns == 10
    assert len(obs.units) == 1
    assert obs.units[0]["unit_id"] == "GE_1"
    assert obs.vp_owner_by_hex.get("3,4") == "AXIS"
    assert obs.terrain_cover_by_hex.get("3,4") == 0.50
    assert coord_meta["playable_hexes"] is not None
    assert coord_meta["q_span"] >= 0


def test_compute_hex_attribution_mathematical_properties():
    net = DummySimpleNet(observation_channels=38, action_dim=16)

    # Synthetic observation
    obs = EZV2Observation(
        turn=1,
        to_play="GE",
        playable_hexes=[{"q": q, "r": r} for q in range(4) for r in range(4)],
        vp_hexes=[{"q": 2, "r": 2, "value": 2.0}],
        units=[{"unit_id": "GE_1", "unit_key": "GE_RIFLES_43", "side": "GE", "q": 1, "r": 1, "hp": 3.0, "alive": True}],
    )
    coord_meta = {
        "min_q": 0,
        "max_q": 3,
        "min_r": 0,
        "max_r": 3,
        "q_span": 3,
        "r_span": 3,
        "playable_hexes": obs.playable_hexes,
    }

    obs_tensor = observation_to_tensor(obs, channels=38, height=16, width=16)
    target_action_index = 3

    result = compute_hex_attribution(
        model=net,
        obs_tensor=obs_tensor,
        action_index=target_action_index,
        coord_meta=coord_meta,
        steps=10,
    )

    # 1. Output structure check
    assert "score_target" in result
    assert "score_baseline" in result
    assert "score_delta" in result
    assert "group_attributions" in result
    assert "channel_attributions" in result
    assert "spatial_heatmaps" in result
    assert "top_influential_hexes" in result
    assert "tactical_rationale" in result

    # 2. Check all canonical groups exist
    for grp in CHANNEL_GROUPS.keys():
        assert grp in result["group_attributions"]
        assert "name" in result["group_attributions"][grp]
        assert "percentage" in result["group_attributions"][grp]
        assert "direction" in result["group_attributions"][grp]

    # 3. Spatial heatmaps integrity
    heatmaps = result["spatial_heatmaps"]
    assert "composite" in heatmaps
    assert "gradcam" in heatmaps
    assert len(heatmaps["composite"]) == len(obs.playable_hexes)
    assert len(heatmaps["gradcam"]) == len(obs.playable_hexes)

    # 4. Top influential hexes
    top_hexes = result["top_influential_hexes"]
    assert len(top_hexes) <= 8
    if top_hexes:
        first = top_hexes[0]
        assert "q" in first and "r" in first
        assert "dominant_channel" in first
        assert "impact" in first


def test_explain_replay_step_real_run(tmp_path: Path):
    # Test on actual benchmark run if present
    repo_root = Path(__file__).resolve().parents[2]
    eval_source = "runs_curriculum/efficientzero_v2_fa79dfb1/xai/bench_replay_index_latest.json"
    full_path = repo_root / eval_source

    if not full_path.exists():
        pytest.skip(f"Replay index {full_path} not present in this workspace.")

    from mlops.reporting.viewer_data_access import load_scenario_overlay

    payload = explain_replay_step(
        repo_root=repo_root,
        eval_source_path=eval_source,
        episode_id="episode_0",
        step_index=0,
        steps=8,
        load_scenario_overlay_fn=load_scenario_overlay,
    )

    assert payload.get("ok") is True
    assert payload.get("unit_id") != ""
    assert payload.get("action_id") != ""
    assert "group_attributions" in payload
    assert "spatial_heatmaps" in payload
    assert "tactical_rationale" in payload
    assert payload.get("execution_time_ms", 0.0) > 0.0


def test_compute_step_tactical_heads_synthetic():
    from mlops.reporting.explainability_api import compute_step_tactical_heads, _extract_auxiliary_heads
    import torch

    class DummyAuxNet(DummySimpleNet):
        def initial_inference(self, obs: torch.Tensor, return_aux: bool = False):
            feat, logits, value, reward = super().initial_inference(obs, return_aux=False)
            aux = {
                "threat_map_pred": torch.ones(obs.shape[0], 1, 16, 16) * 0.75,
                "morale_pred": torch.tensor([[0.1, 0.7, 0.1, 0.1]]),
                "attrition_pred": torch.tensor([[0.25, 0.50]]),
                "final_ownership_pred": torch.ones(obs.shape[0], 1, 16, 16) * 0.5,
            }
            if return_aux:
                return feat, logits, value, reward, aux
            return feat, logits, value, reward

    net = DummyAuxNet(observation_channels=38, action_dim=16)
    obs_tensor = torch.zeros((38, 16, 16), dtype=torch.float32)
    # Put enemy threat on channel 7
    obs_tensor[7, 2, 3] = 0.85
    coord_meta = {
        "min_q": 0,
        "min_r": 0,
        "q_span": 6,
        "r_span": 6,
        "playable_hexes": [{"q": 0, "r": 0}, {"q": 3, "r": 2}],
    }

    heads = _extract_auxiliary_heads(net, obs_tensor, coord_meta)
    assert "threat_map" in heads
    assert "threat_summary" in heads
    assert "morale" in heads
    assert "attrition" in heads
    assert heads["threat_summary"]["max_threat"] >= 0.0
    assert len(heads["threat_map"]) == 2
    assert "suppression_risk" in heads["morale"]
    assert "predicted_friendly_casualties" in heads["attrition"]
    assert heads["attrition"]["predicted_friendly_casualties"] == 0.25
    assert heads["attrition"]["predicted_enemy_casualties"] == 0.50
    assert heads["morale"]["status"] == "DANGER"

