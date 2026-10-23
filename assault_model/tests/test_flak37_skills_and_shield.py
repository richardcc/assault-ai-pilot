import pytest
from pathlib import Path

from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.units.unit_instance import UnitInstance
from assault_model.map.hex_coord import HexCoord
from assault_model.map.combat_geometry import (
    calculate_facing_towards,
    is_in_arc_of_fire,
    determine_attack_sector,
)
from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.movement import FastMoveAction
from assault_model.rules.movement_rules import MovementRules
from assault_model.paths import UNIT_CATALOG_PATH


@pytest.fixture
def catalog():
    return load_unit_catalog(UNIT_CATALOG_PATH)


def test_flak37_catalog_stats_and_traits(catalog):
    """
    Verify canonical 3.7cm Flak 37 (Card S43) catalog entry, exact dice pools,
    cost, movement, and the three required skills: Slow, Pivot, Shield.
    """
    assert "GE_3_7CM_FLAK_37" in catalog
    flak = catalog["GE_3_7CM_FLAK_37"]

    # Basic card stats
    assert flak.code == "GE_3_7CM_FLAK_37"
    assert flak.cost == 8
    assert flak.movement == 1
    assert flak.max_strength == 4
    assert flak.movement_type == "artillery"
    assert flak.subtype == "LIGHT_AA"

    # Traits & skills
    assert flak.has_trait("SLOW") is True
    assert flak.has_trait("SLOW_UNIT") is True
    assert flak.has_trait("PIVOT") is True
    assert flak.has_trait("SHIELD") is True

    # Base defense
    assert list(flak.get_defense_dice(sector=AttackSector.FRONT)) == [DiceColor.YELLOW]
    assert list(flak.get_defense_dice(sector=AttackSector.FLANK_LEFT)) == [DiceColor.YELLOW]
    assert list(flak.get_defense_dice(sector=AttackSector.FLANK_RIGHT)) == [DiceColor.RED]
    assert list(flak.get_defense_dice(sector=AttackSector.REAR)) == [DiceColor.YELLOW]

    # Direct fire attack against vehicles
    v_cat = catalog["GE_SNIPER_43"].category.__class__["VEHICLE"]
    assert tuple(flak.get_attack_dice(distance=0, target_category=v_cat)) == (DiceColor.YELLOW,)
    assert tuple(flak.get_attack_dice(distance=2, target_category=v_cat)) == (DiceColor.YELLOW, DiceColor.BLUE)
    assert tuple(flak.get_attack_dice(distance=6, target_category=v_cat)) == (DiceColor.GREEN, DiceColor.BLUE)
    assert tuple(flak.get_attack_dice(distance=10, target_category=v_cat)) == (DiceColor.GREEN,)

    # Direct fire attack against infantry
    i_cat = catalog["GE_SNIPER_43"].category.__class__["INFANTRY"]
    assert tuple(flak.get_attack_dice(distance=0, target_category=i_cat)) == (
        DiceColor.YELLOW,
        DiceColor.YELLOW,
        DiceColor.BLUE,
    )
    assert tuple(flak.get_attack_dice(distance=2, target_category=i_cat)) == (
        DiceColor.RED,
        DiceColor.YELLOW,
        DiceColor.BLUE,
        DiceColor.BLUE,
    )
    assert tuple(flak.get_attack_dice(distance=6, target_category=i_cat)) == (
        DiceColor.RED,
        DiceColor.GREEN,
        DiceColor.BLUE,
    )
    assert tuple(flak.get_attack_dice(distance=9, target_category=i_cat)) == (
        DiceColor.YELLOW,
        DiceColor.GREEN,
        DiceColor.BLUE,
    )


def test_slow_trait_blocks_fast_actions(catalog):
    """
    Skill 'Slow': 'This unit cannot use fast action.'
    Verify that units with SLOW / SLOW_UNIT trait cannot perform fast actions.
    """
    flak_type = catalog["GE_3_7CM_FLAK_37"]
    flak_unit = UnitInstance(
        unit_id="flak_1",
        unit_type=flak_type,
        side="GE",
        position=HexCoord(0, 0),
    )

    # MovementRules query
    assert MovementRules.can_use_fast_action(flak_unit) is False
    assert MovementRules.can_use_fast_action(flak_type) is False

    # FastMoveAction validation
    fast_action = FastMoveAction("flak_1", [HexCoord(0, 1)])
    assert fast_action.is_valid_for_unit(flak_unit) is False

    # Standard infantry (without SLOW) can use fast action
    sniper_type = catalog["GE_SNIPER_43"]
    sniper_unit = UnitInstance(
        unit_id="sniper_1",
        unit_type=sniper_type,
        side="GE",
        position=HexCoord(0, 0),
    )
    assert MovementRules.can_use_fast_action(sniper_unit) is True
    assert fast_action.is_valid_for_unit(sniper_unit) is True


def test_pivot_trait_360_degree_arc_of_fire(catalog):
    """
    Skill 'Pivot': 'This unit has a 360 degree arc of fire and a shield.'
    Verify that is_in_arc_of_fire returns True in all 360-degree directions
    for a unit with PIVOT trait.
    """
    origin = HexCoord(5, 5)
    targets_all_around = [
        HexCoord(5, 3),   # North
        HexCoord(5, 7),   # South
        HexCoord(8, 5),   # East
        HexCoord(2, 5),   # West
        HexCoord(7, 3),   # North-East
        HexCoord(3, 7),   # South-West
    ]

    # With pivot (True), all directions are in arc of fire
    for t in targets_all_around:
        assert is_in_arc_of_fire(origin, origin_facing="N", target=t, has_pivot=True) is True

    # Verify standard unit facing "N" is blocked when target is directly South
    south_target = HexCoord(5, 7)
    assert is_in_arc_of_fire(origin, origin_facing="N", target=south_target, has_pivot=False) is False


def test_shield_auto_orientation_on_ranged_combat(catalog):
    """
    Skill 'Shield': 'This unit is automatically orientated with its front armor
    to where it is firing.'
    Verify that when the Flak 37 fires, its facing turns directly towards the target,
    and counter-attacks from that target strike its FRONT armor shield.
    """
    flak_type = catalog["GE_3_7CM_FLAK_37"]
    flak_unit = UnitInstance(
        unit_id="flak_1",
        unit_type=flak_type,
        side="GE",
        position=HexCoord(2, 2),
    )
    # Unit initially faces North
    flak_unit.facing = "N"

    # Enemy target is to the East at (5, 2)
    enemy_type = catalog["GE_SNIPER_43"]
    enemy_unit = UnitInstance(
        unit_id="enemy_1",
        unit_type=enemy_type,
        side="US",
        position=HexCoord(5, 2),
    )
    enemy_unit.facing = "W"

    action = RangedDirectAttack("flak_1", "enemy_1")

    # Before firing, facing is N
    assert flak_unit.facing == "N"

    # Execute ranged combat
    resolve_ranged_combat(
        action=action,
        attacker=flak_unit,
        target=enemy_unit,
        distance=3,
        context=None,
    )

    # After firing, facing MUST automatically be orientated to "E" (towards target)
    assert flak_unit.facing == "E"

    # If the enemy at (5, 2) attacks flak at (2, 2), the attack sector must be FRONT
    sector_vs_enemy = determine_attack_sector(
        attacker_pos=enemy_unit.position,
        defender_pos=flak_unit.position,
        defender_facing=flak_unit.facing,
    )
    assert sector_vs_enemy == AttackSector.FRONT

    # Test second orientation: enemy is to the South at (2, 6)
    enemy_south = UnitInstance(
        unit_id="enemy_south",
        unit_type=enemy_type,
        side="US",
        position=HexCoord(2, 6),
    )
    action_south = RangedDirectAttack("flak_1", "enemy_south")

    resolve_ranged_combat(
        action=action_south,
        attacker=flak_unit,
        target=enemy_south,
        distance=4,
        context=None,
    )

    # After firing South, facing MUST be "S"
    assert flak_unit.facing == "S"

    # Incoming counter-fire from South now strikes FRONT
    sector_vs_south = determine_attack_sector(
        attacker_pos=enemy_south.position,
        defender_pos=flak_unit.position,
        defender_facing=flak_unit.facing,
    )
    assert sector_vs_south == AttackSector.FRONT
