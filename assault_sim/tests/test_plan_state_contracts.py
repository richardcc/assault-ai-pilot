import json

from assault_sim.contracts.training_contracts import normalize_plan_state


def test_normalize_plan_state_defaults_and_ranges():
    plan = normalize_plan_state({})
    assert plan["intent"] == "UNKNOWN"
    assert plan["unit_role"] == "UNKNOWN"
    assert plan["focus_vp_id"] is None
    assert plan["plan_step_id"] == 0
    assert plan["budget_state"] == "UNBOUNDED"
    assert plan["plan_progress_stub"] == 0.0
    assert plan["intent_alignment_stub"] == 0.0


def test_normalize_plan_state_clamps_values_and_serializes():
    plan = normalize_plan_state(
        {
            "intent": "capture",
            "unit_role": "support_fire",
            "focus_vp_id": "4,7",
            "plan_step_id": "12",
            "budget_state": "budgeted",
            "plan_progress_stub": 9.5,
            "intent_alignment_stub": -2.0,
        }
    )
    assert plan["intent"] == "CAPTURE"
    assert plan["unit_role"] == "SUPPORT_FIRE"
    assert plan["focus_vp_id"] == "4,7"
    assert plan["plan_step_id"] == 12
    assert plan["budget_state"] == "BUDGETED"
    assert plan["plan_progress_stub"] == 1.0
    assert plan["intent_alignment_stub"] == 0.0
    assert json.loads(json.dumps(plan))["intent"] == "CAPTURE"
