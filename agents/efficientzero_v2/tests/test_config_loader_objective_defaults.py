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
    assert cfg.train["objective_signal"]["opportunity_near_vp_max_dist"] == 3
    assert cfg.train["objective_opportunity_max_dist"] == 3
    assert cfg.train["objective_head"]["progress_positive_threshold"] == 0.0
    assert cfg.train["objective_reporting"]["conversion_window_steps_after_progress"] == 2
    assert cfg.selfplay["reward_shaping"]["capture_bonus"] == 0.70
    assert cfg.selfplay["reward_shaping"]["objective_progress_bonus_per_hex"] == 0.95
    assert cfg.selfplay["reward_shaping"]["objective_team_progress_bonus_per_hex"] == 0.60
    assert cfg.selfplay["reward_shaping"]["objective_progress_cap_abs"] == 1.0
    assert cfg.selfplay["reward_shaping"]["objective_team_progress_cap_abs"] == 1.5
    assert cfg.selfplay["reward_shaping"]["objective_no_progress_penalty"] == 0.46
    assert cfg.selfplay["reward_shaping"]["reaction_fire_soft_signal_enabled"] is True
    assert cfg.selfplay["reward_shaping"]["reaction_fire_soft_signal_weight"] == 0.04
    assert cfg.selfplay["reward_shaping"]["reaction_fire_soft_signal_expected_damage_scale"] == 4.0
    assert cfg.selfplay["reward_shaping"]["global_strategy_soft_enabled"] is True
    assert cfg.selfplay["reward_shaping"]["global_strategy_vp_control_net_gain_weight"] == 0.08
    assert cfg.selfplay["reward_shaping"]["global_strategy_units_in_vp_ring_weight"] == 0.04
    assert cfg.selfplay["reward_shaping"]["global_strategy_enemy_vp_threat_reduced_weight"] == 0.05
    assert cfg.selfplay["reward_shaping"]["global_strategy_sustained_vp_advantage_weight"] == 0.02
    assert cfg.selfplay["reward_shaping"]["global_strategy_role_consistency_weight"] == 0.03
    assert cfg.selfplay["reward_shaping"]["global_strategy_setup_convert_weight"] == 0.03
    assert cfg.selfplay["reward_shaping"]["global_strategy_vp_ring_radius"] == 2
    assert cfg.selfplay["reward_shaping"]["global_strategy_enemy_threat_radius"] == 3
    assert cfg.selfplay["reward_shaping"]["global_strategy_sustained_advantage_min_turns"] == 2
    assert cfg.selfplay["reward_shaping"]["global_strategy_total_cap_abs"] == 0.15
    assert cfg.selfplay["reward_shaping"]["vp_horizon_soft_enabled"] is True
    assert cfg.selfplay["reward_shaping"]["vp_horizon_soft_weight"] == 0.02
    assert cfg.selfplay["reward_shaping"]["vp_horizon_soft_cap_steps"] == 8.0
    assert cfg.selfplay["reward_shaping"]["enemy_threat_component_enabled"] is False
    assert cfg.selfplay["reward_shaping"]["enemy_threat_component_weight"] == 0.01
    assert cfg.selfplay["reward_shaping"]["enemy_threat_component_horizon_steps"] == 6.0
    assert cfg.selfplay["reward_shaping"]["enemy_threat_component_cap_abs"] == 0.03
    assert cfg.selfplay["reward_shaping"]["enemy_threat_component_immediate_capture_bonus"] == 0.40
    assert cfg.selfplay["reward_shaping"]["mobility_opportunity_cost_component_enabled"] is False
    assert cfg.selfplay["reward_shaping"]["mobility_opportunity_cost_component_weight"] == 0.01
    assert cfg.selfplay["reward_shaping"]["mobility_opportunity_cost_component_cap_abs"] == 0.02
    assert cfg.selfplay["reward_shaping"]["cross_unit_synergy_component_enabled"] is False
    assert cfg.selfplay["reward_shaping"]["cross_unit_synergy_component_weight"] == 0.01
    assert cfg.selfplay["reward_shaping"]["cross_unit_synergy_component_cap_abs"] == 0.02
    assert cfg.selfplay["reward_shaping"]["obs_enemy_vp_threat_radius"] == 6
    assert cfg.selfplay["reward_shaping"]["obs_vp_ownership_ttl_cap"] == 8
    assert cfg.selfplay["mcts_q_clip_abs"] == 20.0
    assert cfg.selfplay["mcts_q_root_normalization_mode"] == "adaptive_minmax"
    assert cfg.selfplay["mcts_q_root_normalization_strength"] == 0.40
    assert cfg.selfplay["mcts_vp_tiebreak_epsilon"] == 0.02
    assert cfg.selfplay["mcts_q_flat_spread_epsilon"] == 1.0e-6
    assert cfg.selfplay["mcts_vp_flat_q_score_epsilon"] == 0.02
    assert cfg.selfplay["mcts_vp_flat_q_min_progress"] == 0.0
    assert cfg.selfplay["mcts_chance_mode"] == "off"
    assert cfg.selfplay["mcts_chance_samples_per_expansion"] == 1
    assert cfg.selfplay["mcts_chance_value_noise_std"] == 0.0
    assert cfg.selfplay["mcts_success_prob_enabled"] is False
    assert cfg.selfplay["mcts_success_prob_alpha"] == 0.0
    assert cfg.selfplay["mcts_success_prob_center"] == 0.5
    assert cfg.selfplay["mcts_success_prob_scale"] == 0.5
    assert cfg.selfplay["mcts_success_prob_centered_clip_abs"] == 1.0
    assert cfg.selfplay["mcts_success_prob_expected_damage_scale"] == 4.0
    assert cfg.train["objective_pos_weight"] == 6.8


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
                "    global_strategy_vp_control_net_gain_weight: 0.11",
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
    assert cfg.selfplay["reward_shaping"]["global_strategy_vp_control_net_gain_weight"] == 0.11
