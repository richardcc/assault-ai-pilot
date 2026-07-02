from voec_sim.core.simulator import VOECSimulator


def test_snapshot_units_have_identity_fields():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1")
    snapshot = sim.snapshot()
    assert snapshot.units
    for unit in snapshot.units:
        assert unit.unit_id
        assert unit.unit_key
        assert unit.side
