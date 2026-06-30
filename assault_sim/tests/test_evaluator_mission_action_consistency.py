from types import SimpleNamespace

from assault_sim.evaluation.evaluator import Evaluator
from assault_model.actions.action_category import ActionCategory


class _DummyCatalog:
    def __init__(self, _state, _unit, _terrain_config):
        pass

    def actions(self):
        return []


def _build_state():
    return SimpleNamespace(
        victory=SimpleNamespace(points=[SimpleNamespace(hex_coords=(3, 4))]),
        side_to_ownership={"US": "BLUE"},
        hex_states={(3, 4): SimpleNamespace(ownership="RED")},
    )


def _build_unit():
    return SimpleNamespace(
        unit_id="US_1",
        side="US",
        position=SimpleNamespace(q=1, r=1),
    )


def _build_move_action_to(q, r):
    return SimpleNamespace(
        action_type=SimpleNamespace(category=ActionCategory.MOVEMENT),
        path=[SimpleNamespace(q=q, r=r)],
    )


def test_vp_entry_opportunity_depends_on_legal_movement_actions(monkeypatch):
    # Contract: evaluator must infer VP-entry opportunity from legal movement
    # actions ending in uncaptured VP hexes.
    state = _build_state()
    unit = _build_unit()
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")

    class _CatalogWithVP(_DummyCatalog):
        def actions(self):
            return [_build_move_action_to(3, 4)]

    monkeypatch.setattr("assault_sim.evaluation.evaluator.ActionCatalog", _CatalogWithVP)
    assert ev._can_enter_uncaptured_vp_now(state, unit) is True

    class _CatalogWithoutVP(_DummyCatalog):
        def actions(self):
            return [_build_move_action_to(2, 2)]

    monkeypatch.setattr("assault_sim.evaluation.evaluator.ActionCatalog", _CatalogWithoutVP)
    assert ev._can_enter_uncaptured_vp_now(state, unit) is False


def test_vp_entry_rate_math_handles_zero_and_nonzero_opportunities():
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")

    conv, missed = ev._compute_vp_entry_rates(vp_entry_opportunities=0, vp_entries_taken=0)
    assert conv is None
    assert missed is None

    conv, missed = ev._compute_vp_entry_rates(vp_entry_opportunities=5, vp_entries_taken=0)
    assert conv == 0.0
    assert missed == 1.0

    conv, missed = ev._compute_vp_entry_rates(vp_entry_opportunities=5, vp_entries_taken=2)
    assert conv == 0.4
    assert missed == 0.6


def test_vp_entry_rate_math_supports_full_conversion():
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")
    conv, missed = ev._compute_vp_entry_rates(vp_entry_opportunities=3, vp_entries_taken=3)
    assert conv == 1.0
    assert missed == 0.0


def test_can_enter_vp_requires_uncaptured_vp_destination(monkeypatch):
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")
    unit = _build_unit()
    state = SimpleNamespace(
        victory=SimpleNamespace(points=[SimpleNamespace(hex_coords=(3, 4))]),
        side_to_ownership={"US": "BLUE"},
        # VP already owned by US side -> no entry opportunity
        hex_states={(3, 4): SimpleNamespace(ownership="BLUE")},
    )

    class _CatalogWithVP(_DummyCatalog):
        def actions(self):
            return [_build_move_action_to(3, 4)]

    monkeypatch.setattr("assault_sim.evaluation.evaluator.ActionCatalog", _CatalogWithVP)
    assert ev._can_enter_uncaptured_vp_now(state, unit) is False


def test_captured_objectives_for_side_uses_normalized_side_keys():
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")
    state = SimpleNamespace(
        victory=SimpleNamespace(
            points=[SimpleNamespace(hex_coords=(1, 1)), SimpleNamespace(hex_coords=(2, 2))]
        ),
        side_to_ownership={"Side.US": "BLUE", "SIDE.GE": "RED"},
        hex_states={
            (1, 1): SimpleNamespace(ownership="BLUE"),
            (2, 2): SimpleNamespace(ownership="RED"),
        },
    )
    assert ev._captured_objectives_for_side(state, "US") == 1


def test_vp_entry_conversion_requires_opportunity_and_success_signal():
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")
    info_success = {
        "objective_captured_delta": 1,
        "actor_captured_vp_now": False,
        "actor_on_vp_after": False,
        "actor_vp_owned_by_rl_before": False,
    }
    assert ev._is_vp_entry_converted_now(False, 0, info_success) is False
    assert ev._is_vp_entry_converted_now(True, 0, info_success) is True


def test_vp_entry_success_signal_accepts_actor_entering_enemy_vp():
    ev = Evaluator(env=None, rl_controller=None, rl_side="US")
    info = {
        "objective_captured_delta": 0,
        "actor_captured_vp_now": False,
        "actor_on_vp_after": True,
        "actor_vp_owned_by_rl_before": False,
    }
    assert ev._did_vp_entry_succeed_now(0, info) is True
