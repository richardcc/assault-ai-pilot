from voec_sim.assets_bridge.importers import AssetPaths, load_catalogs


def test_unit_catalog_loads_from_existing_assets():
    unit_catalog, _ = load_catalogs(AssetPaths())
    assert len(unit_catalog) > 0


def test_unit_catalog_contains_expected_keys():
    unit_catalog, _ = load_catalogs(AssetPaths())
    keys = set(unit_catalog.keys())
    # Known keys from existing UI/unit catalogs.
    assert "US_RIFLES_43" in keys
    assert "GE_RIFLES_43" in keys
