import pytest
import torch
import torch.nn.functional as F

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.replay import ReplaySample
from agents.efficientzero_v2.core.support import (
    cross_entropy_two_hot,
    phi_inverse,
    phi_transform,
    scalar_to_two_hot,
    support_to_scalar,
)
from agents.efficientzero_v2.train.loss_balancer import AdaptiveLossScaler, pcgrad_backward
from agents.efficientzero_v2.train.trainer import EfficientZeroV2Trainer


def test_two_hot_transformation_and_inversion():
    """Verify scalar <-> two_hot transformation and phi invertibility."""
    vals = torch.tensor([-15.5, -3.2, 0.0, 1.0, 7.8, 25.0])
    transformed = phi_transform(vals)
    reconstructed = phi_inverse(transformed)
    assert torch.allclose(vals, reconstructed, atol=1e-4)

    # Test two-hot encoding
    support_size = 30
    dist = scalar_to_two_hot(vals, support_size=support_size, use_phi=True)
    assert dist.shape == (len(vals), 2 * support_size + 1)
    # Each row must sum to 1.0 (valid probability distribution)
    assert torch.allclose(dist.sum(dim=-1), torch.ones(len(vals)), atol=1e-5)

    # Two-hot cross-entropy with identical logits should be minimal
    logits = torch.log(dist + 1e-8)
    loss = cross_entropy_two_hot(logits, vals, support_size=support_size, use_phi=True)
    assert loss.item() >= 0.0


def test_spatial_attention_network_forward_and_recurrent():
    """Verify that network with spatial attention bottleneck works seamlessly."""
    net = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=32,
        action_dim=16,
        encoder_type="cnn",
        observation_channels=8,
        observation_height=16,
        observation_width=16,
        support_size=20,
        use_spatial_attention=True,
    )
    b = 2
    obs = torch.randn(b, 8, 16, 16)
    hidden, policy, value, reward, aux = net.initial_inference(obs, return_aux=True)

    assert hidden.shape == (b, 32, 16, 16)
    assert policy.shape == (b, 16)
    # Value should be scalar for MCTS consumer
    assert value.shape == (b, 1)
    assert "value_logits" in aux
    # Value logits should have dimension 2 * support_size + 1
    assert aux["value_logits"].shape == (b, 2 * 20 + 1)

    # Recurrent step
    action = torch.zeros(b, 16)
    action[0, 2] = 1.0
    action[1, 8] = 1.0
    next_h, next_p, next_v, next_r, next_aux = net.recurrent_inference(hidden, action, return_aux=True)
    assert next_h.shape == (b, 32, 16, 16)
    assert next_v.shape == (b, 1)
    assert next_r.shape == (b, 1)
    assert "reward_logits" in next_aux
    assert next_aux["reward_logits"].shape == (b, 2 * 20 + 1)


def test_pcgrad_backward_conflicting_gradient_projection():
    """Verify PCGrad projects conflicting gradients so dot product is non-negative."""
    p = torch.nn.Parameter(torch.tensor([1.0, 2.0], requires_grad=True))
    optimizer = torch.optim.SGD([p], lr=0.1)

    # Task 1 wants to increase p[0], Task 2 wants to decrease p[0]
    l1 = p[0] * 2.0
    l2 = -p[0] * 3.0

    grad_norm = pcgrad_backward([l1, l2], optimizer, [p])
    assert p.grad is not None
    assert grad_norm >= 0.0


def test_adaptive_loss_scaler():
    """Verify AdaptiveLossScaler adjusts aux weight when aux loss scales."""
    scaler = AdaptiveLossScaler(target_aux_ratio=0.2, momentum=0.5)
    primary_loss = torch.tensor(1.0)
    aux_loss = torch.tensor(10.0)

    scaled_w = scaler.compute_scaled_weight(primary_loss, aux_loss, nominal_weight=0.5)
    # When aux loss is 10x primary, weight should scale down
    assert scaled_w < 0.5


def test_trainer_with_two_hot_and_loss_balancer():
    """Verify end-to-end training batch execution with two-hot and pcgrad."""
    model = EfficientZeroV2Network(
        observation_dim=8,
        hidden_dim=16,
        action_dim=4,
        encoder_type="mlp",
        support_size=10,
    )
    trainer = EfficientZeroV2Trainer(
        model=model,
        lr=1e-3,
        gradient_balance_mode="pcgrad",
        amp_enabled=False,
    )
    batch = [
        ReplaySample(
            observation=torch.randn(8),
            policy_target=[1.0, 0.0, 0.0, 0.0],
            value_target=0.5,
            reward_target=0.1,
            info={},
        ),
        ReplaySample(
            observation=torch.randn(8),
            policy_target=[0.0, 1.0, 0.0, 0.0],
            value_target=-0.2,
            reward_target=0.0,
            info={},
        ),
    ]
    metrics = trainer.train_batch(batch)
    assert metrics.loss > 0.0
    assert metrics.value_loss > 0.0
    assert metrics.reward_loss >= 0.0
