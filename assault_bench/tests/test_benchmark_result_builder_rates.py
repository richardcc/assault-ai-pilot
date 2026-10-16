from __future__ import annotations

from assault_bench.benchmark_result_builder import build_benchmark_result


def test_build_benchmark_result_non_timeout_rates() -> None:
    out = build_benchmark_result(
        agent_name="a",
        profile="p",
        group="g",
        goal="goal",
        policy="mcts",
        policy_by_side={"IT": "mcts", "US": "mcts"},
        seeds=[1, 2, 3, 4],
        returns=[1.0, -1.0, 1.0, 0.0],
        steps=[10, 10, 10, 10],
        terminals=[True, True, True, True],
        timeouts=[True, False, False, True],
        wins=[True, True, False, False],
        terminal_reason_counts={"turn_unit_budget": 2, "objective_outcome_resolved": 2},
        vp_initial_sum_by_side={"IT": 0.0, "US": 0.0},
        vp_final_sum_by_side={"IT": 0.0, "US": 0.0},
        vp_initial_counts_by_side={"IT": {}, "US": {}},
        vp_final_counts_by_side={"IT": {}, "US": {}},
        vp_gained_sum_by_side={"IT": 0.0, "US": 0.0},
        vp_lost_sum_by_side={"IT": 0.0, "US": 0.0},
        winner_side_counts={"IT": 2, "US": 2},
        tracked_side="US",
        tracked_metric="objectives_captured",
        tracked_captured_values=[0, 0, 0, 0],
        scenario_outcome_counts={},
        scenario_outcome_class_counts={},
        scenario_outcome_class_counts_by_side={},
        tracked_outcome_bucket_counts={},
        opponent_outcome_bucket_counts={},
        phase29_seed_rows=[],
        phase29_seed_rows_by_side=[],
        eval_decision_summary={},
        eval_decisions_top=[],
        eval_decision_steps_top=[],
        seed_games_rows=[],
        episode_wall_s_values=[],
        profile_wall_s=1.0,
    )
    assert out.timeout_rate == 0.5
    assert out.non_timeout_resolution_rate == 0.5
    # Non-timeout episodes are seeds 2 and 3; only seed 2 is a win.
    assert out.resolved_non_timeout_win_rate == 0.5
