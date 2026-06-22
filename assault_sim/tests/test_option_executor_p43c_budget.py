from types import SimpleNamespace

from assault_sim.decision.option_executor import OptionExecutor
from assault_model.actions.status import WaitAction
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.rl.tactical_options import TacticalOption


class _DummyHeuristic:
    def choose_action(self, _state, _unit, _option):
        return None


def _build_state_and_unit():
    unit = SimpleNamespace(
        unit_id="US_1",
        side="US",
        alive=True,
        suppressed=False,
        hp=10,
        position=SimpleNamespace(q=0, r=0),
        unit_type=SimpleNamespace(classification="STANDARD_INFANTRY", max_strength=10),
    )
    state = SimpleNamespace(
        units=[unit],
        victory=SimpleNamespace(points=[]),
        side_to_ownership={},
        hex_states={},
        turn=3,
    )
    return state, unit


def test_p43c_budget_tags_include_remaining_and_violations(monkeypatch):
    state, unit = _build_state_and_unit()
    ex = OptionExecutor(_DummyHeuristic())

    monkeypatch.setattr(ex, "_plan_focus_vp_id", lambda *_: "0,0")

    slot = ex._capture_budget_slot(unit.side, state.turn)
    slot["required_advances"] = 2
    slot["advance_count"] = 0
    slot["decision_count"] = 0
    slot["violation_count"] = 1

    action = ex._tag_action(
        WaitAction(unit.unit_id),
        TacticalOption.ADVANCE,
        StrategicIntent.CAPTURE,
        state=state,
        unit=unit,
        budget_state=ex._capture_budget_state_label(unit.side, state.turn, True),
        budget_remaining_by_role={"ADVANCE": 2},
        budget_violation_count=int(slot["violation_count"]),
        budget_violation_delta=1,
    )

    assert getattr(action, "rl_l2_option", "") == "ADVANCE"
    assert getattr(action, "rl_plan_budget_state", "") == "BUDGETED"
    assert getattr(action, "rl_plan_budget_violation_count", 0) == 1
    assert getattr(action, "rl_plan_budget_violation_delta", 0) == 1
    assert getattr(action, "rl_plan_budget_remaining_by_role", {}).get("ADVANCE", -1) == 2
