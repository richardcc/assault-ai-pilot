from assault_sim.evaluation.record_sb3_trace import _build_step_trace_entry


def test_trace_entry_includes_plan_fields():
    trace = _build_step_trace_entry(
        step_idx=3,
        info={
            "plan_intent": "CAPTURE",
            "plan_unit_role": "ASSAULT",
            "plan_focus_vp_id": "5,8",
            "plan_step_id": 9,
            "plan_budget_state": "UNBOUNDED",
            "plan_progress_stub": 1.0,
            "intent_alignment_stub": 1.0,
            "capture_emergency_override": True,
            "capture_legal_override": False,
            "capture_override_reason": "capture_emergency",
        },
        strategy_idx=0,
        option_idx=1,
        attack_mode=0,
        unit_slot=0,
        reward=0.5,
        done=False,
        truncated=False,
    )
    plan = trace["plan_debug"]
    capture = trace["capture_debug"]
    assert plan["intent"] == "CAPTURE"
    assert plan["unit_role"] == "ASSAULT"
    assert plan["focus_vp_id"] == "5,8"
    assert plan["plan_step_id"] == 9
    assert capture["emergency_override"] is True
    assert capture["legal_override"] is False
    assert capture["override_reason"] == "capture_emergency"


def test_trace_entry_backward_compatible_when_plan_missing():
    trace = _build_step_trace_entry(
        step_idx=1,
        info={},
        strategy_idx=0,
        option_idx=0,
        attack_mode=0,
        unit_slot=0,
        reward=0.0,
        done=False,
        truncated=False,
    )
    assert "plan_debug" in trace
    assert trace["plan_debug"]["intent"] is None
    assert trace["plan_debug"]["plan_step_id"] is None
    assert trace["capture_debug"]["emergency_override"] is False
    assert trace["capture_debug"]["legal_override"] is False
