"""
Unit tests for Task 2.7: Canonical Layer Initialization for Reinforcement Learning
(Orthogonal, Zero-Init ResNet & Fixup, Kaiming Normal).

Validates the formal mathematical properties:
    1. Orthogonal Policy Head (gain=0.01, bias=0.0):
       Guarantees maximum initial uniform entropy H(pi) ~ log(|A|) at step 0.
    2. Orthogonal Value & Reward Heads (gain=1.0, bias=0.0):
       Preserves representation norm and variance without early saturation.
    3. Kaiming Normal (fan_out, relu/silu) for Conv2d and intermediate Linear layers:
       Preserves activation variance across deep towers.
    4. Zero-Init ResNet (Goyal et al. 2017 / Zhang et al. 2019 Fixup):
       Gamma=0 and Beta=0 on the second residual normalization (gn2/ln2),
       guaranteeing pure identity mapping F(x) = 0 at step 0.
"""

from __future__ import annotations

import math
import pytest
import torch
import torch.nn as nn

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.network_base import (
    EfficientZeroV2BaseNetwork,
    ResidualConvBlock,
    ResidualMLPBlock,
    apply_canonical_rl_init,
    _get_last_linear,
)


def test_orthogonal_policy_head_entropy():
    """Verify orthogonal policy head with gain=0.01 yields near-maximum uniform entropy at step 0."""
    action_dim = 32
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=48,
        action_dim=action_dim,
        encoder_type="cnn",
        observation_channels=16,
        observation_height=16,
        observation_width=16,
        apply_rl_init=True,
    )

    last_pol = _get_last_linear(net.prediction_policy)
    assert last_pol is not None
    # Check bias is exactly zero
    assert torch.all(last_pol.bias == 0.0)

    # Check weight Frobenius norm is consistent with small gain=0.01
    weight_norm = torch.norm(last_pol.weight).item()
    # Expected Frobenius norm for orthogonal matrix of shape (32, d): gain * sqrt(32) = 0.01 * 5.657 = ~0.0566
    assert abs(weight_norm - (0.01 * math.sqrt(action_dim))) < 1e-3

    # Forward pass with random inputs: policy distribution must have near-maximum uniform entropy
    obs = torch.randn(4, 16, 16, 16)
    _, policy_logits, _, _ = net.initial_inference(obs)
    probs = torch.softmax(policy_logits, dim=-1)

    max_entropy = math.log(action_dim)
    # Shannon entropy: -sum(p * log(p))
    entropy = -torch.sum(probs * torch.log(probs.clamp(min=1e-9)), dim=-1)

    for e in entropy:
        # Discrepancy from theoretical max uniform entropy must be under 0.02 nats
        assert abs(e.item() - max_entropy) < 0.02, f"Expected entropy close to {max_entropy}, got {e.item()}"


def test_orthogonal_value_and_reward_heads():
    """Verify value, reward, and consistency output projections have gain=1.0 and zero bias."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=16,
        observation_height=16,
        observation_width=16,
        support_size=5,
        apply_rl_init=True,
    )

    # 1. Prediction Value
    last_val = _get_last_linear(net.prediction_value)
    assert last_val is not None
    assert torch.all(last_val.bias == 0.0)
    out_features = last_val.weight.shape[0]
    expected_val_norm = 1.0 * math.sqrt(out_features)
    assert abs(torch.norm(last_val.weight).item() - expected_val_norm) < 1e-2

    # 2. Dynamics Reward
    last_rew = _get_last_linear(net.dynamics_reward)
    assert last_rew is not None
    assert torch.all(last_rew.bias == 0.0)
    expected_rew_norm = 1.0 * math.sqrt(last_rew.weight.shape[0])
    assert abs(torch.norm(last_rew.weight).item() - expected_rew_norm) < 1e-2

    # 3. Consistency Projection
    last_proj = _get_last_linear(net.consistency_projection)
    assert last_proj is not None
    assert torch.all(last_proj.bias == 0.0)
    expected_proj_norm = 1.0 * math.sqrt(last_proj.weight.shape[0])
    assert abs(torch.norm(last_proj.weight).item() - expected_proj_norm) < 1e-2


def test_zero_init_resnet_identity_at_step_zero():
    """Verify Zero-Init ResNet sets gn2/ln2 weight and bias to 0.0, producing zero residual branch."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=16,
        observation_height=16,
        observation_width=16,
        dynamics_blocks=2,
        prediction_blocks=2,
        apply_rl_init=True,
    )

    # Check all ResidualConvBlocks in the network
    conv_blocks = [m for m in net.modules() if isinstance(m, ResidualConvBlock)]
    assert len(conv_blocks) > 0

    for block in conv_blocks:
        assert torch.all(block.gn2.weight == 0.0), "gn2 weight must be zero-initialized"
        assert torch.all(block.gn2.bias == 0.0), "gn2 bias must be zero-initialized"

        # Mathematical property: residual branch output before addition must be strictly zero
        test_x = torch.randn(2, 48, 8, 8).abs() + 0.1  # strictly positive
        # forward pass: output = act2(x + z), where z = attn(gn2(conv2(...)))
        # Since gn2 has weight=0, bias=0, gn2 output is 0.0, attn(0) = 0.0
        out = block(test_x)
        expected = block.act2(test_x)
        assert torch.allclose(out, expected, atol=1e-6), "Residual branch must evaluate to zero at step 0"


def test_mlp_encoder_zero_init_and_orthogonal():
    """Verify canonical RL initialization functions correctly on MLP architecture."""
    net = EfficientZeroV2Network(
        observation_dim=64,
        hidden_dim=32,
        action_dim=16,
        encoder_type="mlp",
        dynamics_blocks=2,
        prediction_blocks=2,
        apply_rl_init=True,
    )

    # Check ResidualMLPBlocks
    mlp_blocks = [m for m in net.modules() if isinstance(m, ResidualMLPBlock)]
    assert len(mlp_blocks) > 0

    for block in mlp_blocks:
        assert torch.all(block.ln2.weight == 0.0)
        assert torch.all(block.ln2.bias == 0.0)

        test_x = torch.randn(3, 32).abs() + 0.1
        out = block(test_x)
        expected = block.act2(test_x)
        assert torch.allclose(out, expected, atol=1e-6)

    # Policy head
    assert torch.all(net.prediction_policy.bias == 0.0)
    expected_pol_norm = 0.01 * math.sqrt(16)
    assert abs(torch.norm(net.prediction_policy.weight).item() - expected_pol_norm) < 1e-3


def test_kaiming_normal_intermediate_layers():
    """Verify intermediate convolutional and linear layers are initialized with He / Kaiming normal."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=64,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=16,
        observation_height=16,
        observation_width=16,
        apply_rl_init=True,
    )

    # Check representation input convolution
    rep_conv = net.representation_input[0]
    assert isinstance(rep_conv, nn.Conv2d)
    # Mean of Kaiming Normal weights should be close to 0.0
    assert abs(rep_conv.weight.mean().item()) < 0.05
    # Standard deviation should be close to sqrt(2 / fan_out)
    fan_out = rep_conv.out_channels * rep_conv.kernel_size[0] * rep_conv.kernel_size[1]
    expected_std = math.sqrt(2.0 / fan_out)
    actual_std = rep_conv.weight.std().item()
    assert abs(actual_std - expected_std) < 0.03
