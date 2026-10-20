import pytest
from pathlib import Path

from assault_model.core.scenario_loader import load_scenario
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.paths import SCENARIOS_DIR, MAP_PIECE_CATALOG_PATH, UNIT_CATALOG_PATH
from assault_model.combat.line_of_sight import LineOfSight, check_line_of_sight, clear_los_cache
from assault_model.map.terrain_config import terrain_config


@pytest.fixture
def catalogs():
    units = load_unit_catalog(UNIT_CATALOG_PATH)
    pieces = load_map_piece_catalog(MAP_PIECE_CATALOG_PATH)
    return units, pieces


def test_battaglia_cittadina_rebalance_oob_and_smoke(catalogs):
    units_cat, pieces_cat = catalogs
    scenario = load_scenario(SCENARIOS_DIR / "battaglia_cittadina_2_1.json", units_cat, pieces_cat)

    # 1. Verify US_5 is US_COMBAT_ENGINEERS_43
    us_5 = next((u for u in scenario.units if u.unit_id == "US_5"), None)
    assert us_5 is not None, "US_5 must exist in scenario units"
    assert us_5.unit_type.code == "US_COMBAT_ENGINEERS_43", (
        f"US_5 unit_key must be US_COMBAT_ENGINEERS_43, got {us_5.unit_type.code}"
    )
    assert us_5.side == "US"
    assert "EXPLOSIVE_CHARGE" in us_5.unit_type.traits
    assert "BANGALORE_TORPEDO" in us_5.unit_type.traits
    assert us_5.position.q == 7 and us_5.position.r == 9

    # 2. Verify no artificial static smoke markers are pre-placed on map (Rule 7.2 fidelity)
    assert scenario.game_map.get_smoke_markers(7, 6) == 0, "No artificial static smoke markers should be in scenario JSON"

    # 3. Verify dynamic smoke capabilities for tactical deployment (Mortar indirect + Engineer smoke grenades)
    us_7 = next((u for u in scenario.units if u.unit_id == "US_7"), None)
    assert us_7 is not None
    assert us_7.unit_type.can_fire_smoke(), "81mm Mortar must be capable of laying dynamic smoke screens"
    assert us_5.unit_type.can_fire_smoke(), "Combat Engineers must have smoke grenade deployment capability"
    assert "SMOKE_GRENADES" in us_5.unit_type.traits

    # 4. Acceptance Criterion: Attacker assault effectiveness ratio >= 1.0 against fixed defense
    # US Combat Engineers 0-range direct fire pool: RED + RED + YELLOW (3 + 3 + 2 = 8 attack power)
    # Target Italian regular infantry base defense: 1 YELLOW (2 defense power)
    # Attack power (8) / defense power (2) = 4.0 >= 1.0
    from assault_model.units.unit_type import UnitCategory
    eng_dice = us_5.unit_type.get_close_combat_attack_dice(UnitCategory.INFANTRY)
    assert len(eng_dice) >= 3, "Engineers must have at least 3 dice at assault range (0 hex)"
    attack_power = sum(3.0 if d.name == "RED" else 2.0 if d.name == "YELLOW" else 1.0 for d in eng_dice)
    target_def_power = 2.0  # 1 YELLOW die base
    assault_ratio = attack_power / target_def_power
    assert assault_ratio >= 1.0, f"Assault effectiveness ratio {assault_ratio} must be >= 1.0"


def test_mettete_i_piedi_terra_rebalance_oob_and_smoke(catalogs):
    units_cat, pieces_cat = catalogs
    scenario = load_scenario(SCENARIOS_DIR / "mettete_i_piedi_terra_1.json", units_cat, pieces_cat)

    # 1. Verify US_5 is US_COMBAT_ENGINEERS_43
    us_5 = next((u for u in scenario.units if u.unit_id == "US_5"), None)
    assert us_5 is not None, "US_5 must exist in scenario units"
    assert us_5.unit_type.code == "US_COMBAT_ENGINEERS_43", (
        f"US_5 unit_key must be US_COMBAT_ENGINEERS_43, got {us_5.unit_type.code}"
    )
    assert us_5.side == "US"
    assert us_5.position.q == 4 and us_5.position.r == 12, (
        f"US Engineers expected at [4, 12] in central sector, got ({us_5.position.q}, {us_5.position.r})"
    )

    # 2. Verify central barbed wire fortification at (4, 9) exists
    fort_type = scenario.game_map.get_hex_fortification(4, 9)
    assert fort_type == "barbed_wire", f"Expected barbed_wire at (4, 9), got {fort_type}"

    # 3. Verify no artificial static smoke markers are pre-placed on map (Rule 7.2 fidelity)
    assert scenario.game_map.get_smoke_markers(4, 10) == 0, "No artificial static smoke markers should be in scenario JSON"

    # 4. Verify dynamic smoke capabilities and breach traits (Bangalore, Explosive charge)
    us_7 = next((u for u in scenario.units if u.unit_id == "US_7"), None)
    assert us_7 is not None
    assert us_7.unit_type.can_fire_smoke(), "81mm Mortar must be capable of laying dynamic smoke screens"
    assert us_5.unit_type.can_fire_smoke(), "Combat Engineers must have smoke grenade capability"
    assert "EXPLOSIVE_CHARGE" in us_5.unit_type.traits
    assert "BANGALORE_TORPEDO" in us_5.unit_type.traits
    assert "SMOKE_GRENADES" in us_5.unit_type.traits

    # 5. Acceptance Criterion: Attacker assault effectiveness ratio >= 1.0
    from assault_model.units.unit_type import UnitCategory
    eng_dice = us_5.unit_type.get_close_combat_attack_dice(UnitCategory.INFANTRY)
    attack_power = sum(3.0 if d.name == "RED" else 2.0 if d.name == "YELLOW" else 1.0 for d in eng_dice)
    german_def_power = 2.0  # GE_RIFLES_43 has 1 YELLOW base defense
    assault_ratio = attack_power / german_def_power
    assert assault_ratio >= 1.0, f"Assault effectiveness ratio {assault_ratio} must be >= 1.0"
