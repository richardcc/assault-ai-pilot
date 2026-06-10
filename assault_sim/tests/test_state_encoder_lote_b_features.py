from types import SimpleNamespace

import pytest

from assault_model.map.hex_coord import HexCoord
from assault_sim.rl import state_encoder


class _DummyCatalog:
    def __init__(self, _state, _unit, _terrain_config):
        pass

    def actions(self):
        return [
            SimpleNamespace(
                action_type=SimpleNamespace(category=state_encoder.ActionCategory.MOVEMENT),
                path=[HexCoord(2, 0)],
            )
        ]


def _build_state():
    rl = SimpleNamespace(
        unit_id="US_1",
        side="US",
        alive=True,
        hp=10,
        position=HexCoord(0, 0),
        spotted_enemies=[],
        unit_type=SimpleNamespace(classification="STANDARD_INFANTRY"),
    )
    en = SimpleNamespace(
        unit_id="IT_1",
        side="IT",
        alive=True,
        hp=10,
        position=HexCoord(3, 0),
        spotted_enemies=[],
    )
    vp = SimpleNamespace(hex_coords=(2, 0), per_turn=1)
    game_map = SimpleNamespace(
        get_hex=lambda _q, _r: SimpleNamespace(get_terrain=lambda: "clear"),
        get_hex_fortification_data=lambda _q, _r: {},
    )
    return SimpleNamespace(
        units=[rl, en],
        turn=1,
        vp_tracker=SimpleNamespace(total_points=0, conditions=SimpleNamespace(points=[vp])),
        victory=SimpleNamespace(points=[vp]),
        side_to_ownership={"US": "BLUE", "IT": "RED"},
        hex_states={(2, 0): SimpleNamespace(ownership="RED")},
        game_map=game_map,
    )


def test_lote_b_features_present_and_bounded(monkeypatch):
    monkeypatch.setattr(state_encoder, "compute_tactical_features", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(state_encoder, "ActionCatalog", _DummyCatalog)
    state = _build_state()
    obs = state_encoder.encode_state(
        state=state,
        unit=None,
        rl_side="US",
        scenario=SimpleNamespace(max_turns=20, victory_outcomes={}),
        focus_vp_id="2,0",
    )
    # Tail layout: [..., lote_a(4), lote_c(4), lote_b(4), lote_d(7), lote_e(4)]
    for idx in (-15, -14, -13, -12):
        assert 0.0 <= float(obs[idx]) <= 1.0
    assert float(obs[-12]) == pytest.approx(1.0, rel=1e-6, abs=1e-6)
