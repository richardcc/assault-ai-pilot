# assault_model/tests/test_smoke_and_indirect_fire_system.py
from pathlib import Path
import pytest

from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.line_of_sight import LineOfSight, check_line_of_sight, clear_los_cache
from assault_model.combat.modifiers.terrain_modifier import TerrainModifier
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.combat.smoke_resolver import resolve_smoke_fire
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.smoke import FireSmokeAction
from assault_model.actions.resolution import resolve_action
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.units.unit_instance import UnitInstance
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex import Hex
from assault_model.map.terrain import Terrain
from assault_model.map.map import Map
from assault_model.map.terrain_config import terrain_config
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.state.game_state import GameState


@pytest.fixture(scope="module")
def catalog():
    return load_unit_catalog(Path("assets/catalogs/unit_catalog.json"))


def create_test_map(hex_definitions=None):
    """
    Helper creating a canonical Map for testing.
    hex_definitions is a list of (q, r, terrain) tuples.
    """
    if hex_definitions is None:
        hexes = [
            Hex(0, 0, Terrain.CLEAR),
            Hex(1, 0, Terrain.CLEAR),
            Hex(2, 0, Terrain.CLEAR),
            Hex(3, 0, Terrain.CLEAR),
            Hex(4, 0, Terrain.CLEAR),
            Hex(5, 0, Terrain.CLEAR),
            Hex(3, 1, Terrain.CLEAR),
            Hex(4, 1, Terrain.CLEAR),
        ]
    else:
        hexes = [Hex(q, r, t) for q, r, t in hex_definitions]
    return Map(hexes)


# =====================================================================
# SECTION 1: RULE 7.1 - INDIRECT FIRE ARCHITECTURE & TACTICAL PROPERTIES
# =====================================================================

def test_indirect_fire_card_properties_parsing(catalog):
    """Verify that indirect fire properties are parsed from catalog without fake traits."""
    mortar_50 = catalog["GE_50MM_MORTAR"]
    mortar_81 = catalog["US_81MM_MORTAR"]
    rifles = catalog["US_RIFLES_43"]

    # Mortars: 50mm has NONE, 81mm has WEAKEST_TERRAIN
    assert mortar_50.indirect_fire_profile["defense_loss"] == "NONE"
    assert mortar_50.indirect_fire_profile["reroll"] is False
    assert mortar_81.indirect_fire_profile["defense_loss"] == "WEAKEST_TERRAIN"

    # Rifle Grenades have reroll True and defense_loss WEAKEST_TERRAIN
    assert rifles.indirect_fire_profile["reroll"] is True
    assert rifles.indirect_fire_profile["defense_loss"] == "WEAKEST_TERRAIN"

    # No fake traits leaked into traits chips
    assert "ATTACK_DIE_REROLL" not in mortar_50.traits
    assert "REMOVE_WEAKEST_TERRAIN_DEFENSE" not in mortar_50.traits
    assert "ATTACK_DIE_REROLL" not in rifles.traits


def test_indirect_fire_ignores_blocking_los_and_no_hindrance_bonus(catalog):
    """
    Rule 7.1: Indirect fire is fired over terrain that blocks direct LOS.
    The defending unit does NOT gain defense dice for hindered LOS.
    """
    mortar = catalog["US_81MM_MORTAR"]
    infantry = catalog["US_RIFLES_43"]

    # Place a heavy forest (blocks LOS) between firer (0,0) and target (4,0)
    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.HEAVY_FOREST),  # BLOCKS LOS
        (3, 0, Terrain.CLEAR),
        (4, 0, Terrain.BRUSH),         # Target hex with terrain cover
    ])

    attacker = UnitInstance(unit_id="MORTAR_1", unit_type=mortar, side="GE", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="DEF_1", unit_type=infantry, side="US", position=HexCoord(4, 0))

    # Direct line of sight is BLOCKED
    los = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los == LineOfSight.BLOCKED

    # But indirect fire executes successfully!
    ctx = ExecutionContext(game_map=gmap)
    action = RangedIndirectAttack(attacker.unit_id, (4, 0))

    result = resolve_ranged_combat(
        action=action,
        attacker=attacker,
        target=defender,
        distance=4,
        context=ctx,
    )

    # Combat resolved: attack dice and defense dice rolled
    assert len(result.attack_roll) > 0
    assert len(result.defense_roll) > 0

    # Mortar has defense_loss: "WEAKEST_TERRAIN"
    # Brush gives GREEN and BLUE. Weakest die (BLUE) is removed!
    # Defender has base defense (YELLOW) + remaining stronger terrain die (GREEN).
    assert DiceColor.BLUE not in [d.color for d in result.defense_roll]
    assert DiceColor.GREEN in [d.color for d in result.defense_roll]
    assert DiceColor.YELLOW in [d.color for d in result.defense_roll]


def test_indirect_fire_blocked_when_firer_in_heavy_forest_or_building(catalog):
    """
    Rule 7.1: Indirect fire is not possible out of a terrain hex with heavy forest or building.
    """
    mortar = catalog["GE_50MM_MORTAR"]
    infantry = catalog["US_RIFLES_43"]

    gmap = create_test_map([
        (0, 0, Terrain.HEAVY_FOREST),  # Firer is in heavy forest (no_indirect_from: true)
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
        (3, 0, Terrain.CLEAR),
        (4, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="MORTAR_1", unit_type=mortar, side="GE", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="DEF_1", unit_type=infantry, side="US", position=HexCoord(4, 0))

    ctx = ExecutionContext(game_map=gmap)
    action = RangedIndirectAttack(attacker.unit_id, (4, 0))

    result = resolve_ranged_combat(
        action=action,
        attacker=attacker,
        target=defender,
        distance=4,
        context=ctx,
    )

    # Attack is completely blocked from inside heavy forest
    assert len(result.attack_roll) == 0
    assert len(result.defense_roll) == 0


def test_indirect_fire_reroll_property(catalog):
    """
    Rule Rifle Grenades (US_RIFLES_43):
    Attacker with reroll: True may re-roll one of their attack dice.
    """
    rifles = catalog["US_RIFLES_43"]
    enemy = catalog["GE_RIFLES_43"]

    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="US_1", unit_type=rifles, side="US", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="GE_1", unit_type=enemy, side="GE", position=HexCoord(2, 0))

    ctx = ExecutionContext(game_map=gmap)
    action = RangedIndirectAttack(attacker.unit_id, (2, 0))

    # Run trials to confirm combat resolves without error
    for _ in range(5):
        result = resolve_ranged_combat(
            action=action,
            attacker=attacker,
            target=defender,
            distance=2,
            context=ctx,
        )
        assert len(result.attack_roll) > 0


# =====================================================================
# SECTION 2: RULE 7.1.2 - INDIRECT FIRE ON VEHICLES
# =====================================================================

def test_indirect_fire_on_vehicles_preliminary_roll_and_defense(catalog):
    """
    Rule 7.1.2:
    - Preliminary roll by attacker.
    - Blanks and suppressions are discarded.
    - If remaining dice exist, actual attack roll takes place with remaining dice.
    - Vehicle uses FLANK defense dice (or ABOVE if critical hit in remaining dice).
    - In any case, vehicle receives +1 GREEN defense die.
    """
    mortar = catalog["US_81MM_MORTAR"]

    # Build a mock vehicle unit type with distinct sectors
    from assault_model.units.unit_type import UnitType, UnitCategory, UnitSide
    tank_type = UnitType(
        code="TEST_PANZER",
        side=UnitSide.GE,
        category=UnitCategory.VEHICLE,
        base_defense={
            "FRONT": ["RED", "YELLOW"],
            "FLANK": ["YELLOW"],
            "FLANK_LEFT": ["YELLOW"],
            "FLANK_RIGHT": ["YELLOW"],
            "ABOVE": ["BLUE"],
        },
    )

    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
        (3, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="MORTAR_1", unit_type=mortar, side="US", position=HexCoord(0, 0))
    vehicle = UnitInstance(unit_id="TANK_1", unit_type=tank_type, side="GE", position=HexCoord(3, 0))

    ctx = ExecutionContext(game_map=gmap)
    action = RangedIndirectAttack(attacker.unit_id, (3, 0))

    # Run multiple trials to verify Rule 7.1.2 mechanics
    effective_trials = 0
    for _ in range(20):
        result = resolve_ranged_combat(
            action=action,
            attacker=attacker,
            target=vehicle,
            distance=3,
            context=ctx,
        )
        # If attack passed preliminary roll:
        if len(result.attack_roll) > 0:
            effective_trials += 1
            # Rule 7.1.2: Vehicle always receives +1 GREEN defense die for indirect fire
            assert DiceColor.GREEN in [d.color for d in result.defense_roll]

            # Check sector used:
            has_crit = any(
                any("CRITICAL" in getattr(f, "name", str(f)).upper() for f in getattr(d, "faces", []))
                for d in result.attack_roll
            )
            defense_colors = [d.color for d in result.defense_roll]
            if has_crit:
                # Direct hit: uses ABOVE defense (BLUE) + 1 GREEN
                assert DiceColor.BLUE in defense_colors
            else:
                # Flank defense (YELLOW) + 1 GREEN
                assert DiceColor.YELLOW in defense_colors

    assert effective_trials > 0


# =====================================================================
# SECTION 3: RULE 7.2 - FIRING SMOKE (MULTI-STAGE CASCADE & MAP MARKERS)
# =====================================================================

def test_unit_can_fire_smoke_and_smoke_dice(catalog):
    """Verify smoke capability and dice pools from unit catalog cards."""
    mortar_50 = catalog["GE_50MM_MORTAR"]
    mortar_81 = catalog["US_81MM_MORTAR"]
    rifles = catalog["US_RIFLES_43"]

    assert mortar_50.can_fire_smoke() is True
    # 50mm mortar: 3 Green, 3 Blue
    smoke_dice_50 = mortar_50.get_smoke_dice()
    assert smoke_dice_50.count(DiceColor.GREEN) == 3
    assert smoke_dice_50.count(DiceColor.BLUE) == 3

    assert mortar_81.can_fire_smoke() is True
    # 81mm mortar: 4 Green, 4 Blue
    smoke_dice_81 = mortar_81.get_smoke_dice()
    assert smoke_dice_81.count(DiceColor.GREEN) == 4
    assert smoke_dice_81.count(DiceColor.BLUE) == 4

    assert rifles.can_fire_smoke() is False
    assert rifles.get_smoke_dice() == []


def test_resolve_smoke_fire_primary_and_adjacent_hexes(catalog):
    """
    Rule 7.2:
    - Active player rolls smoke dice pool.
    - Damage symbols place smoke markers in target hex (max 4).
    - Misses are put to one side.
    - If misses exist, active player nominates adjacent hex 1 and rolls missed dice.
    - If misses still exist, nominated adjacent hex 2 is rolled.
    - No damage, no suppression, no defense roll for units in hex.
    """
    mortar = catalog["US_81MM_MORTAR"]
    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
        (3, 0, Terrain.CLEAR),
        (4, 0, Terrain.CLEAR),  # Primary target hex
        (3, 1, Terrain.CLEAR),  # Adjacent hex 1
        (4, 1, Terrain.CLEAR),  # Adjacent hex 2
    ])

    attacker = UnitInstance(unit_id="MORTAR_1", unit_type=mortar, side="US", position=HexCoord(0, 0))

    # Place an enemy unit in primary target hex
    enemy = UnitInstance(unit_id="ENEMY_1", unit_type=catalog["GE_RIFLES_43"], side="GE", position=HexCoord(4, 0))
    initial_enemy_strength = enemy.strength

    action = FireSmokeAction(
        unit_id=attacker.unit_id,
        target_hex=(4, 0),
        adjacent_hexes=[(3, 1), (4, 1)],
    )

    res = resolve_smoke_fire(action, attacker, gmap)

    # Unit marked as having fired
    assert attacker.has_fired is True

    # Smoke placed in primary hex (up to max 4)
    target_markers = gmap.get_smoke_markers((4, 0))
    assert target_markers == res.smoke_placed.get((4, 0), 0)
    assert 0 <= target_markers <= 4

    # Enemy unit in hex must suffer NO damage and NO suppression
    assert enemy.strength == initial_enemy_strength
    assert getattr(enemy, "suppressed", False) is False

    # Check that adjacent hexes got markers if misses cascaded
    adj1_markers = gmap.get_smoke_markers((3, 1))
    adj2_markers = gmap.get_smoke_markers((4, 1))
    assert 0 <= adj1_markers <= 4
    assert 0 <= adj2_markers <= 4


def test_map_smoke_markers_cap_at_four():
    """Rule 7.2: Maximum of four smoke markers per hex."""
    gmap = create_test_map()

    added = gmap.add_smoke_markers((2, 0), count=3)
    assert added == 3
    assert gmap.get_smoke_markers((2, 0)) == 3

    # Add 3 more: should cap at 4 (only 1 added)
    added_second = gmap.add_smoke_markers((2, 0), count=3)
    assert added_second == 1
    assert gmap.get_smoke_markers((2, 0)) == 4

    # Any further additions add 0
    added_third = gmap.add_smoke_markers((2, 0), count=2)
    assert added_third == 0
    assert gmap.get_smoke_markers((2, 0)) == 4


# =====================================================================
# SECTION 4: RULE 10.3 - SMOKE & LINE OF SIGHT (HINDRANCE & BLOCKING)
# =====================================================================

def test_smoke_los_clear_hindered_and_blocked(catalog):
    """
    Rule 10.3:
    - 0 smoke markers: CLEAR
    - 1 or 2 smoke markers in ray: HINDERED (+1 green defense die in direct fire)
    - 3 or more smoke markers in ray: BLOCKED (direct fire prohibited)
    """
    infantry_us = catalog["US_RIFLES_43"]
    infantry_ge = catalog["GE_RIFLES_43"]

    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="US_1", unit_type=infantry_us, side="US", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="GE_1", unit_type=infantry_ge, side="GE", position=HexCoord(2, 0))

    # Case 1: No smoke -> CLEAR
    clear_los_cache()
    gmap.clear_smoke_markers()
    los_1 = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los_1 == LineOfSight.CLEAR

    # Case 2: 1 smoke marker on intermediate hex (1, 0) -> HINDERED
    clear_los_cache()
    gmap.add_smoke_markers((1, 0), count=1)
    los_2 = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los_2 == LineOfSight.HINDERED

    # In direct fire combat, HINDERED adds +1 GREEN defense die to defender
    ctx = ExecutionContext(game_map=gmap)
    class MockDirectAction:
        combat_mode = CombatMode.RANGED_DIRECT
        unit_id = attacker.unit_id
        target_id = defender.unit_id
    res_combat = resolve_ranged_combat(
        action=MockDirectAction(),
        attacker=attacker,
        target=defender,
        distance=2,
        context=ctx,
    )
    # Defender has base YELLOW + 1 GREEN from HINDERED LOS
    assert DiceColor.GREEN in [d.color for d in res_combat.defense_roll]

    # Case 3: 2 smoke markers on intermediate hex (1, 0) -> HINDERED
    clear_los_cache()
    gmap.clear_smoke_markers()
    gmap.add_smoke_markers((1, 0), count=2)
    los_3 = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los_3 == LineOfSight.HINDERED

    # Case 4: 3 smoke markers on intermediate hex (1, 0) -> BLOCKED
    clear_los_cache()
    gmap.clear_smoke_markers()
    gmap.add_smoke_markers((1, 0), count=3)
    los_4 = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los_4 == LineOfSight.BLOCKED

    # Direct fire is blocked
    res_blocked = resolve_ranged_combat(
        action=MockDirectAction(),
        attacker=attacker,
        target=defender,
        distance=2,
        context=ctx,
    )
    assert len(res_blocked.attack_roll) == 0
    assert len(res_blocked.defense_roll) == 0


def test_smoke_on_target_hex_hinders_and_blocks_los(catalog):
    """
    Rule 10.3: Smoke covering the target hex itself obscures the ray.
    1-2 smoke markers on target hex -> HINDERED
    3-4 smoke markers on target hex -> BLOCKED
    """
    infantry_us = catalog["US_RIFLES_43"]
    infantry_ge = catalog["GE_RIFLES_43"]

    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="US_1", unit_type=infantry_us, side="US", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="GE_1", unit_type=infantry_ge, side="GE", position=HexCoord(2, 0))

    # Place 1 smoke marker directly on target hex (2, 0)
    clear_los_cache()
    gmap.clear_smoke_markers()
    gmap.add_smoke_markers((2, 0), count=1)
    los = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los == LineOfSight.HINDERED

    # Place 3 smoke markers directly on target hex (2, 0)
    clear_los_cache()
    gmap.clear_smoke_markers()
    gmap.add_smoke_markers((2, 0), count=3)
    los_blocked = check_line_of_sight(attacker, defender, gmap, terrain_config)
    assert los_blocked == LineOfSight.BLOCKED


# =====================================================================
# SECTION 5: RULE 6.5 - ORGANIZATION PHASE SMOKE DISSIPATION
# =====================================================================

def test_organization_phase_smoke_dissipation():
    """
    Rule 6.5 Organization Phase Step 6:
    Reduce the number of smoke markers on each hex by 1.
    When a marker reaches 0, it is removed.
    """
    gmap = create_test_map()

    gmap.add_smoke_markers((1, 0), count=1)
    gmap.add_smoke_markers((2, 0), count=3)
    gmap.add_smoke_markers((3, 0), count=4)

    assert gmap.get_smoke_markers((1, 0)) == 1
    assert gmap.get_smoke_markers((2, 0)) == 3
    assert gmap.get_smoke_markers((3, 0)) == 4

    # End of turn 1 organization phase
    gmap.dissipate_smoke_markers()

    assert gmap.get_smoke_markers((1, 0)) == 0  # 1 -> 0 (removed)
    assert (1, 0) not in gmap.smoke_markers
    assert gmap.get_smoke_markers((2, 0)) == 2  # 3 -> 2
    assert gmap.get_smoke_markers((3, 0)) == 3  # 4 -> 3

    # End of turn 2 organization phase
    gmap.dissipate_smoke_markers()
    assert gmap.get_smoke_markers((2, 0)) == 1  # 2 -> 1
    assert gmap.get_smoke_markers((3, 0)) == 2  # 3 -> 2


# =====================================================================
# SECTION 6: ACTION RESOLUTION DISPATCH & ACTION CATALOG
# =====================================================================

def test_resolve_action_dispatches_smoke(catalog):
    """Verify resolve_action() executes FireSmokeAction and updates game state."""
    mortar = catalog["GE_50MM_MORTAR"]
    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
        (3, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="MORTAR_1", unit_type=mortar, side="GE", position=HexCoord(0, 0))
    state = GameState(game_map=gmap, units=[attacker])

    action = FireSmokeAction(
        unit_id=attacker.unit_id,
        target_hex=(3, 0),
        adjacent_hexes=[(2, 0)],
    )

    res = resolve_action(state=state, action=action)
    assert res.combat_result is not None
    assert res.combat_result.firer_id == attacker.unit_id
    assert res.combat_result.target_hex == (3, 0)
    assert 0 <= state.game_map.get_smoke_markers((3, 0)) <= 4


def test_action_catalog_generates_smoke_action(catalog):
    """Verify ActionCatalog produces FireSmokeAction when unit can fire smoke."""
    mortar = catalog["US_81MM_MORTAR"]
    enemy = catalog["GE_RIFLES_43"]

    gmap = create_test_map([
        (0, 0, Terrain.CLEAR),
        (1, 0, Terrain.CLEAR),
        (2, 0, Terrain.CLEAR),
        (3, 0, Terrain.CLEAR),
        (4, 0, Terrain.CLEAR),
    ])

    attacker = UnitInstance(unit_id="US_MORTAR", unit_type=mortar, side="US", position=HexCoord(0, 0))
    target = UnitInstance(unit_id="GE_INF", unit_type=enemy, side="GE", position=HexCoord(3, 0))
    attacker.spotted_enemies = [target.unit_id]

    state = GameState(game_map=gmap, units=[attacker, target])
    ac = ActionCatalog(game_state=state, unit=attacker, terrain_config=terrain_config)
    actions = ac.actions()

    # Should contain RangedIndirectAttack AND FireSmokeAction
    smoke_actions = [a for a in actions if isinstance(a, FireSmokeAction)]
    indirect_actions = [a for a in actions if isinstance(a, RangedIndirectAttack)]

    assert len(indirect_actions) >= 1
    assert len(smoke_actions) >= 1
    assert smoke_actions[0].target_hex == (3, 0)
    assert smoke_actions[0].combat_mode == CombatMode.SMOKE
