from pathlib import Path

from agents.efficientzero_v2.core.interop import load_efficientzero_config


def test_ezv2_config_loader_injects_objective_and_reward_defaults(tmp_path: Path) -> None:
    cfg_path = tmp_path / "legacy_ezv2.yaml"
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
    cfg = load_efficientzero_config(cfg_path)
    assert cfg.train["objective_signal"]["opportunity_near_vp_max_dist"] == 2.5
    assert cfg.train["objective_head"]["progress_positive_threshold"] == 0.0
    assert cfg.train["objective_reporting"]["conversion_window_steps_after_progress"] == 2
    assert cfg.selfplay["reward_shaping"]["capture_bonus"] == 0.62


def test_ezv2_config_loader_preserves_explicit_overrides(tmp_path: Path) -> None:
    cfg_path = tmp_path / "override_ezv2.yaml"
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
                "  reward_shaping:",
                "    capture_bonus: 0.77",
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
                "    conversion_window_steps_after_progress: 5",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_efficientzero_config(cfg_path)
    assert cfg.train["objective_signal"]["opportunity_near_vp_max_dist"] == 3.5
    assert cfg.train["objective_head"]["progress_positive_threshold"] == 0.25
    assert cfg.train["objective_reporting"]["conversion_window_steps_after_progress"] == 5
    assert cfg.selfplay["reward_shaping"]["capture_bonus"] == 0.77
