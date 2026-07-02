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
