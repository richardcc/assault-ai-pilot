from types import SimpleNamespace

from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.rl.tactical_options import TacticalOption


class _DummyHeuristic:
    def choose_action(self, _state, _unit, _option):
        return None


class _DummyCatalog:
    def __init__(self, _state, _unit, _terrain_config):
        pass

    def actions(self):
        return []


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
        turn=1,
    )
    return state, unit


def test_option_executor_tags_plan_fields_on_action(monkeypatch):
    monkeypatch.setattr("assault_sim.decision.option_executor.ActionCatalog", _DummyCatalog)
    state, unit = _build_state_and_unit()
    ex = OptionExecutor(_DummyHeuristic())

    action = ex.execute(
        state=state,
        unit=unit,
        option=TacticalOption.ADVANCE,
        attack_mode=0,
        strategy=StrategicIntent.CAPTURE,
        objective_tracked_side="US",
    )

    assert action.__class__.__name__ == "WaitAction"
    assert getattr(action, "rl_plan_intent", "") == "CAPTURE"
    assert getattr(action, "rl_plan_unit_role", "") in {"SCREEN", "ASSAULT", "SUPPORT_FIRE", "UNKNOWN"}
    assert getattr(action, "rl_plan_focus_vp_id", None) is None
    assert int(getattr(action, "rl_plan_step_id", 0)) >= 1
    assert getattr(action, "rl_plan_budget_state", "") == "UNBOUNDED"
    assert getattr(action, "rl_capture_emergency_override", False) is False
    assert getattr(action, "rl_capture_legal_override", False) is False


def test_option_executor_plan_step_id_monotonic(monkeypatch):
    monkeypatch.setattr("assault_sim.decision.option_executor.ActionCatalog", _DummyCatalog)
    state, unit = _build_state_and_unit()
    ex = OptionExecutor(_DummyHeuristic())

    a1 = ex.execute(state, unit, TacticalOption.HOLD, strategy=StrategicIntent.DENY)
    a2 = ex.execute(state, unit, TacticalOption.HOLD, strategy=StrategicIntent.DENY)

    assert int(getattr(a2, "rl_plan_step_id", 0)) > int(getattr(a1, "rl_plan_step_id", 0))
