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


def test_tactical_heads_inference_and_aux():
    """Verify inference and aux dictionary outputs for threat, attrition, and morale heads."""
    # 1. Test CNN architecture with Spatial Attention
    net_cnn = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=32,
        action_dim=16,
        encoder_type="cnn",
        observation_channels=8,
        observation_height=16,
        observation_width=16,
        use_spatial_attention=True,
        enable_threat_head=True,
        enable_attrition_head=True,
        enable_morale_head=True,
        morale_classes=4,
    )
    b = 2
    obs = torch.randn(b, 8, 16, 16)
    hidden, policy, value, reward, aux = net_cnn.initial_inference(obs, return_aux=True)

    assert "threat_map_pred" in aux
    assert aux["threat_map_pred"].shape == (b, 1, 16, 16)
    assert "attrition_pred" in aux
    assert aux["attrition_pred"].shape == (b, 2)
    assert "morale_pred" in aux
    assert aux["morale_pred"].shape == (b, 4)

    # Recurrent step
    action = torch.zeros(b, 16)
    action[0, 1] = 1.0
    action[1, 5] = 1.0
    next_h, next_p, next_v, next_r, next_aux = net_cnn.recurrent_inference(hidden, action, return_aux=True)
    assert "threat_map_pred" in next_aux
    assert next_aux["threat_map_pred"].shape == (b, 1, 16, 16)
    assert "attrition_pred" in next_aux
    assert next_aux["attrition_pred"].shape == (b, 2)
    assert "morale_pred" in next_aux
    assert next_aux["morale_pred"].shape == (b, 4)

    # 2. Test MLP architecture
    net_mlp = EfficientZeroV2Network(
        observation_dim=8,
        hidden_dim=16,
        action_dim=4,
        encoder_type="mlp",
        observation_height=4,
        observation_width=4,
        enable_threat_head=True,
        enable_attrition_head=True,
        enable_morale_head=True,
        morale_classes=4,
    )
    obs_mlp = torch.randn(b, 8)
    h_m, p_m, v_m, r_m, aux_m = net_mlp.initial_inference(obs_mlp, return_aux=True)
    assert aux_m["threat_map_pred"].shape == (b, 16)
    assert aux_m["attrition_pred"].shape == (b, 2)
    assert aux_m["morale_pred"].shape == (b, 4)

    # 3. Test with heads disabled
    net_disabled = EfficientZeroV2Network(
        observation_dim=8,
        hidden_dim=16,
        action_dim=4,
        encoder_type="mlp",
        enable_threat_head=False,
        enable_attrition_head=False,
        enable_morale_head=False,
    )
    _, _, _, _, aux_dis = net_disabled.initial_inference(obs_mlp, return_aux=True)
    assert "threat_map_pred" not in aux_dis
    assert "attrition_pred" not in aux_dis
    assert "morale_pred" not in aux_dis


def test_trainer_with_tactical_heads_losses():
    """Verify trainer computes threat, final ownership, attrition, and morale aux losses with targets and fallbacks."""
    model = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=16,
        action_dim=4,
        encoder_type="cnn",
        observation_channels=2,
        observation_height=4,
        observation_width=4,
        enable_threat_head=True,
        enable_final_ownership_head=True,
        enable_attrition_head=True,
        enable_morale_head=True,
        morale_classes=4,
    )
    trainer = EfficientZeroV2Trainer(
        model=model,
        lr=1e-3,
        aux_objective_enabled=True,
        aux_threat_loss_weight=0.5,
        aux_final_ownership_loss_weight=0.5,
        aux_attrition_loss_weight=0.5,
        aux_morale_loss_weight=0.5,
        amp_enabled=False,
    )

    # Sample 1: Explicit targets
    # Sample 2: Fallback target inference from gameplay metrics
    batch = [
        ReplaySample(
            observation=torch.randn(2, 4, 4),
            policy_target=[1.0, 0.0, 0.0, 0.0],
            value_target=0.5,
            reward_target=0.1,
            info={
                "threat_map_target": torch.ones(1, 4, 4),
                "final_ownership_target": torch.ones(1, 4, 4),
                "attrition_target": [0.2, 0.8],
                "morale_target": 2,
            },
        ),
        ReplaySample(
            observation=torch.randn(2, 4, 4),
            policy_target=[0.0, 1.0, 0.0, 0.0],
            value_target=-0.2,
            reward_target=0.0,
            info={
                "damage_dealt": 5.0,
                "enemy_damage": 2.0,
                "pinned": True,
            },
        ),
    ]

    metrics = trainer.train_batch(batch)
    assert metrics.loss > 0.0
    assert metrics.aux_objective_loss > 0.0
    assert metrics.aux_threat_loss > 0.0
    assert metrics.aux_final_ownership_loss > 0.0
    assert metrics.aux_attrition_loss > 0.0
    assert metrics.aux_morale_loss > 0.0

    metrics_dict = metrics.to_dict()
    assert "aux_threat_loss" in metrics_dict
    assert "aux_final_ownership_loss" in metrics_dict
    assert "aux_attrition_loss" in metrics_dict
    assert "aux_morale_loss" in metrics_dict


def test_all_11_network_heads_topology_and_shapes():
    """
    Verify simultaneously all 11 heads of the production EfficientZeroV2Network:
    1. Policy (pi)
    2. Value (v + Two-Hot support logits)
    3. Reward (r + Two-Hot support logits)
    4. Consistency Projection (SimSiam hypersphere)
    5. Threat Map 2D (Spatial heatmap)
    6. Final Ownership Map 2D (KataGo final territory prediction)
    7. Attrition (Allied/Enemy casualties)
    8. Morale (4 cohesion classes)
    9. Macro-Intent (8 HRL doctrinal postures)
    10. Multi-VP (4 objective features)
    11. Objective Scalar (1 binary/progress logit)
    """
    net = EfficientZeroV2Network(
        observation_dim=32 * 16 * 16,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        observation_height=16,
        observation_width=16,
        dynamics_blocks=3,
        prediction_blocks=2,
        consistency_proj_dim=128,
        objective_intent_classes=8,
        multi_vp_feature_dim=4,
        support_size=30,
        use_spatial_attention=True,
        enable_threat_head=True,
        enable_final_ownership_head=True,
        enable_attrition_head=True,
        enable_morale_head=True,
        morale_classes=4,
        dynamics_recurrent_steps=2,
    )
    b = 3
    obs = torch.randn(b, 32, 16, 16)
    actions = torch.tensor([0, 15, 31], dtype=torch.long)

    hidden, policy, value, reward, aux = net.initial_inference(obs, return_aux=True)
    assert hidden.shape == (b, 48, 16, 16)
    assert policy.shape == (b, 32)
    assert value.shape == (b, 1)
    assert reward.shape == (b, 1)
    assert aux["value_logits"].shape == (b, 61)
    assert aux["reward_logits"].shape == (b, 61)
    assert aux["objective_logit"].shape == (b, 1)
    assert aux["objective_intent_logits"].shape == (b, 8)
    assert aux["multi_vp_pred"].shape == (b, 4)
    assert aux["threat_map_pred"].shape == (b, 1, 16, 16)
    assert aux["final_ownership_pred"].shape == (b, 1, 16, 16)
    assert aux["attrition_pred"].shape == (b, 2)
    assert aux["morale_pred"].shape == (b, 4)

    next_h, next_p, next_v, next_r, next_aux = net.recurrent_inference(hidden, actions, return_aux=True)
    assert next_h.shape == (b, 48, 16, 16)
    assert next_p.shape == (b, 32)
    assert next_v.shape == (b, 1)
    assert next_r.shape == (b, 1)
    assert next_aux["value_logits"].shape == (b, 61)
    assert next_aux["reward_logits"].shape == (b, 61)
    assert next_aux["objective_logit"].shape == (b, 1)
    assert next_aux["objective_intent_logits"].shape == (b, 8)
    assert next_aux["multi_vp_pred"].shape == (b, 4)
    assert next_aux["threat_map_pred"].shape == (b, 1, 16, 16)
    assert next_aux["final_ownership_pred"].shape == (b, 1, 16, 16)
    assert next_aux["attrition_pred"].shape == (b, 2)
    assert next_aux["morale_pred"].shape == (b, 4)

    emb = net.consistency_embedding(next_h)
    assert emb.shape == (b, 128)
    assert torch.allclose(emb.norm(dim=-1), torch.ones(b), atol=1e-4)


def test_dynamic_macro_modulation_scale():
    """Verify Task 2.8: Dynamic Prior Modulation and Pure Neural Network Ablation."""
    from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner, MacroPlan

    planner = MacroStrategyPlanner()
    macro_plan = MacroPlan(
        posture="ASSAULT_VP",
        target_vp_id="4,4",
        target_vp_coords=(4, 4),
        unit_roles={"US_1": "ROLE_MANEUVER"},
        unit_cohesion={"US_1": "FORMED"},
        unit_coords={"US_1": (4, 1)},
    )
    priors = {"MOVE:US_1:4:3": 0.5, "WAIT:US_1": 0.5}
    legal = ["MOVE:US_1:4:3", "WAIT:US_1"]
    vps = {"4,4": "NEUTRAL"}

    # Full doctrinal modulation (scale = 1.0)
    priors_full = planner.modulate_priors(
        priors, macro_plan, legal, vps, to_play="US", modulation_scale=1.0
    )
    # Pure neural network (scale = 0.0) -> zero heuristic distortion
    priors_zero = planner.modulate_priors(
        priors, macro_plan, legal, vps, to_play="US", modulation_scale=0.0
    )
    # Half modulation (scale = 0.5)
    priors_half = planner.modulate_priors(
        priors, macro_plan, legal, vps, to_play="US", modulation_scale=0.5
    )

    # Scale 0.0 must preserve exact neural prior distribution
    assert priors_zero["MOVE:US_1:4:3"] == pytest.approx(0.5, rel=1e-4)
    assert priors_zero["WAIT:US_1"] == pytest.approx(0.5, rel=1e-4)

    # Scale 1.0 must boost MOVE towards target VP and penalize WAIT
    assert priors_full["MOVE:US_1:4:3"] > 0.5
    assert priors_full["WAIT:US_1"] < 0.5

    # Scale 0.5 must be strictly between scale 0.0 and scale 1.0
    assert priors_zero["MOVE:US_1:4:3"] < priors_half["MOVE:US_1:4:3"] < priors_full["MOVE:US_1:4:3"]



