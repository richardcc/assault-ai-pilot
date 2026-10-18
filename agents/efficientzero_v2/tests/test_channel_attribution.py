import pytest
import torch

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from scripts.analyze_channel_attribution import analyze_channels


def test_analyze_channels_with_all_heads():
    """Verify that channel attribution evaluates all 9 active prediction heads with Spatial Attention."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=32,
        action_dim=16,
        encoder_type="cnn",
        observation_channels=8,
        observation_height=16,
        observation_width=16,
        enable_threat_head=True,
        enable_final_ownership_head=True,
        enable_attrition_head=True,
        enable_morale_head=True,
        objective_intent_classes=8,
        multi_vp_feature_dim=4,
        support_size=15,
        use_spatial_attention=True,
    )
    net.eval()

    # Create dummy observations
    observations = [torch.randn(8, 16, 16) for _ in range(4)]

    report = analyze_channels(net, observations, device="cpu")

    assert report["num_observations_analyzed"] == 4
    assert report["channels_analyzed"] == 8
    assert "heads_analyzed" in report
    for expected_head in [
        "policy",
        "value",
        "threat_map",
        "final_ownership",
        "attrition",
        "morale",
        "objective",
        "objective_intent",
        "multi_vp",
    ]:
        assert expected_head in report["heads_analyzed"]

    ranked = report["ranked_channels"]
    assert len(ranked) == 8

    # Each channel row must contain individual metrics and head_attributions
    for row in ranked:
        assert "importance_score" in row
        assert "threat_shift_mean" in row
        assert "final_ownership_shift_mean" in row
        assert "attrition_shift_mean" in row
        assert "morale_shift_mean" in row
        assert "objective_shift_mean" in row
        assert "intent_shift_mean" in row
        assert "multi_vp_shift_mean" in row
        assert "grad_saliency_threat" in row
        assert "grad_saliency_final_ownership" in row
        assert "grad_saliency_attrition" in row
        assert "grad_saliency_morale" in row
        assert "grad_saliency_objective" in row
        assert "grad_saliency_intent" in row
        assert "grad_saliency_multi_vp" in row

        ha = row.get("head_attributions")
        assert ha is not None
        assert "policy_kl" in ha
        assert "value_shift" in ha
        assert "threat_shift" in ha
        assert "final_ownership_shift" in ha
        assert "attrition_shift" in ha
        assert "morale_shift" in ha
        assert "objective_shift" in ha
        assert "intent_shift" in ha
        assert "multi_vp_shift" in ha
        assert "grad_threat" in ha
        assert "grad_final_ownership" in ha
        assert "grad_attrition" in ha
        assert "grad_morale" in ha
        assert "grad_objective" in ha
        assert "grad_intent" in ha
        assert "grad_multi_vp" in ha


def test_observation_enhanced_channels_contract():
    """Verify all 32 tactical channels are uniquely named, finite, and populated in observation_to_tensor."""
    from types import SimpleNamespace
    from agents.efficientzero_v2.core.observation import observation_to_tensor
    from agents.efficientzero_v2.train.train_engine import _channel_name

    # 1. Verify all 32 channels [0..31] have canonical semantic names (not fallback ch_X)
    channel_names = [_channel_name(i) for i in range(32)]
    assert len(set(channel_names)) == 32
    for idx, cname in enumerate(channel_names):
        assert not cname.startswith(f"ch_{idx}") and not cname.startswith(f"channel_{idx}"), (
            f"Channel {idx} has fallback name {cname}"
        )

    assert _channel_name(4) == "ally_crossfire_risk"
    assert _channel_name(5) == "enemy_target_engagement"
    assert _channel_name(8) == "ally_heavy_mg_support"
    assert _channel_name(9) == "enemy_heavy_mg_support"
    assert _channel_name(10) == "ally_indirect_mortar"
    assert _channel_name(18) == "vp_distance_field"
    assert _channel_name(23) == "enemy_indirect_mortar"
    assert _channel_name(27) == "heavy_fortifications"
    assert _channel_name(29) == "hazard_mines_and_wire"

    # 2. Rich tactical state populating all 32 channels
    obs = SimpleNamespace(
        turn=2,
        max_turns=8,
        done=False,
        to_play="ALLIES",
        units=[
            {"q": 0, "r": 0, "side": "ALLIES", "unit_key": "US_RIFLES_43", "alive": True, "hp": 10},
            {"q": 0, "r": 1, "side": "ALLIES", "unit_key": "GE_HEAVY_MG_42", "alive": True, "hp": 6},
            {"q": 1, "r": 1, "side": "ALLIES", "unit_key": "US_81MM_MORTAR", "alive": True, "hp": 4},
            {"q": 2, "r": 0, "side": "AXIS", "unit_key": "GE_RIFLES_43", "alive": True, "hp": 10},
            {"q": 2, "r": 1, "side": "AXIS", "unit_key": "IT_BREDA_MMG", "alive": True, "hp": 6},
            {"q": 3, "r": 1, "side": "AXIS", "unit_key": "GE_50MM_MORTAR", "alive": True, "hp": 4},
        ],
        reinforcements=[
            {"q": -1, "r": 0, "side": "ALLIES", "turn": 3, "arrival_prob": 0.8, "recon_tier": 5},
            {"q": 4, "r": 0, "side": "AXIS", "turn": 3, "arrival_prob": 0.5, "recon_tier": 4},
        ],
        playable_hexes=[
            {"q": -1, "r": 0}, {"q": 0, "r": 0}, {"q": 0, "r": 1}, {"q": 1, "r": 0},
            {"q": 1, "r": 1}, {"q": 2, "r": 0}, {"q": 2, "r": 1}, {"q": 3, "r": 1},
            {"q": 4, "r": 0}, {"q": 5, "r": 0},
        ],
        vp_hexes=[{"q": 1, "r": 0}, {"q": 2, "r": 0}],
        vp_owner_by_hex={"1,0": "ALLIES", "2,0": "AXIS"},
        terrain_move_cost_by_hex={"0,0": 1.0, "1,0": 1.5, "2,0": 1.0, "1,1": 1.2},
        terrain_cover_by_hex={"0,0": 0.4, "1,0": 0.5, "2,0": 0.4, "1,1": 0.3},
        terrain_los_block_by_hex={"0,0": 0.2, "1,0": 0.0, "2,0": 0.3, "1,1": 0.1},
        fortification_type_by_hex={
            "0,0": "bunker",
            "1,1": "trench",
            "2,1": "minefield",
            "3,1": "barbed_wire",
        },
    )
    ten = observation_to_tensor(obs, channels=32, height=16, width=16)
    assert ten.shape == (32, 16, 16)
    assert torch.isfinite(ten).all()

    # 3. Verify ALL 32 channels have non-zero tactical data
    for ch_idx in range(32):
        ch_sum = ten[ch_idx].abs().sum().item()
        assert ch_sum > 0.0, f"Channel {ch_idx} ({_channel_name(ch_idx)}) has zero activation in tactical scene"


