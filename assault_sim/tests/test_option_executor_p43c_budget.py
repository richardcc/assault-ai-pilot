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


def test_p43c_light_budget_forces_advance_until_quota(monkeypatch):
    state, unit = _build_state_and_unit()
    ex = OptionExecutor(_DummyHeuristic())

    monkeypatch.setattr(ex, "_has_uncaptured_objective_for_side", lambda *_: True)
    monkeypatch.setattr(ex, "_has_uncaptured_objective", lambda *_: True)
    monkeypatch.setattr(ex, "_is_capture_emergency", lambda *_: False)
    monkeypatch.setattr(ex, "_is_behind_on_objectives", lambda *_: False)
    monkeypatch.setattr(ex, "_nearest_uncaptured_vp_dist", lambda *_: 2)
    monkeypatch.setattr(ex, "_has_vp_attack_opportunity", lambda *_: False)
    monkeypatch.setattr(ex, "_resolve_option_for_strategy", lambda _s, _u, o, _st: o)
    monkeypatch.setattr(ex, "_apply_local_role_bias", lambda _s, _u, o, _st: o)
    monkeypatch.setattr(ex, "_move_closer", lambda _s, u: WaitAction(u.unit_id))

    a1 = ex.execute(
        state=state,
        unit=unit,
        option=TacticalOption.ATTACK,
        strategy=StrategicIntent.ATTRIT,
        objective_tracked_side="US",
    )
    a2 = ex.execute(
        state=state,
        unit=unit,
        option=TacticalOption.ATTACK,
        strategy=StrategicIntent.ATTRIT,
        objective_tracked_side="US",
    )

    assert getattr(a1, "rl_l2_option", "") == "ADVANCE"
    assert getattr(a1, "rl_plan_budget_state", "") == "BUDGETED"
    assert getattr(a1, "rl_capture_legal_override", False) is True
    assert getattr(a2, "rl_l2_option", "") == "ADVANCE"
    assert getattr(a2, "rl_plan_budget_state", "") == "EXHAUSTED"
    assert getattr(a2, "rl_capture_legal_override", False) is True
