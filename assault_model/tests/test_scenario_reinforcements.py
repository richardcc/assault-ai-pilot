from __future__ import annotations

import pytest
from pathlib import Path

from assault_model.core.scenario_loader import load_scenario
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.paths import SCENARIOS_DIR, MAP_PIECE_CATALOG_PATH, UNIT_CATALOG_PATH
from voec_sim.core.simulator import VOECSimulator


@pytest.fixture
def catalogs():
    units = load_unit_catalog(UNIT_CATALOG_PATH)
    pieces = load_map_piece_catalog(MAP_PIECE_CATALOG_PATH)
    return units, pieces


def test_scenario_loader_parses_reinforcements(catalogs):
    units_cat, pieces_cat = catalogs
    scenario = load_scenario(SCENARIOS_DIR / "mettete_i_piedi_terra_1.json", units_cat, pieces_cat)

    assert hasattr(scenario, "reinforcements"), "Scenario must expose reinforcements property"
    assert len(scenario.reinforcements) >= 1, "Scenario 1.0 must have at least 1 reinforcement wave"
    wave = scenario.reinforcements[0]
    assert int(wave["turn"]) == 2
    assert wave["side"] == "US"
    assert "landing_zones" in wave
    assert "A" in wave["landing_zones"]
    assert "B" in wave["landing_zones"]
    assert len(wave["units"]) == 7, "2nd wave must contain 7 units (1 complete infantry company)"


def test_voec_simulator_deploys_reinforcements_at_turn_2():
    sim = VOECSimulator()
    sim.new_episode("mettete_i_piedi_terra_1", seed=42)

    snap1 = sim.snapshot()
    initial_us = [u for u in snap1.units if u.side == "US"]
    assert len(initial_us) == 7, "Turn 1 must start with 7 Darby's Rangers units"
    assert len(snap1.units) == 13, "Turn 1 total units must be 13 (6 IT + 7 US)"

    # Step through legal actions until Turn 2 is reached
    turn_2_reached = False
    for _ in range(120):
        legals = sim.legal_actions()
        if not legals:
            break
        tr = sim.step(legals[0])
        if tr.state.turn >= 2:
            turn_2_reached = True
            break

    assert turn_2_reached, "Simulator must advance into Turn 2"
    snap2 = sim.snapshot()
    turn2_us = [u for u in snap2.units if u.side == "US"]
    assert len(turn2_us) == 14, f"Turn 2 must have 14 US units (7 wave 1 + 7 wave 2), got {len(turn2_us)}"
    assert len(snap2.units) == 20, f"Turn 2 total units must be 20, got {len(snap2.units)}"

    # Check reinforcement IDs US_8..US_14 exist and are alive
    turn2_uids = {u.unit_id for u in snap2.units}
    for expected_id in [f"US_{i}" for i in range(8, 15)]:
        assert expected_id in turn2_uids, f"Reinforcement unit {expected_id} must be present in Turn 2"
