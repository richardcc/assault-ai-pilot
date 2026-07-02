from voec_sim.core.simulator import VOECSimulator


def test_clone_state_is_isolated_from_runtime_state():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=7)
    cloned = sim.clone_state()
    original = sim.snapshot()

    assert cloned is not None
    if cloned.units:
        cloned.units[0].alive = False

    new_snapshot = sim.snapshot()
    assert original.units[0].alive == new_snapshot.units[0].alive
