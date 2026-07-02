import pytest

torch = pytest.importorskip("torch")

from agents.muzero.core.network import MuZeroNetwork
from agents.muzero.core.replay import ReplaySample
from agents.muzero.train.trainer import MuZeroTrainer


def _make_sample(progress_delta: float, has_opportunity: int, converted: int = 0) -> ReplaySample:
    return ReplaySample(
        observation=torch.randn(4),
        policy_target=[1.0, 0.0, 0.0, 0.0],
        value_target=0.0,
        reward_target=0.0,
        info={
            "objective_converted": int(converted),
            "objective_progress_delta": float(progress_delta),
            "objective_had_opportunity": int(has_opportunity),
        },
    )


def test_trainer_reports_objective_loss_when_enabled():
    model = MuZeroNetwork(observation_dim=4, hidden_dim=16, action_dim=4)
    trainer = MuZeroTrainer(model=model, lr=1e-3, objective_loss_weight=1.0)
    batch = [_make_sample(1.0, 1), _make_sample(0.0, 1), _make_sample(0.0, 0)]
    metrics = trainer.train_batch(batch).to_dict()
    assert "objective_loss" in metrics
    assert metrics["objective_loss"] > 0.0


def test_trainer_objective_loss_zero_when_disabled():
    model = MuZeroNetwork(observation_dim=4, hidden_dim=16, action_dim=4)
    trainer = MuZeroTrainer(model=model, lr=1e-3, objective_loss_weight=0.0)
    batch = [_make_sample(1.0, 1), _make_sample(0.0, 1)]
    metrics = trainer.train_batch(batch).to_dict()
    assert metrics["objective_loss"] == 0.0
