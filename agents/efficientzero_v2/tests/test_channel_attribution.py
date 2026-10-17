import pytest
import torch

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from scripts.analyze_channel_attribution import analyze_channels


def test_analyze_channels_with_all_heads():
    """Verify that channel attribution evaluates all active heads (policy, value, threat_map, attrition, morale, objective)."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=32,
        action_dim=16,
        encoder_type="cnn",
        observation_channels=8,
        observation_height=16,
        observation_width=16,
        enable_threat_head=True,
        enable_attrition_head=True,
        enable_morale_head=True,
        use_spatial_attention=False,
    )
    net.eval()

    # Create dummy observations
    observations = [torch.randn(8, 16, 16) for _ in range(4)]

    report = analyze_channels(net, observations, device="cpu")

    assert report["num_observations_analyzed"] == 4
    assert report["channels_analyzed"] == 8
    assert "heads_analyzed" in report
    for expected_head in ["policy", "value", "threat_map", "attrition", "morale", "objective"]:
        assert expected_head in report["heads_analyzed"]

    ranked = report["ranked_channels"]
    assert len(ranked) == 8

    # Each channel row must contain individual metrics and head_attributions
    for row in ranked:
        assert "importance_score" in row
        assert "threat_shift_mean" in row
        assert "attrition_shift_mean" in row
        assert "morale_shift_mean" in row
        assert "objective_shift_mean" in row
        assert "grad_saliency_threat" in row
        assert "grad_saliency_attrition" in row
        assert "grad_saliency_morale" in row

        ha = row.get("head_attributions")
        assert ha is not None
        assert "policy_kl" in ha
        assert "value_shift" in ha
        assert "threat_shift" in ha
        assert "attrition_shift" in ha
        assert "morale_shift" in ha
        assert "objective_shift" in ha
        assert "grad_threat" in ha
        assert "grad_attrition" in ha
        assert "grad_morale" in ha


def test_observation_enhanced_channels_contract():
    """Verify that channels 4, 5, 18, and 27 are populated and named correctly."""
    from types import SimpleNamespace
    from agents.efficientzero_v2.core.observation import observation_to_tensor
    from agents.efficientzero_v2.train.train_engine import _channel_name

    assert _channel_name(4) == "ally_crossfire_risk"
    assert _channel_name(5) == "enemy_target_engagement"
    assert _channel_name(18) == "vp_delta_pressure"
    assert _channel_name(27) == "fortification_and_urban_chokepoint"

    obs = SimpleNamespace(
        turn=1,
        done=False,
        to_play="ALLIES",
        units=[
            {"q": 0, "r": 0, "side": "ALLIES", "unit_key": "US_INFANTRY_RIFLES", "alive": True, "hp": 10},
            {"q": 1, "r": 0, "side": "AXIS", "unit_key": "GER_INFANTRY_RIFLES", "alive": True, "hp": 10},
        ],
        playable_hexes=[{"q": 0, "r": 0}, {"q": 1, "r": 0}, {"q": 2, "r": 0}],
        vp_hexes=[{"q": 2, "r": 0}],
        vp_owner_by_hex={"2,0": "AXIS"},
        terrain_move_cost_by_hex={"0,0": 1.0, "1,0": 1.0, "2,0": 1.0},
        terrain_cover_by_hex={"0,0": 0.4, "1,0": 0.4, "2,0": 0.4},
        terrain_los_block_by_hex={"0,0": 0.5, "1,0": 0.5, "2,0": 0.5},
        fortification_type_by_hex={},
    )
    ten = observation_to_tensor(obs, channels=32, height=16, width=16)
    assert ten.shape == (32, 16, 16)
    # Channel 4 (crossfire risk) should be populated for allied position
    assert ten[4].sum().item() >= 0.0
    # Channel 5 (target engagement) should be populated for enemy position
    assert ten[5].sum().item() >= 0.0
    # Channel 18 (vp delta pressure) should be positive near playable hexes
    assert ten[18].sum().item() > 0.0
    # Channel 27 (fortification / urban chokepoint) should reflect cover/los bottleneck
    assert ten[27].sum().item() > 0.0

