from types import SimpleNamespace

from assault_model.runtime.game_state_runtime import RuntimeGameState


def _unit(unit_id: str, side: str, *, alive: bool = True, suppressed: bool = False, fallback: bool = False):
    unit = SimpleNamespace(
        unit_id=unit_id,
        side=side,
        alive=alive,
        suppressed=suppressed,
        fallback=fallback,
    )
    unit.clear_suppression = lambda: setattr(unit, "suppressed", False)
    unit.clear_fallback = lambda: setattr(unit, "fallback", False)
    return unit


def _runtime(units):
    base_state = SimpleNamespace(turn=1, units=list(units))
    scenario = SimpleNamespace()
    return RuntimeGameState(base_state, scenario)


def test_multiside_activation_rotates_and_rolls_turn():
    rt = _runtime([
        _unit("A_1", "A"),
        _unit("B_1", "B"),
        _unit("C_1", "C"),
    ])

    # sides are discovered dynamically and sorted
    assert rt.active_side == "A"

    rt.activated_units.add("A_1")
    rt.next_activation()
    assert rt.active_side == "B"

    rt.activated_units.add("B_1")
    rt.next_activation()
    assert rt.active_side == "C"

    rt.activated_units.add("C_1")
    rt.next_activation()
    # no units left -> new turn + reset activation
    assert rt.base_state.turn == 2
    assert rt.active_side == "A"
    assert rt.activated_units == set()


def test_multiside_activation_skips_side_without_activable_units():
    rt = _runtime([
        _unit("A_1", "A"),
        _unit("B_1", "B", suppressed=True),  # B cannot act
        _unit("C_1", "C"),
    ])

    assert rt.active_side == "A"
    rt.activated_units.add("A_1")
    rt.next_activation()
    # B is skipped because no available units
    assert rt.active_side == "C"


def test_rollover_clears_suppression_and_restores_unit_eligibility():
    rt = _runtime([
        _unit("A_1", "A", suppressed=True),
        _unit("B_1", "B"),
    ])

    # Reach B side first, then exhaust B to trigger turn rollover.
    rt.next_activation()
    assert rt.active_side == "B"
    rt.activated_units.add("B_1")
    rt.next_activation()

    assert rt.base_state.turn == 2
    assert rt.active_side == "A"
    a1 = next(u for u in rt.base_state.units if u.unit_id == "A_1")
    assert a1.suppressed is False
    assert [u.unit_id for u in rt.get_available_units("A")] == ["A_1"]
