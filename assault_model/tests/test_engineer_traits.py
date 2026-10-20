import pytest
from unittest.mock import MagicMock

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace
from assault_model.combat.battle_die import DiceResult
from assault_model.actions.action_type import ActionType
from assault_model.actions.combat_mode import CombatMode
from assault_model.actions.explosive_charge import ExplosiveChargeAction
from assault_model.actions.mine_detection import MineDetectionAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.resolution import resolve_action
from assault_model.combat.explosive_charge_resolver import (
    resolve_explosive_charge,
    _get_strongest_terrain_defense_die,
)
from assault_model.combat.mine_resolver import (
    resolve_mine_detection,
    calculate_detection_modifiers,
)
from assault_model.map.map import Map
from assault_model.map.hex import Hex
from assault_model.map.terrain import Terrain
from assault_model.map.hex_coord import HexCoord
from assault_model.map.terrain_config import terrain_config
from assault_model.units.unit_type import UnitType, UnitCategory, UnitSide
from assault_model.units.unit_instance import UnitInstance
from assault_model.state.game_state import GameState


def _make_engineer_unit(unit_id="US_ENG_1", pos=(2, 2)):
    ut = UnitType(
        code="US_COMBAT_ENGINEERS_43",
        side=UnitSide.US,
        category=UnitCategory.INFANTRY,
        subtype="COMBAT_ENGINEERS",
        classification="SPECIALIZED_INFANTRY",
        movement=2,
        max_strength=4,
        base_defense={"FRONT": ["YELLOW"]},
        attack={"DIRECT_FIRE": {"INFANTRY": {"0": {"dice": ["RED", "RED"]}}}},
        traits=["EXPLOSIVE_CHARGE", "MINE_DETECTION"],
    )
    return UnitInstance(
        unit_id=unit_id,
        unit_type=ut,
        side="US",
        position=HexCoord(pos[0], pos[1]),
    )


def _make_dummy_target_unit(unit_id="GE_DEF_1", pos=(2, 3), hp=4):
    ut = UnitType(
        code="GE_RIFLES_43",
        side=UnitSide.GE,
        category=UnitCategory.INFANTRY,
        subtype="STANDARD_INFANTRY",
        classification="STANDARD_INFANTRY",
        movement=2,
        max_strength=hp,
        base_defense={"FRONT": ["YELLOW"]},
        attack={},
    )
    inst = UnitInstance(
        unit_id=unit_id,
        unit_type=ut,
        side="GE",
        position=HexCoord(pos[0], pos[1]),
    )
    inst.strength = hp
    return inst


def _build_test_map():
    hexes = []
    for q in range(6):
        for r in range(6):
            hexes.append(Hex(q, r, Terrain.CLEAR))
    return Map(hexes=hexes)


# =============================================================================
# 1. Trait checks on UnitType and UnitInstance
# =============================================================================
def test_unit_has_trait():
    eng = _make_engineer_unit()
    assert eng.has_trait("EXPLOSIVE_CHARGE") is True
    assert eng.has_trait("MINE_DETECTION") is True
    assert eng.has_trait("SNIPER") is False
    assert eng.unit_type.has_trait("EXPLOSIVE_CHARGE") is True


# =============================================================================
# 2. ActionCatalog generation of ExplosiveChargeAction and MineDetectionAction
# =============================================================================
def test_action_catalog_generates_engineer_actions():
    gmap = _build_test_map()
    # (2, 3) is neighbor of (2, 2)
    # Set (2, 3) to have a bunker fortification
    gmap.add_hex_fortification(2, 3, "bunker")
    # Set (3, 2) to have a minefield
    gmap.add_hex_fortification(3, 2, "minefield")
    # Set (1, 2) to be a building
    b_tile = gmap.get_hex(1, 2)
    b_tile.terrain = Terrain.BUILDING_SINGLE

    eng = _make_engineer_unit(pos=(2, 2))
    gs = GameState(units=[eng], game_map=gmap)

    catalog = ActionCatalog(gs, eng, terrain_config=terrain_config)
    actions = catalog.actions()

    # Check ExplosiveChargeAction generated for bunker, building, and minefield
    explosive_actions = [a for a in actions if isinstance(a, ExplosiveChargeAction)]
    exp_targets = {(a.target_hex[0], a.target_hex[1]) for a in explosive_actions}
    assert (2, 3) in exp_targets  # Bunker
    assert (1, 2) in exp_targets  # Building
    assert (3, 2) in exp_targets  # Minefield

    # Check MineDetectionAction generated for minefield at (3, 2)
    mine_actions = [a for a in actions if isinstance(a, MineDetectionAction)]
    mine_targets = {(a.target_hex[0], a.target_hex[1]) for a in mine_actions}
    assert (3, 2) in mine_targets


# =============================================================================
# 3. Explosive Charge Defense Die Selection (Rule 12.5)
# =============================================================================
def test_explosive_charge_defense_die_selection():
    gmap = _build_test_map()
    # Bunker has defense bonus [RED, RED, YELLOW] for infantry -> strongest is RED
    gmap.add_hex_fortification(2, 3, "bunker")
    die = _get_strongest_terrain_defense_die(gmap, 2, 3, "bunker")
    assert die == DiceColor.RED

    # Barbed wire has no defense die -> fallback to GREEN
    gmap.add_hex_fortification(3, 2, "barbed_wire")
    wire_die = _get_strongest_terrain_defense_die(gmap, 3, 2, "barbed_wire")
    assert wire_die == DiceColor.GREEN


# =============================================================================
# 4. Explosive Charge Resolution (Rule 12.5 Table)
# =============================================================================
def test_explosive_charge_collapses_and_eliminates_on_crit_plus_damage():
    gmap = _build_test_map()
    gmap.add_hex_fortification(2, 3, "bunker")
    eng = _make_engineer_unit(pos=(2, 2))
    target = _make_dummy_target_unit(pos=(2, 3), hp=4)
    gs = GameState(units=[eng, target], game_map=gmap)

    act = ExplosiveChargeAction(eng.unit_id, (2, 3), "bunker")

    # Injected rolls:
    # Attacker: RED die with CRITICAL and DAMAGE
    inj_attack = [DiceResult(DiceColor.RED, [DiceFace.CRITICAL, DiceFace.DAMAGE])]
    # Defender: GREEN die with BLANK
    inj_defense = [DiceResult(DiceColor.GREEN, [])]

    res = resolve_explosive_charge(
        action=act,
        attacker=eng,
        game_map=gmap,
        game_state=gs,
        injected_attack_roll=inj_attack,
        injected_defense_roll=inj_defense,
    )

    assert res.outcome == "COLLAPSED_ELIMINATED"
    assert res.structure_collapsed is True
    # Defender inside hex is eliminated
    assert target.hp == 0
    assert not target.alive
    # Bunker collapses to trench side (Rule 12.5)
    assert gmap.get_hex_fortification(2, 3) == "trench"


def test_explosive_charge_destroys_obstacle_on_one_damage():
    gmap = _build_test_map()
    gmap.add_hex_fortification(2, 3, "barbed_wire")
    eng = _make_engineer_unit(pos=(2, 2))
    gs = GameState(units=[eng], game_map=gmap)

    act = ExplosiveChargeAction(eng.unit_id, (2, 3), "barbed_wire")

    # Attacker scores 1 DAMAGE, defender scores BLANK
    inj_attack = [DiceResult(DiceColor.RED, [DiceFace.DAMAGE])]
    inj_defense = [DiceResult(DiceColor.GREEN, [])]

    res = resolve_explosive_charge(
        action=act,
        attacker=eng,
        game_map=gmap,
        game_state=gs,
        injected_attack_roll=inj_attack,
        injected_defense_roll=inj_defense,
    )

    assert res.obstacle_destroyed is True
    # Barbed wire removed from map
    assert gmap.get_hex_fortification(2, 3) is None


# =============================================================================
# 5. Mine Detection Scouting (Rule 9.6.6.2)
# =============================================================================
def test_mine_detection_with_trait_bonus():
    eng = _make_engineer_unit()
    # MINE_DETECTION grants +2
    mod = calculate_detection_modifiers(eng)
    assert mod == 2

    gmap = _build_test_map()
    gmap.add_hex_fortification(2, 3, "minefield")
    act = MineDetectionAction(eng.unit_id, (2, 3))

    # Base infantry target is 5+. With +2 bonus, a roll of 3 gives 3 + 2 = 5 (success)
    res = resolve_mine_detection(
        action=act,
        scout_unit=eng,
        game_map=gmap,
        injected_d6=3,
    )
    assert res.success is True
    assert res.total_score == 5
    assert res.identified is True
    assert gmap.is_hex_fortification_identified(2, 3) is True


def test_mine_detection_removes_dummy_marker_on_success():
    eng = _make_engineer_unit()
    gmap = _build_test_map()
    gmap.add_hex_fortification(2, 3, "dummy_minefield")
    act = MineDetectionAction(eng.unit_id, (2, 3))

    res = resolve_mine_detection(
        action=act,
        scout_unit=eng,
        game_map=gmap,
        injected_d6=4,  # 4 + 2 = 6 >= 5
    )
    assert res.success is True
    assert res.was_dummy is True
    # Dummy marker removed from map
    assert gmap.get_hex_fortification(2, 3) is None


# =============================================================================
# 6. Integration via resolve_action in resolution.py
# =============================================================================
def test_resolve_action_integration():
    gmap = _build_test_map()
    gmap.add_hex_fortification(2, 3, "trench")
    eng = _make_engineer_unit(pos=(2, 2))
    target = _make_dummy_target_unit(pos=(2, 3), hp=3)
    gs = GameState(units=[eng, target], game_map=gmap)

    exp_act = ExplosiveChargeAction(eng.unit_id, (2, 3), "trench")
    res = resolve_action(gs, exp_act)

    assert res.new_state is not None
    assert res.combat_result is not None
    assert isinstance(res.combat_result.outcome, str)
