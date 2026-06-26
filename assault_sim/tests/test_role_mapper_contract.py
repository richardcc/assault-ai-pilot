from types import SimpleNamespace

from assault_sim.decision.role_mapper import resolve_role_with_reason


def _build_unit(classification: str = "STANDARD_INFANTRY"):
    return SimpleNamespace(
        unit_id="US_1",
        side="US",
        alive=True,
        position=SimpleNamespace(q=0, r=0),
        unit_type=SimpleNamespace(classification=classification),
    )


def _build_state(units):
    return SimpleNamespace(units=units)


def test_resolve_role_never_unknown_for_missing_unit():
    role, reason = resolve_role_with_reason(state=None, unit=None, plan_intent="CAPTURE")
    assert role != "UNKNOWN"
    assert reason == "fallback_no_unit"


def test_resolve_role_maps_intent_for_maneuver_units():
    unit = _build_unit("STANDARD_INFANTRY")
    state = _build_state([unit])
    role, reason = resolve_role_with_reason(state=state, unit=unit, plan_intent="DENY")
    assert role == "HOLD_VP"
    assert reason == "mapped_intent"


def test_resolve_role_maps_support_units():
    unit = _build_unit("SUPPORT_INFANTRY")
    enemy = SimpleNamespace(
        unit_id="IT_1",
        side="IT",
        alive=True,
        position=SimpleNamespace(q=2, r=0),
        unit_type=SimpleNamespace(classification="STANDARD_INFANTRY"),
    )
    state = _build_state([unit, enemy])
    role, reason = resolve_role_with_reason(state=state, unit=unit, plan_intent="ATTRIT")
    assert role == "SUPPORT_FIRE"
    assert reason == "mapped_support"
