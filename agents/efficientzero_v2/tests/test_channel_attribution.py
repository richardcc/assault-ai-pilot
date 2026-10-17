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
