# -*- coding: utf-8 -*-
import pytest
from assault_bench.sprt import WaldSPRT, SPRTDecision
from assault_bench.benchmark_matrix_runner import execute_benchmark_matrix


def test_sprt_stopping_in_sequential_mode():
    """Verify that execute_benchmark_matrix stops early when SPRT criteria is met."""
    seeds = list(range(1, 50))  # 50 seeds scheduled

    # Mock functions for episode execution
    call_count = 0

    def mock_run_episode(**kwargs):
        nonlocal call_count
        call_count += 1
        # Always return a decisive win for candidate
        return (
            kwargs["seed"],   # seed_used
            10.0,             # ret
            5,                # step_count
            True,             # terminal
            False,            # timeout
            True,             # win
            "objective_vps",  # terminal_reason
            {"GE": 0, "IT": 0},
            {"GE": 30, "IT": 0},
            "GE",
            {"outcome": "win"},
            {},
            [],
        )

    def mock_accumulate(**kwargs):
        kwargs["wins"].append(kwargs["win"])
        kwargs["returns"].append(kwargs["ret"])
        kwargs["steps"].append(kwargs["step_count"])
        kwargs["terminals"].append(kwargs["terminal"])
        kwargs["timeouts"].append(kwargs["timeout"])
        return "GE", "vp"

    results, _ = execute_benchmark_matrix(
        matchup_specs=[{
            "profile": "test_sprt_profile",
            "agent_name": "ezv2_test",
            "policy": "random",
            "enable_sprt": True,
            "sprt_config": {
                "p0": 0.50,
                "p1": 0.75,
                "alpha": 0.01,
                "beta": 0.01,
                "min_games": 5,
                "max_games": 50,
            },
        }],
        seeds=seeds,
        sides=["GE", "IT"],
        num_workers=1,
        scenario_id="battaglia_cittadina_2_1",
        policy_seed_task_builder_fn=lambda **kw: kw,
        benchmark_seed_task_fn=lambda kw: (),
        benchmark_seed_task_batch_fn=None,
        run_episode_with_policy_fn=mock_run_episode,
        accumulate_seed_episode_fn=mock_accumulate,
        build_eval_decision_summary_fn=lambda trace_rows: ({}, []),
        normalize_outcome_score_fn=lambda sc: 1,
        compute_seed_side_outcome_metrics_fn=lambda rows: {},
        outcome_bucket_from_score_fn=lambda s: "win",
        outcome_bucket_from_class_fn=lambda c: "win",
        max_steps=10,
        max_steps_override=0,
        mcts_simulations=1,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        mcts_dirichlet_alpha=0.3,
        mcts_dirichlet_epsilon=0.0,
        mcts_q_clip_abs=10.0,
        mcts_q_root_normalization_mode="adaptive_minmax",
        mcts_q_root_normalization_strength=0.35,
        mcts_value_rescale_mode="tanh",
        mcts_value_rescale_temperature=10.0,
        mcts_success_prob_enabled=False,
        mcts_success_prob_alpha=0.0,
        mcts_success_prob_center=0.5,
        mcts_success_prob_scale=0.5,
        mcts_success_prob_centered_clip_abs=1.0,
        mcts_min_root_visits_per_action=0,
        mcts_min_root_visits_top_n=0,
        checkpoint_path="",
        ckpt=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        reward_shaping_cfg={},
        bench_device="cpu",
        model_kind="efficientzero_v2",
        muz_cfg=None,
        model=None,
        enable_sprt=True,
    )

    assert len(results) == 1
    res = results[0]
    # SPRT should stop well before 50 games when all games are wins!
    assert res.episodes < 50
    assert res.episodes >= 5  # At least min_games
    assert res.win_rate == 1.0
    assert "sprt_status" in res.eval_decision_summary
    assert res.eval_decision_summary["sprt_status"]["active"] is True
