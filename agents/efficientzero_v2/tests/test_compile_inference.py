# -*- coding: utf-8 -*-
import torch
import pytest
from agents.efficientzero_v2.core.network import EfficientZeroV2Network


def test_compile_inference_api():
    model = EfficientZeroV2Network(
        observation_dim=16 * 16 * 38,
        hidden_dim=32,
        action_dim=32,
        encoder_type="cnn",
        observation_channels=38,
        observation_height=16,
        observation_width=16,
        dynamics_blocks=1,
        prediction_blocks=1,
    )
    # Ensure compile_inference returns model instance
    compiled_model = model.compile_inference(mode="default")
    assert compiled_model is model

    # Test eager/compiled forward pass
    obs = torch.zeros((1, 38, 16, 16), dtype=torch.float32)
    hidden, policy_logits, value, reward = compiled_model.initial_inference(obs)
    assert hidden.shape[0] == 1
    assert policy_logits.shape == (1, 32)
    assert value.shape == (1, 1)
