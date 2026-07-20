import random

from agents.efficientzero_v2.core.mcts import run_mcts_puct


def test_temperature_sampling_selects_multiple_actions() -> None:
    legal = ["A", "B"]
    counts = {"A": 0, "B": 0}
    for seed in range(120):
        random.seed(seed)
        out = run_mcts_puct(
            legal_actions=legal,
            num_simulations=16,
            c_puct=1.5,
            priors_by_action={"A": 0.5, "B": 0.5},
            values_by_action={"A": 0.2, "B": 0.2},
            temperature=1.0,
            dirichlet_epsilon=0.0,
        )
        counts[str(out.chosen_action)] += 1
    assert counts["A"] > 0
    assert counts["B"] > 0


def test_low_temperature_keeps_deterministic_choice() -> None:
    legal = ["A", "B"]
    chosen = []
    for seed in range(12):
        random.seed(seed)
        out = run_mcts_puct(
            legal_actions=legal,
            num_simulations=16,
            c_puct=1.5,
            priors_by_action={"A": 0.5, "B": 0.5},
            values_by_action={"A": 0.2, "B": 0.2},
            temperature=1e-6,
            dirichlet_epsilon=0.0,
        )
        chosen.append(str(out.chosen_action))
    assert len(set(chosen)) == 1


def test_min_root_visits_forces_coverage_on_top_n() -> None:
    random.seed(7)
    legal = ["A", "B", "C", "D"]
    out = run_mcts_puct(
        legal_actions=legal,
        num_simulations=32,
        c_puct=1.5,
        priors_by_action={"A": 0.50, "B": 0.30, "C": 0.15, "D": 0.05},
        values_by_action={"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1},
        temperature=1.0,
        dirichlet_epsilon=0.0,
        min_root_visits_per_action=2,
        min_root_visits_top_n=3,
    )
    visits_by_action = {
        str(a): int(v) for a, v in zip(list(out.actions or []), list(out.visits or []))
    }
    assert visits_by_action["A"] >= 2
    assert visits_by_action["B"] >= 2
    assert visits_by_action["C"] >= 2
