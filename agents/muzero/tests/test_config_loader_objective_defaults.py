from pathlib import Path

from agents.muzero.configs.config_loader import load_muzero_config


def test_config_loader_injects_objective_defaults_for_legacy_configs(tmp_path: Path) -> None:
    cfg_path = tmp_path / "legacy.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "paths:",
                "  run_root: runs",
                "  voec_config: voec_sim/configs/voec_config.yaml",
                "scenario:",
                "  id: s1",
                "  seed: 1",
                "model:",
                "  observation_dim: 4",
                "  hidden_dim: 8",
                "  action_dim: 4",
                "  learning_rate: 0.001",
                "selfplay:",
                "  max_steps: 10",
                "  mcts_simulations: 4",
                "  mcts_c_puct: 1.5",
                "train:",
                "  iterations: 1",
                "  episodes_per_iter: 1",
                "  batch_size: 2",
                "  replay_capacity: 8",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_muzero_config(cfg_path)
    assert cfg.train["objective_signal"]["opportunity_near_vp_max_dist"] == 2.0
    assert cfg.train["objective_head"]["progress_positive_threshold"] == 0.0
    assert cfg.train["objective_reporting"]["high_confidence_prob_threshold"] == 0.60


def test_config_loader_preserves_explicit_objective_overrides(tmp_path: Path) -> None:
    cfg_path = tmp_path / "override.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "paths:",
                "  run_root: runs",
                "  voec_config: voec_sim/configs/voec_config.yaml",
                "scenario:",
                "  id: s1",
                "  seed: 1",
                "model:",
                "  observation_dim: 4",
                "  hidden_dim: 8",
                "  action_dim: 4",
                "  learning_rate: 0.001",
                "selfplay:",
                "  max_steps: 10",
                "  mcts_simulations: 4",
                "  mcts_c_puct: 1.5",
                "train:",
                "  iterations: 1",
                "  episodes_per_iter: 1",
                "  batch_size: 2",
                "  replay_capacity: 8",
                "  objective_signal:",
                "    opportunity_near_vp_max_dist: 3.5",
                "  objective_head:",
                "    progress_positive_threshold: 0.25",
                "  objective_reporting:",
                "    near_vp_max_dist: 3.5",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_muzero_config(cfg_path)
    assert cfg.train["objective_signal"]["opportunity_near_vp_max_dist"] == 3.5
    assert cfg.train["objective_head"]["progress_positive_threshold"] == 0.25
    assert cfg.train["objective_reporting"]["near_vp_max_dist"] == 3.5


def test_config_loader_preserves_checkpoint_every_when_set(tmp_path: Path) -> None:
    cfg_path = tmp_path / "checkpoint.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "paths:",
                "  run_root: runs",
                "  voec_config: voec_sim/configs/voec_config.yaml",
                "scenario:",
                "  id: s1",
                "  seed: 1",
                "model:",
                "  observation_dim: 4",
                "  hidden_dim: 8",
                "  action_dim: 4",
                "  learning_rate: 0.001",
                "selfplay:",
                "  max_steps: 10",
                "  mcts_simulations: 4",
                "  mcts_c_puct: 1.5",
                "train:",
                "  iterations: 1",
                "  episodes_per_iter: 1",
                "  batch_size: 2",
                "  replay_capacity: 8",
                "  checkpoint_every: 5",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_muzero_config(cfg_path)
    assert cfg.train["checkpoint_every"] == 5
