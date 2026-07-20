from assault_bench.runner import (
    _compute_decision_diagnostics_kpis,
    _build_head_diagnostics_eval,
    _count_immediate_vp_capture_move_options,
    _is_immediate_vp_capture_move_taken,
)


def test_head_diagnostics_uses_objective_opportunity_as_primary_denominator():
    out = _build_head_diagnostics_eval(
        train_summary={"objective_loss": 0.2},
        eval_kpis={
            "xai_decision_steps": 10.0,
            "xai_vp_capture_opportunity_steps": 4.0,
            "xai_vp_capture_taken_steps": 2.0,
            "xai_vp_immediate_capture_opportunity_steps": 1.0,
            "xai_vp_immediate_capture_taken_steps": 1.0,
        },
        muzero_row={"tracked_captured_avg": 0.0},
    )
    objective = dict(out.get("objective", {}) or {})
    assert objective["eval_vp_capture_opportunity_steps"] == 4.0
    assert objective["eval_vp_capture_take_rate"] == 0.5
    assert objective["eval_vp_capture_take_rate_denominator_steps"] == 4.0
    assert objective["eval_vp_conversion_efficiency"] == 0.2
    assert objective["eval_vp_conversion_efficiency_denominator_steps"] == 10.0


def test_head_diagnostics_keeps_immediate_capture_metric_separate():
    out = _build_head_diagnostics_eval(
        train_summary={"objective_loss": 0.1},
        eval_kpis={
            "xai_decision_steps": 8.0,
            "xai_vp_capture_opportunity_steps": 3.0,
            "xai_vp_capture_taken_steps": 1.0,
            "xai_vp_immediate_capture_opportunity_steps": 1.0,
            "xai_vp_immediate_capture_taken_steps": 1.0,
        },
        muzero_row={"tracked_captured_avg": 0.0},
    )
    objective = dict(out.get("objective", {}) or {})
    assert objective["eval_vp_capture_take_rate"] == (1.0 / 3.0)
    assert objective["eval_vp_immediate_capture_take_rate"] == 1.0
    assert objective["eval_vp_immediate_conversion_efficiency"] == (1.0 / 8.0)


def test_immediate_capture_opportunity_counts_move_into_capturable_vp():
    options = _count_immediate_vp_capture_move_options(
        side="US",
        legal_actions=[
            "MOVE:US_1:2:2",
            "MOVE:US_1:5:5",
            "ATTACK:US_1:GE_1:2:2",
            "WAIT:US_1",
        ],
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}, {"q": 5, "r": 5, "vp_id": "VP_B"}],
        vp_owner_by_hex={"2,2": "GE", "5,5": "US"},
    )
    assert options == 1


def test_immediate_capture_taken_requires_move_and_owner_conversion():
    taken = _is_immediate_vp_capture_move_taken(
        side="US",
        chosen_action_id="MOVE:US_1:2:2",
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        before_vp_owner_by_hex={"2,2": "GE"},
        after_vp_owner_by_hex={"2,2": "US"},
    )
    not_taken_without_conversion = _is_immediate_vp_capture_move_taken(
        side="US",
        chosen_action_id="MOVE:US_1:2:2",
        vp_hexes=[{"q": 2, "r": 2, "vp_id": "VP_A"}],
        before_vp_owner_by_hex={"2,2": "GE"},
        after_vp_owner_by_hex={"2,2": "GE"},
    )
    assert taken is True
    assert not_taken_without_conversion is False


def test_decision_diagnostics_kpis_compute_expected_rates_and_spreads():
    trace_rows = [
        {
            "step": 0,
            "game_turn": 1,
            "action_id": "MOVE:US_1:2:2",
            "legal_capture_options": 1,
            "capture_like_taken": False,
            "mcts_action_candidates": [
                {"action_id": "MOVE:US_1:2:2", "vp_progress_delta": 1.0, "real_decision_score": 0.8, "mcts_q_value": 9.999, "q_clip_limit": 10.0},
                {"action_id": "WAIT:US_1", "vp_progress_delta": 0.0, "real_decision_score": 1.1, "mcts_q_value": 0.2, "q_clip_limit": 10.0},
            ],
        },
        {
            "step": 2,
            "game_turn": 5,
            "action_id": "WAIT:US_1",
            "legal_capture_options": 1,
            "capture_like_taken": True,
            "mcts_action_candidates": [
                {"action_id": "WAIT:US_1", "vp_progress_delta": -0.5, "real_decision_score": 0.4, "mcts_q_value": -10.0, "q_clip_limit": 10.0},
                {"action_id": "MOVE:US_1:3:2", "vp_progress_delta": 0.5, "real_decision_score": 0.9, "mcts_q_value": 0.1, "q_clip_limit": 10.0},
            ],
        },
    ]
    out = _compute_decision_diagnostics_kpis(trace_rows)
    assert out["vp_approach_rate_eligible_steps"] == 2
    assert out["vp_approach_rate_positive_steps"] == 1
    assert out["vp_approach_rate"] == 0.5
    assert out["vp_regret_delta_count"] == 2
    assert out["vp_regret_delta_mean"] == 0.4
    assert out["q_saturation_candidate_rows"] == 4
    assert out["q_saturation_hits"] == 2
    assert out["q_saturation_rate"] == 0.5
    assert out["decision_spread_step_count"] == 2
    assert out["path_to_capture_length_episode"] == 2
    assert out["path_to_capture_length_count"] == 1
    assert out["opportunity_conversion_early_opportunity_steps"] == 1
    assert out["opportunity_conversion_early_converted_steps"] == 0
    assert out["opportunity_conversion_mid_opportunity_steps"] == 1
    assert out["opportunity_conversion_mid_converted_steps"] == 1
    assert out["opportunity_conversion_late_opportunity_steps"] == 0
