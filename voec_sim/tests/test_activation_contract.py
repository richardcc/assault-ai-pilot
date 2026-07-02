from voec_sim.core.simulator import VOECSimulator


def test_legal_actions_bound_to_active_side_units():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=10)
    snap = sim.snapshot()
    active_side = snap.to_play
    legal = sim.legal_actions()
    assert legal
    for action_id in legal:
        parts = str(action_id).split(":")
        assert len(parts) >= 2
        unit_id = parts[1]
        unit = next((u for u in snap.units if u.unit_id == unit_id), None)
        assert unit is not None
        assert unit.side == active_side
