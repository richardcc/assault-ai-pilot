import pytest

pytest.importorskip("torch")

from agents.muzero.train.train_muzero import run_training


def test_train_smoke_runs():
    result = run_training(config_path="agents/muzero/configs/muzero_config.test.yaml")
    assert "run_id" in result
    assert "metrics" in result
    assert "phase_2_9_train_kpis" in result["metrics"]
    assert "reaction_fire_count" in result["metrics"]["phase_2_9_train_kpis"]
    assert "assault_quality" in result["metrics"]["phase_2_9_train_kpis"]
