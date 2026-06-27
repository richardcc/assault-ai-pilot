from types import SimpleNamespace

from assault_model.actions.status import WaitAction
from assault_model.combat.line_of_sight import LineOfSight, check_line_of_sight, clear_los_cache
from assault_model.combat.spotting import can_spot
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.map.hex import Hex
from assault_model.map.hex_coord import HexCoord
from assault_model.map.terrain import Terrain
from assault_model.map.terrain_config import terrain_config
from assault_model.map.map import Map
from assault_model.rules.fortification_rules import FortificationRules
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.state.game_state import GameState
from assault_model.units.unit_instance import UnitInstance


def _simple_runtime_unit(unit_id: str, side: str, q: int, r: int):
    return SimpleNamespace(
        unit_id=unit_id,
        side=side,
        alive=True,
        suppressed=False,
        fallback=False,
        position=HexCoord(q, r),
    )


def test_6_4_and_8_1_wait_advances_activation_side():
    game_map = Map([Hex(0, 0, Terrain.CLEAR), Hex(1, 0, Terrain.CLEAR)])
    units = [_simple_runtime_unit("A_1", "A", 0, 0), _simple_runtime_unit("B_1", "B", 1, 0)]
    state = GameState(game_map=game_map, units=units, turn=1, victory=None)
    scenario = SimpleNamespace(terrain_config=terrain_config, max_turns=None, victory_outcomes={})
    rt = RuntimeGameState(base_state=state, scenario=scenario)
    assert rt.active_side == "A"
    rt.apply_action(WaitAction("A_1"))
    assert rt.active_side == "B"


def test_9_4_move_cost_clear_foot():
    assert terrain_config.get_move_cost("clear", "foot") == 1


def test_9_6_4_fortification_trench_front_bonus_exists_for_infantry():
    bonus = FortificationRules.defense_bonus(
        fort_type="trench",
        unit_category="INFANTRY",
        sector=SimpleNamespace(name="FRONT"),
    )
    assert len(bonus) >= 1


def test_9_7_objective_hex_control_switches_to_occupying_side():
    game_map = Map([Hex(0, 0, Terrain.CLEAR)])
    units = [_simple_runtime_unit("US_1", "US", 0, 0)]
    victory = VictoryConditions.from_json({"value_per_hex": 1, "hexes": [[0, 0]]})
    state = GameState(game_map=game_map, units=units, turn=1, victory=victory)
    state.recalculate_hex_control()
    hs = state.hex_states[(0, 0)]
    assert hs.ownership == state.side_to_ownership["US"]


def test_10_2_10_4_los_blocked_through_building():
    clear_los_cache()
    game_map = Map(
        [
            Hex(0, 0, Terrain.CLEAR),
            Hex(1, 0, Terrain.BUILDING_SINGLE),
            Hex(2, 0, Terrain.CLEAR),
        ]
    )
    attacker = SimpleNamespace(position=HexCoord(0, 0))
    target = SimpleNamespace(position=HexCoord(2, 0))
    los = check_line_of_sight(attacker, target, game_map, terrain_config)
    assert los == LineOfSight.BLOCKED


def test_10_2_10_4_los_hindered_through_brush():
    clear_los_cache()
    game_map = Map(
        [
            Hex(0, 0, Terrain.CLEAR),
            Hex(1, 0, Terrain.BRUSH),
            Hex(2, 0, Terrain.CLEAR),
        ]
    )
    attacker = SimpleNamespace(position=HexCoord(0, 0))
    target = SimpleNamespace(position=HexCoord(2, 0))
    los = check_line_of_sight(attacker, target, game_map, terrain_config)
    assert los == LineOfSight.HINDERED


def test_10_5_spotting_can_fail_on_hindered_target_hex():
    game_map = Map(
        [
            Hex(0, 0, Terrain.CLEAR),
            Hex(1, 0, Terrain.BRUSH),
            Hex(2, 0, Terrain.BRUSH),
        ]
    )
    attacker = SimpleNamespace(position=HexCoord(0, 0))
    target = SimpleNamespace(position=HexCoord(2, 0))
    visible = can_spot(attacker, target, LineOfSight.HINDERED, game_map, terrain_config)
    assert visible is False


def test_13_3_suppression_then_fallback_transition():
    unit_type = SimpleNamespace(max_strength=6, category=SimpleNamespace(name="INFANTRY"))
    u = UnitInstance(
        unit_id="U1",
        unit_type=unit_type,
        side="US",
        position=(0, 0),
        experience="REGULAR",
    )
    u.apply_suppression()
    assert u.is_suppressed() is True
    u.apply_suppression()
    assert u.is_in_fallback() is True
