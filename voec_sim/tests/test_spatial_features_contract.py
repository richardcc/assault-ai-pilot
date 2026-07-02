from voec_sim.core.simulator import VOECSimulator


def test_spatial_features_exposes_vp_hexes_and_owner_map():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=7)
    spatial = sim.spatial_features()

    vp_hexes = list(spatial.get("vp_hexes", []) or [])
    owner_map = dict(spatial.get("vp_owner_by_hex", {}) or {})

    assert len(vp_hexes) > 0
    assert len(owner_map) == len(vp_hexes)
    for vp in vp_hexes:
        q = int(vp["q"])
        r = int(vp["r"])
        assert f"{q},{r}" in owner_map
