import torch
import pytest

from agents.efficientzero_v2.core.support import (
    symlog,
    symexp,
    scalar_to_hl_gauss,
    cross_entropy_hl_gauss,
    scalar_to_two_hot,
    support_to_scalar,
)
from agents.efficientzero_v2.core.network_base import (
    HexagonalMaskConv2d,
    ResidualConvBlock,
    TemporalContextBlock,
)


def test_symlog_symexp_invertibility():
    x = torch.tensor([-150.0, -10.0, -1.0, 0.0, 1.0, 10.0, 150.0])
    compressed = symlog(x)
    recovered = symexp(compressed)
    assert torch.allclose(x, recovered, atol=1e-5)


def test_hl_gauss_distribution_properties():
    scalars = torch.tensor([[-5.2], [0.0], [7.8]])
    dist = scalar_to_hl_gauss(scalars, support_size=10, sigma=0.75, use_phi=False)
    assert dist.shape == (3, 1, 21)
    # Probabilities must sum to 1.0
    sums = dist.sum(dim=-1)
    assert torch.allclose(sums, torch.ones_like(sums), atol=1e-5)


def test_cross_entropy_hl_gauss():
    batch_size = 4
    num_atoms = 61
    logits = torch.randn(batch_size, num_atoms, requires_grad=True)
    targets = torch.tensor([[1.5], [-2.0], [0.0], [5.5]])
    loss = cross_entropy_hl_gauss(logits, targets, support_size=30, sigma=0.75)
    assert loss.dim() == 0
    assert loss.item() > 0
    loss.backward()
    assert logits.grad is not None
    assert torch.isfinite(logits.grad).all()


def test_hexagonal_mask_conv2d():
    conv = HexagonalMaskConv2d(4, 4, kernel_size=3, padding=1)
    assert conv.hex_mask is not None
    # Verify the 2 diagonal non-hex corners are 0.0
    mask = conv.hex_mask.squeeze()
    assert mask[0, 0].item() == 0.0
    assert mask[2, 2].item() == 0.0
    # Other 6 directional neighbors + center are 1.0
    assert mask[0, 1].item() == 1.0
    assert mask[1, 0].item() == 1.0
    assert mask[1, 2].item() == 1.0
    assert mask[2, 1].item() == 1.0

    x = torch.randn(2, 4, 8, 8)
    out = conv(x)
    assert out.shape == (2, 4, 8, 8)


def test_residual_conv_block_with_hex_mask():
    block = ResidualConvBlock(channels=16, use_hex_mask=True)
    x = torch.randn(2, 16, 8, 8)
    out = block(x)
    assert out.shape == (2, 16, 8, 8)


def test_temporal_context_block():
    ctx = TemporalContextBlock(hidden_dim=32)
    step1_pooled = torch.randn(2, 32)
    h1 = ctx(step1_pooled, None)
    assert h1.shape == (2, 32)

    step2_pooled = torch.randn(2, 32)
    h2 = ctx(step2_pooled, h1)
    assert h2.shape == (2, 32)
    assert not torch.allclose(h1, h2)


def test_two_hot_asymmetric_zero_boost():
    # Test fine discrimination of micro-attrition near zero (e.g. 0.05 vs 0.10)
    micro1 = torch.tensor([[0.02]])
    micro2 = torch.tensor([[0.08]])
    dist1 = scalar_to_two_hot(micro1, support_size=30, asym_zero_boost=True, zero_power=0.75)
    dist2 = scalar_to_two_hot(micro2, support_size=30, asym_zero_boost=True, zero_power=0.75)
    assert dist1.shape == (1, 1, 61)
    assert dist2.shape == (1, 1, 61)
    # Distributions must be distinct and non-zero
    assert not torch.allclose(dist1, dist2, atol=1e-3)
    rec1 = support_to_scalar(torch.log(torch.clamp(dist1, min=1e-8)), support_size=30, asym_zero_boost=True, zero_power=0.75)
    assert torch.isclose(rec1, micro1, atol=0.08)


def test_katago_final_ownership_head():
    from agents.efficientzero_v2.core.network_base import EfficientZeroV2BaseNetwork
    net = EfficientZeroV2BaseNetwork(
        observation_dim=32 * 16 * 16,
        hidden_dim=32,
        action_dim=10,
        encoder_type="cnn",
        observation_channels=32,
        observation_height=16,
        observation_width=16,
        enable_final_ownership_head=True,
    )
    assert net.prediction_final_ownership is not None
    obs = torch.randn(2, 32, 16, 16)
    hidden, policy_logits, value, reward, aux = net.initial_inference(obs, return_aux=True)
    assert "final_ownership_pred" in aux
    ownership = aux["final_ownership_pred"]
    # Final ownership map is 1 x H x W (KataGo)
    assert ownership.shape == (2, 1, 16, 16)

