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


def test_spatial_features_exposes_doctrine_roles_and_optimal_ranges():
    sim = VOECSimulator()
    sim.new_episode("battaglia_cittadina_2_1", seed=7)
    spatial = sim.spatial_features()

    roles = spatial.get("unit_doctrine_roles", {})
    ranges = spatial.get("unit_optimal_ranges", {})

    assert isinstance(roles, dict)
    assert isinstance(ranges, dict)
    assert len(roles) > 0
    assert len(ranges) > 0

    snapshot = sim.snapshot()
    for u in snapshot.units:
        assert u.unit_id in roles
        assert u.unit_id in ranges
        assert u.doctrine_role is not None
        assert u.doctrine_profile is not None
        assert "default_role" in u.doctrine_profile
        assert "optimal_engagement_range" in u.doctrine_profile
