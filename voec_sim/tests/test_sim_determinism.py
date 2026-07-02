from voec_sim.core.simulator import VOECSimulator


def test_new_episode_snapshot_is_stable_for_same_scenario():
    sim1 = VOECSimulator()
    sim2 = VOECSimulator()
    sim1.new_episode("battaglia_cittadina_2_1", seed=123)
    sim2.new_episode("battaglia_cittadina_2_1", seed=123)

    snap1 = sim1.snapshot()
    snap2 = sim2.snapshot()

    assert snap1.turn == snap2.turn
    assert len(snap1.units) == len(snap2.units)
    assert [(u.unit_id, u.q, u.r) for u in snap1.units] == [
        (u.unit_id, u.q, u.r) for u in snap2.units
    ]
