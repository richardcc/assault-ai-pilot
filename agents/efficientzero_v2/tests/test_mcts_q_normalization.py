from agents.efficientzero_v2.core.mcts import run_mcts_puct


def test_q_root_normalization_breaks_saturation_ties_in_extreme_case() -> None:
    legal = ["A", "B", "C"]
    priors = {"A": 1.0 / 3.0, "B": 1.0 / 3.0, "C": 1.0 / 3.0}
    values = {"A": 1_000_000.0, "B": 900_000.0, "C": 800_000.0}

    baseline = run_mcts_puct(
        legal_actions=legal,
        num_simulations=64,
        c_puct=1.5,
        priors_by_action=priors,
        values_by_action=values,
        q_clip_abs=0.01,
        q_root_normalization_mode="none",
        q_root_normalization_strength=0.0,
        value_rescale_mode="none",
    )
    patched = run_mcts_puct(
        legal_actions=legal,
        num_simulations=64,
        c_puct=1.5,
        priors_by_action=priors,
        values_by_action=values,
        q_clip_abs=0.01,
        q_root_normalization_mode="adaptive_minmax",
        q_root_normalization_strength=0.5,
        value_rescale_mode="none",
    )

    assert float(baseline.q_root_score_spread) == 0.0
    assert bool(patched.q_root_normalization_applied) is True
    assert float(patched.q_root_score_spread) > 0.0


def test_mcts_sampled_expectation_chance_mode_reports_effective_k() -> None:
    out = run_mcts_puct(
        legal_actions=["A", "B"],
        num_simulations=24,
        c_puct=1.5,
        priors_by_action={"A": 0.5, "B": 0.5},
        values_by_action={"A": 0.8, "B": 0.2},
        chance_mode="sampled_expectation",
        chance_samples_per_expansion=4,
        chance_value_noise_std=0.0,
    )
    assert int(out.chance_samples_per_expansion) == 4


def test_mcts_success_prob_term_prefers_higher_proxy_in_tie_like_conditions() -> None:
    legal = ["ATTACK_LOW", "ATTACK_HIGH"]
    out = run_mcts_puct(
        legal_actions=legal,
        num_simulations=1,
        c_puct=0.0,
        priors_by_action={"ATTACK_LOW": 0.5, "ATTACK_HIGH": 0.5},
        values_by_action={"ATTACK_LOW": 0.0, "ATTACK_HIGH": 0.0},
        success_prob_by_action={"ATTACK_LOW": 0.20, "ATTACK_HIGH": 0.80},
        success_prob_enabled=True,
        success_prob_alpha=0.30,
        success_prob_center=0.5,
        success_prob_scale=0.5,
        success_prob_centered_clip_abs=1.0,
    )
    assert str(out.chosen_action) == "ATTACK_HIGH"


def test_mcts_success_prob_term_disabled_restores_baseline_choice() -> None:
    legal = ["ATTACK_LOW", "ATTACK_HIGH"]
    out = run_mcts_puct(
        legal_actions=legal,
        num_simulations=1,
        c_puct=0.0,
        priors_by_action={"ATTACK_LOW": 0.5, "ATTACK_HIGH": 0.5},
        values_by_action={"ATTACK_LOW": 0.0, "ATTACK_HIGH": 0.0},
        success_prob_by_action={"ATTACK_LOW": 0.20, "ATTACK_HIGH": 0.80},
        success_prob_enabled=False,
        success_prob_alpha=0.30,
        success_prob_center=0.5,
        success_prob_scale=0.5,
        success_prob_centered_clip_abs=1.0,
    )
    assert str(out.chosen_action) == "ATTACK_LOW"
