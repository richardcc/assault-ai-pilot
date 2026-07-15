from assault_bench.runner import _build_head_diagnostics_eval


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
