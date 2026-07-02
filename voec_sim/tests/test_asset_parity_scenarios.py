from voec_sim.assets_bridge.importers import AssetPaths, list_scenario_ids


def test_scenarios_exist_in_current_assets():
    scenarios = list_scenario_ids(AssetPaths())
    assert len(scenarios) > 0


def test_battaglia_cittadina_present():
    scenarios = set(list_scenario_ids(AssetPaths()))
    assert "battaglia_cittadina_2_1" in scenarios
