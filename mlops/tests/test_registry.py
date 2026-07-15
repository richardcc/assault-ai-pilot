from pathlib import Path

from mlops.registry.default_registry import BaselineRandomAdapter, build_default_registry


def test_registry_contains_default_agents(tmp_path: Path) -> None:
    registry = build_default_registry(run_root=tmp_path)
    assert "muzero" in registry
    assert "baseline_random" in registry


def test_baseline_train_is_noop() -> None:
    adapter = BaselineRandomAdapter()
    out = adapter.train(config_path="", stage_name="stage_a", scenario_id="scenario")
    assert out.run_id == "baseline_random"
    assert out.checkpoint_path == ""
