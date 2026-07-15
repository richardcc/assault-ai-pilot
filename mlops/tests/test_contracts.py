from pathlib import Path

from mlops.config_loader import load_experiment_config
from mlops.curriculum.io import load_curriculum_spec


def test_load_curriculum_spec(tmp_path: Path) -> None:
    path = tmp_path / "curriculum.yaml"
    path.write_text(
        """
stages:
  - name: stage_a
    scenario_id: s1
    seeds: [1, 2, 3]
    train_iterations: 2
    eval_episodes: 3
""".strip(),
        encoding="utf-8",
    )
    spec = load_curriculum_spec(path)
    assert len(spec.stages) == 1
    assert spec.stages[0].name == "stage_a"
    assert spec.stages[0].seeds == [1, 2, 3]


def test_load_experiment_config(tmp_path: Path) -> None:
    curriculum = tmp_path / "curriculum.yaml"
    curriculum.write_text("stages: []", encoding="utf-8")
    bench = tmp_path / "bench.yaml"
    bench.write_text("benchmark: {}", encoding="utf-8")
    muzero = tmp_path / "muzero.yaml"
    muzero.write_text("model: {}", encoding="utf-8")
    cfg_path = tmp_path / "experiment.yaml"
    cfg_path.write_text(
        f"""
experiment_name: smoke
paths:
  run_root: runs
  curriculum_config: {curriculum.name}
  benchmark_config: {bench.name}
  muzero_config: {muzero.name}
""".strip(),
        encoding="utf-8",
    )
    cfg = load_experiment_config(cfg_path)
    assert cfg.experiment_name == "smoke"
    assert cfg.paths.curriculum_config.name == curriculum.name
