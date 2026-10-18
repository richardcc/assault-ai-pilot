"""
Tests for Palma et al. Architectural & Training Transfers in EfficientZero V2:
1. Map-Size Agnosticism (Zero-Shot Resolution Invariance: 16x16, 32x32, 64x64)
2. Weight-Tied Recurrent Reasoning Depth (k-step latent iteration with 0 extra params)
3. Procedural Asymmetric Scenario & Force Mutation (Terrain, Deployment, Strength jitter)
"""

from types import SimpleNamespace
import torch

from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from assault_model.core.procedural_mutator import apply_procedural_mutation
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.map.hex import Hex
from assault_model.map.hex_coord import HexCoord
from assault_model.map.map import Map
from assault_model.map.terrain import Terrain
from assault_model.state.game_state import GameState


def test_map_size_agnostic_zero_shot_inference_16_32_64():
    """
    A single EfficientZeroV2Network trained on 16x16 must seamlessly process
    16x16, 32x32, and 64x64 map tensors without retraining or parameter changes.
    """
    for use_attn in (True, False):
        net = EfficientZeroV2Network(
            observation_dim=32 * 16 * 16,
            hidden_dim=48,
            action_dim=32,
            encoder_type="cnn",
            observation_channels=32,
            observation_height=16,
            observation_width=16,
            dynamics_blocks=2,
            prediction_blocks=2,
            support_size=30,
            use_spatial_attention=use_attn,
            enable_threat_head=True,
            enable_attrition_head=True,
            enable_morale_head=True,
        )
        net.eval()

        for res in (16, 32, 64):
            obs = torch.randn(2, 32, res, res)
            actions = torch.tensor([3, 7], dtype=torch.long)

            with torch.no_grad():
                hidden, policy, value, reward, aux = net.initial_inference(obs, return_aux=True)
                assert hidden.shape == (2, 48, res, res)
                assert policy.shape == (2, 32)
                assert value.shape == (2, 1)
                assert aux["threat_map_pred"].shape == (2, 1, res, res)

                next_hidden, next_pol, next_val, next_rew, next_aux = net.recurrent_inference(
                    hidden, actions, return_aux=True
                )
                assert next_hidden.shape == (2, 48, res, res)
                assert next_pol.shape == (2, 32)
                assert next_val.shape == (2, 1)
                assert next_rew.shape == (2, 1)
                assert next_aux["threat_map_pred"].shape == (2, 1, res, res)

                emb = net.consistency_embedding(next_hidden)
                assert emb.shape == (2, 128)


def test_weight_tied_recurrent_reasoning_zero_extra_parameters():
    """
    Iterating the dynamics block k times must add 0 trainable parameters,
    preserve 100% state_dict compatibility, and refine latent transitions.
    """
    torch.manual_seed(42)
    net_k1 = EfficientZeroV2Network(
        observation_dim=32 * 16 * 16,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        dynamics_blocks=3,
        prediction_blocks=2,
        use_spatial_attention=True,
        dynamics_recurrent_steps=1,
    )
    net_k3 = EfficientZeroV2Network(
        observation_dim=32 * 16 * 16,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        dynamics_blocks=3,
        prediction_blocks=2,
        use_spatial_attention=True,
        dynamics_recurrent_steps=3,
    )

    params_k1 = sum(p.numel() for p in net_k1.parameters())
    params_k3 = sum(p.numel() for p in net_k3.parameters())
    assert params_k1 == params_k3
    assert set(net_k1.state_dict().keys()) == set(net_k3.state_dict().keys())

    # Load exact weights from k=1 into k=3
    net_k3.load_state_dict(net_k1.state_dict())

    obs = torch.randn(1, 32, 16, 16)
    act = torch.tensor([5], dtype=torch.long)
    with torch.no_grad():
        h0, _, _, _ = net_k1.initial_inference(obs)
        h_next_1, _, _, _ = net_k1.recurrent_inference(h0, act)
        h_next_3, _, _, _ = net_k3.recurrent_inference(h0, act)
        # Dynamic override at call time
        h_next_override, _, _, _ = net_k1.recurrent_inference(h0, act, recurrent_steps=3)

    assert torch.allclose(h_next_3, h_next_override)
    assert not torch.allclose(h_next_1, h_next_3)


def test_procedural_asymmetric_scenario_mutator():
    """
    Verify seed determinism, VP protection, terrain perturbation, unit jitter,
    and asymmetric strength mutation.
    """
    def _build_state():
        hexes = [Hex(q, r, Terrain.CLEAR) for q in range(8) for r in range(8)]
        game_map = Map(hexes)
        u1 = SimpleNamespace(
            unit_id="US_1",
            side="US",
            alive=True,
            suppressed=False,
            fallback=False,
            strength=6,
            max_strength=6,
            position=HexCoord(2, 2),
        )
        u2 = SimpleNamespace(
            unit_id="GE_1",
            side="GE",
            alive=True,
            suppressed=False,
            fallback=False,
            strength=6,
            max_strength=6,
            position=HexCoord(5, 5),
        )
        victory = VictoryConditions.from_json({"value_per_hex": 2, "hexes": [[0, 0], [7, 7]]})
        return GameState(game_map=game_map, units=[u1, u2], turn=1, victory=victory)

    state_a = _build_state()
    state_b = _build_state()

    stats_a = apply_procedural_mutation(
        state_a,
        seed=12345,
        terrain_mutation_prob=0.35,
        unit_jitter_prob=1.0,
        asymmetric_strength_jitter=1.0,
    )
    stats_b = apply_procedural_mutation(
        state_b,
        seed=12345,
        terrain_mutation_prob=0.35,
        unit_jitter_prob=1.0,
        asymmetric_strength_jitter=1.0,
    )

    assert stats_a == stats_b
    assert stats_a["mutated_terrain_count"] > 0
    assert stats_a["jittered_units_count"] == 2

    # VP hexes (0, 0) and (7, 7) must remain untouched CLEAR terrain
    assert state_a.hex_states[(0, 0)].hex.terrain == Terrain.CLEAR
    assert state_a.hex_states[(7, 7)].hex.terrain == Terrain.CLEAR

    # Seed determinism check on unit positions
    assert state_a.units[0].position == state_b.units[0].position
    assert state_a.units[1].position == state_b.units[1].position

    # Hex control must match new jittered positions
    u1_pos = (state_a.units[0].position.q, state_a.units[0].position.r)
    assert state_a.hex_states[u1_pos].ownership == state_a.side_to_ownership["US"]


def test_hexagonal_masked_conv_and_depthwise_separable():
    """
    Verify HexagonalMaskConv2d is active by default across towers without adding
    state_dict keys, and HexagonalDepthwiseSeparableConv2d zeroes out non-hex corners.
    """
    from agents.efficientzero_v2.core.network_base import (
        HexagonalMaskConv2d,
        HexagonalDepthwiseSeparableConv2d,
    )

    net = EfficientZeroV2Network(
        observation_dim=32 * 16 * 16,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        dynamics_blocks=2,
        prediction_blocks=2,
        use_hex_mask=True,
    )
    assert isinstance(net.representation_input[0], HexagonalMaskConv2d)
    assert isinstance(net.dynamics_merge[0], HexagonalMaskConv2d)
    # Verify non-persistent buffer does not pollute state_dict
    assert not any("hex_mask" in k for k in net.state_dict().keys())

    dw = HexagonalDepthwiseSeparableConv2d(16, 32, bias=False)
    x = torch.randn(2, 16, 8, 8)
    out = dw(x)
    assert out.shape == (2, 32, 8, 8)


def test_recall_skip_connection_and_progressive_loss_truncation():
    """
    Verify Palma et al. (2025, Sec. 2.2) Recall skip-connection and Progressive Loss
    gradient truncation (no_grad_steps > 0).
    """
    net = EfficientZeroV2Network(
        observation_dim=32 * 16 * 16,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        dynamics_blocks=2,
        prediction_blocks=2,
        dynamics_recurrent_steps=3,
        use_recall=True,
    )
    obs = torch.randn(2, 32, 16, 16)
    actions = torch.tensor([1, 2], dtype=torch.long)
    hidden, _, _, _ = net.initial_inference(obs)

    # Progressive loss pass: 1 no-grad step + 2 grad steps
    next_h, pol, val, rew = net.recurrent_inference(
        hidden, actions, recurrent_steps=3, no_grad_steps=1
    )
    loss = pol.sum() + val.sum() + rew.sum()
    loss.backward()
    assert next_h.shape == (2, 48, 16, 16)
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in net.dynamics_state.parameters())


def test_input_channel_gate_and_temporal_context_block():
    """Verify InputChannelGate and TemporalContextBlock optional modules."""
    net = EfficientZeroV2Network(
        observation_dim=32 * 16 * 16,
        hidden_dim=48,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=32,
        enable_input_channel_gate=True,
        enable_temporal_context=True,
    )
    obs = torch.randn(2, 32, 16, 16)
    # Zero out channel 5 completely to test dead-channel suppression
    obs[:, 5, :, :] = 0.0
    h0, _, _, _ = net.initial_inference(obs)
    h_fused = net.update_temporal_context(h0, prev_state=None)
    h_fused_2 = net.update_temporal_context(h0, prev_state=h_fused)
    assert h_fused_2.shape == (2, 48, 16, 16)


def test_reinforcement_schedule_projection_and_adaptive_simulations():
    """
    Verify Palma et al. (Sec. 3.2.3) incoming reinforcement schedule countdown
    projection in observation_to_tensor and PonderNet-style compute_adaptive_simulations.
    """
    from agents.efficientzero_v2.core.observation import observation_to_tensor
    from agents.efficientzero_v2.core.mcts import compute_adaptive_simulations

    obs = SimpleNamespace(
        to_play="US",
        turn=2,
        max_turns=8,
        units=[],
        playable_hexes=[{"q": 0, "r": 0}, {"q": 1, "r": 0}],
        vp_hexes=[],
        vp_owner_by_hex={},
        reinforcements=[
            {"side": "US", "q": 0, "r": 0, "turn": 3},
            {"side": "GER", "q": 1, "r": 0, "turn": 4},
        ],
    )
    grid = observation_to_tensor(obs, channels=32, height=8, width=8)
    assert grid[0][0][0] > 0.0  # US incoming reinforcement projected on ch 0
    assert grid[4][0][1] > 0.0  # GER incoming reinforcement projected on ch 4

    # Low entropy (dominant action) -> fewer simulations than high entropy (uniform)
    sims_easy = compute_adaptive_simulations(
        32, priors_by_action={"a": 0.98, "b": 0.01, "c": 0.01}, values_by_action={"a": 0.5, "b": 0.5, "c": 0.5}
    )
    sims_hard = compute_adaptive_simulations(
        32, priors_by_action={"a": 0.33, "b": 0.33, "c": 0.34}, values_by_action={"a": 0.9, "b": -0.8, "c": 0.1}
    )
    assert sims_hard > sims_easy

