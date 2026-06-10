from types import SimpleNamespace

import pytest

from assault_model.map.hex_coord import HexCoord
from assault_sim.rl import state_encoder


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


def test_lote_d_features_tail_present(monkeypatch):
    monkeypatch.setattr(state_encoder, "compute_tactical_features", lambda *_args, **_kwargs: [])
    state = _build_state()
    obs = state_encoder.encode_state(
        state=state,
        unit=None,
        rl_side="US",
        scenario=SimpleNamespace(max_turns=20, victory_outcomes={}),
        unit_stuck_steps_norm=0.4,
        plan_commitment_age_norm=0.6,
        intent_alignment_last_k=0.75,
        last_failure_reason_onehot=[1.0, 0.0, 1.0, 0.0],
    )
    # Tail layout: [..., lote_d(7), lote_e(4)]
    assert float(obs[-11]) == pytest.approx(0.4, rel=1e-6, abs=1e-6)
    assert float(obs[-10]) == pytest.approx(0.6, rel=1e-6, abs=1e-6)
    assert float(obs[-9]) == pytest.approx(0.75, rel=1e-6, abs=1e-6)
    assert float(obs[-8]) == pytest.approx(1.0, rel=1e-6, abs=1e-6)
    assert float(obs[-7]) == pytest.approx(0.0, rel=1e-6, abs=1e-6)
    assert float(obs[-6]) == pytest.approx(1.0, rel=1e-6, abs=1e-6)
    assert float(obs[-5]) == pytest.approx(0.0, rel=1e-6, abs=1e-6)
