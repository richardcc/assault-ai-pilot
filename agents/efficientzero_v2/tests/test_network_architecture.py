import pytest
import torch

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.network_base import EfficientZeroV2BaseNetwork


def test_cnn_network_parameters_lightweight():
    """Verify that CNN network avoids the 302M parameter dense merge bottleneck."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        observation_height=16,
        observation_width=16,
        dynamics_blocks=3,
        prediction_blocks=2,
    )
    total_params = sum(p.numel() for p in net.parameters())
    # Should be under 5M parameters, down from 305M
    assert total_params < 5_000_000, f"Expected < 5M params, got {total_params:,}"
    # Verify dynamics_merge is a Conv2d rather than a 300M Linear layer
    assert isinstance(net.dynamics_merge[0], torch.nn.Conv2d)


def test_cnn_forward_and_recurrent_inference_shapes():
    """Verify forward and recurrent inferences with different action shapes."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        observation_height=16,
        observation_width=16,
        dynamics_blocks=2,
        prediction_blocks=2,
    )
    b, c, h, w = 3, 32, 16, 16
    obs = torch.randn(b, c, h, w)

    # 1. Initial inference
    hidden, policy, value, reward, aux = net.initial_inference(obs, return_aux=True)
    assert hidden.shape == (b, 48, h, w)
    assert policy.shape == (b, 32)
    assert value.shape == (b, 1)
    assert reward.shape == (b, 1)
    assert "objective_logit" in aux

    # 2. Recurrent inference with 2D one-hot tensor
    action_onehot = torch.zeros(b, 32)
    action_onehot[0, 5] = 1.0
    action_onehot[1, 12] = 1.0
    action_onehot[2, 31] = 1.0
    next_hidden, next_pol, next_val, next_rew, next_aux = net.recurrent_inference(
        hidden, action_onehot, return_aux=True
    )
    assert next_hidden.shape == (b, 48, h, w)
    assert next_pol.shape == (b, 32)
    assert next_val.shape == (b, 1)
    assert next_rew.shape == (b, 1)

    # 3. Recurrent inference with 1D index tensor
    action_idx = torch.tensor([5, 12, 31], dtype=torch.long)
    next_h2, next_p2, next_v2, next_r2 = net.recurrent_inference(hidden, action_idx)
    assert next_h2.shape == (b, 48, h, w)
    assert next_p2.shape == (b, 32)

    # 4. Consistency embedding
    z = net.consistency_embedding(next_hidden)
    assert z.shape == (b, net.consistency_proj_dim)
    # L2 normalized
    norms = torch.norm(z, dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)


def test_cnn_gradient_flow():
    """Verify gradients propagate end-to-end through representation and dynamics."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=32,
        action_dim=16,
        encoder_type="cnn",
        observation_channels=8,
        observation_height=8,
        observation_width=8,
    )
    obs = torch.randn(2, 8, 8, 8, requires_grad=True)
    hidden, policy, value, _ = net.initial_inference(obs)
    action = torch.zeros(2, 16)
    action[0, 1] = 1.0
    action[1, 3] = 1.0

    next_hidden, next_policy, next_value, reward = net.recurrent_inference(hidden, action)
    loss = next_policy.sum() + next_value.sum() + reward.sum()
    loss.backward()

    # Verify input received gradients
    assert obs.grad is not None
    assert obs.grad.abs().sum() > 0.0
    # Verify dynamics merge received gradients
    assert net.dynamics_merge[0].weight.grad is not None
    assert net.dynamics_merge[0].weight.grad.abs().sum() > 0.0


def test_mlp_backward_compatibility():
    """Verify MLP encoder mode continues to function properly."""
    net = EfficientZeroV2Network(
        observation_dim=20,
        hidden_dim=32,
        action_dim=10,
        encoder_type="mlp",
    )
    obs = torch.randn(2, 20)
    hidden, policy, value, _ = net.initial_inference(obs)
    assert hidden.shape == (2, 32)
    assert policy.shape == (2, 10)

    action = torch.zeros(2, 10)
    action[0, 2] = 1.0
    action[1, 7] = 1.0
    next_hidden, next_pol, next_val, next_rew = net.recurrent_inference(hidden, action)
    assert next_hidden.shape == (2, 32)
    assert next_pol.shape == (2, 10)
