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


def test_min_root_visits_top_n_zero_forces_all_actions() -> None:
    random.seed(11)
    legal = ["A", "B", "C", "D"]
    out = run_mcts_puct(
        legal_actions=legal,
        num_simulations=64,
        c_puct=1.5,
        priors_by_action={"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10},
        values_by_action={"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1},
        temperature=1.0,
        dirichlet_epsilon=0.0,
        min_root_visits_per_action=2,
        min_root_visits_top_n=0,
    )
    visits_by_action = {
        str(a): int(v) for a, v in zip(list(out.actions or []), list(out.visits or []))
    }
    assert visits_by_action["A"] >= 2
    assert visits_by_action["B"] >= 2
    assert visits_by_action["C"] >= 2
    assert visits_by_action["D"] >= 2


def test_min_root_visits_can_exceed_nominal_simulation_budget() -> None:
    random.seed(23)
    legal = ["A", "B", "C", "D"]
    out = run_mcts_puct(
        legal_actions=legal,
        num_simulations=8,
        c_puct=1.5,
        priors_by_action={"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.10},
        values_by_action={"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1},
        temperature=1.0,
        dirichlet_epsilon=0.0,
        min_root_visits_per_action=5,
        min_root_visits_top_n=0,
    )
    visits_by_action = {
        str(a): int(v) for a, v in zip(list(out.actions or []), list(out.visits or []))
    }
    assert sum(int(v) for v in visits_by_action.values()) >= 20
    assert visits_by_action["A"] >= 5
    assert visits_by_action["B"] >= 5
    assert visits_by_action["C"] >= 5
    assert visits_by_action["D"] >= 5


def test_value_rescale_tanh_bounds_q_values() -> None:
    random.seed(19)
    out = run_mcts_puct(
        legal_actions=["A", "B"],
        num_simulations=48,
        c_puct=1.5,
        priors_by_action={"A": 0.5, "B": 0.5},
        values_by_action={"A": 900000.0, "B": -900000.0},
        temperature=1.0,
        dirichlet_epsilon=0.0,
        value_rescale_mode="tanh",
        value_rescale_temperature=10.0,
    )
    rows = list(out.root_candidate_breakdown or [])
    assert rows
    q_vals = [float(r.get("q_value", 0.0) or 0.0) for r in rows]
    assert max(abs(v) for v in q_vals) <= 1.000001


def test_value_rescale_signed_log_tanh_preserves_order_on_large_values() -> None:
    random.seed(29)
    out = run_mcts_puct(
        legal_actions=["A", "B"],
        num_simulations=16,
        c_puct=1.5,
        priors_by_action={"A": 0.5, "B": 0.5},
        values_by_action={"A": 1_000_000.0, "B": 500_000.0},
        temperature=1.0,
        dirichlet_epsilon=0.0,
        value_rescale_mode="signed_log_tanh",
        value_rescale_temperature=8.0,
        q_root_normalization_strength=0.0,
        min_root_visits_per_action=4,
        min_root_visits_top_n=0,
    )
    rows = {str(r.get("action_id", "")): dict(r or {}) for r in list(out.root_candidate_breakdown or [])}
    assert rows
    q_a = float(rows["A"].get("q_value", 0.0) or 0.0)
    q_b = float(rows["B"].get("q_value", 0.0) or 0.0)
    assert q_a > q_b


def test_success_component_is_nonzero_when_enabled() -> None:
    random.seed(31)
    out = run_mcts_puct(
        legal_actions=["A", "B"],
        num_simulations=16,
        c_puct=1.5,
        priors_by_action={"A": 0.5, "B": 0.5},
        values_by_action={"A": 0.1, "B": 0.1},
        temperature=1.0,
        dirichlet_epsilon=0.0,
        success_prob_enabled=True,
        success_prob_alpha=0.25,
        success_prob_center=0.45,
        success_prob_scale=0.35,
        success_prob_centered_clip_abs=1.0,
    )
    rows = list(out.root_candidate_breakdown or [])
    assert rows
    comps = [float(r.get("success_component", 0.0) or 0.0) for r in rows]
    assert any(abs(v) > 1e-9 for v in comps)
