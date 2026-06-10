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
    ev = Evaluator(env=None, rl_controller=None, enemy_controller=None, rl_side="US")

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
