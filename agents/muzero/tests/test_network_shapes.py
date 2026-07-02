import pytest

torch = pytest.importorskip("torch")

from agents.muzero.core.network import MuZeroNetwork


def test_initial_inference_shapes():
    model = MuZeroNetwork(observation_dim=4, hidden_dim=16, action_dim=8)
    obs = torch.randn(3, 4)
    hidden, policy, value, reward = model.initial_inference(obs)
    assert hidden.shape == (3, 16)
    assert policy.shape == (3, 8)
    assert value.shape == (3, 1)
    assert reward.shape == (3, 1)


def test_initial_inference_aux_objective_shape():
    model = MuZeroNetwork(observation_dim=4, hidden_dim=16, action_dim=8)
    obs = torch.randn(2, 4)
    hidden, policy, value, reward, aux = model.initial_inference(obs, return_aux=True)
    assert hidden.shape == (2, 16)
    assert policy.shape == (2, 8)
    assert value.shape == (2, 1)
    assert reward.shape == (2, 1)
    assert isinstance(aux, dict)
    assert "objective_logit" in aux
    assert aux["objective_logit"].shape == (2, 1)
