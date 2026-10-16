from agents.muzero.core.mcts import run_mcts_puct


def test_mcts_puct_returns_valid_distribution():
    output = run_mcts_puct(["A", "B", "C"], num_simulations=24, c_puct=1.5)
    assert output.chosen_action in {"A", "B", "C"}
    assert len(output.probs) == 3
    assert abs(sum(output.probs) - 1.0) < 1e-9
    assert sum(output.visits) == 24


def test_mcts_puct_respects_external_priors():
    priors = {"A": 0.98, "B": 0.01, "C": 0.01}
    output = run_mcts_puct(
        ["A", "B", "C"],
        num_simulations=32,
        c_puct=1.5,
        priors_by_action=priors,
    )
    assert output.chosen_action == "A"


def test_mcts_puct_uses_external_values_when_provided():
    # Equal priors; chosen action should be the one with highest provided value.
    priors = {"A": 1.0 / 3.0, "B": 1.0 / 3.0, "C": 1.0 / 3.0}
    values = {"A": -0.2, "B": 0.9, "C": 0.1}
    output = run_mcts_puct(
        ["A", "B", "C"],
        num_simulations=40,
        c_puct=1.5,
        priors_by_action=priors,
        values_by_action=values,
    )
    assert output.chosen_action == "B"


def test_mcts_puct_applies_value_signs_in_backup():
    priors = {"A": 0.5, "B": 0.5}
    values = {"A": 0.9, "B": 0.3}
    signs = {"A": -1, "B": 1}
    output = run_mcts_puct(
        ["A", "B"],
        num_simulations=30,
        c_puct=1.5,
        priors_by_action=priors,
        values_by_action=values,
        value_sign_by_action=signs,
    )
    assert output.chosen_action == "B"


def test_mcts_temperature_sharpens_choice():
    output = run_mcts_puct(
        ["A", "B"],
        num_simulations=20,
        c_puct=1.5,
        priors_by_action={"A": 0.99, "B": 0.01},
        temperature=1e-6,
    )
    assert output.chosen_action == "A"


def test_mcts_q_guardrail_clips_extreme_values_and_tracks_counter():
    output = run_mcts_puct(
        ["A", "B"],
        num_simulations=20,
        c_puct=1.5,
        priors_by_action={"A": 0.01, "B": 0.99},
        values_by_action={"A": 1e9, "B": 0.0},
        q_clip_abs=0.0,
    )
    assert output.chosen_action == "B"
    assert int(output.q_guardrail_clipped_count) > 0
    assert float(output.q_guardrail_clip_limit) == 0.0


def test_mcts_sampled_expectation_chance_mode_tracks_k() -> None:
    output = run_mcts_puct(
        ["A", "B"],
        num_simulations=24,
        c_puct=1.5,
        priors_by_action={"A": 0.5, "B": 0.5},
        values_by_action={"A": 0.7, "B": 0.3},
        chance_mode="sampled_expectation",
        chance_samples_per_expansion=3,
        chance_value_noise_std=0.0,
    )
    assert int(output.chance_samples_per_expansion) == 3


def test_mcts_min_root_visits_top_n_zero_forces_all_actions_and_can_overspend() -> None:
    output = run_mcts_puct(
        ["A", "B", "C", "D"],
        num_simulations=8,
        c_puct=1.5,
        priors_by_action={"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10},
        values_by_action={"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1},
        min_root_visits_per_action=5,
        min_root_visits_top_n=0,
    )
    visits_by_action = {
        str(a): int(v) for a, v in zip(list(output.actions or []), list(output.visits or []))
    }
    assert sum(int(v) for v in visits_by_action.values()) >= 20
    assert visits_by_action["A"] >= 5
    assert visits_by_action["B"] >= 5
    assert visits_by_action["C"] >= 5
    assert visits_by_action["D"] >= 5
