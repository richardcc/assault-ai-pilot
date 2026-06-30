from types import SimpleNamespace

from assault_model.actions.status import WaitAction
from assault_model.combat.dice_color import DiceColor
from assault_model.combat.line_of_sight import LineOfSight, check_line_of_sight, clear_los_cache
from assault_model.combat.modifiers.terrain_modifier import TerrainModifier
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.combat.spotting import can_spot
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.map.hex import Hex
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_edge_feature import HexEdgeFeature
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


def _simple_ranged_unit(unit_id: str, side: str, q: int, r: int, *, suppressed: bool = False):
    unit_type = SimpleNamespace(
        category=SimpleNamespace(name="INFANTRY", value="INFANTRY"),
        get_attack_dice=lambda distance, target_category: [DiceColor.RED, DiceColor.BLUE, DiceColor.GREEN],
        get_defense_dice=lambda sector: [],
        _resolve_attack_mode=lambda _distance: "DIRECT_FIRE",
    )
    return SimpleNamespace(
        unit_id=unit_id,
        side=side,
        alive=True,
        hp=10,
        suppressed=suppressed,
        fallback=False,
        position=HexCoord(q, r),
        unit_type=unit_type,
        apply_damage=lambda _dmg: None,
        apply_suppression=lambda: None,
        is_suppressed=lambda: False,
        is_in_fallback=lambda: False,
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


def test_9_6_5_obstacle_crossing_flagged_for_combat_context():
    game_map = Map([Hex(0, 0, Terrain.CLEAR), Hex(1, 0, Terrain.CLEAR)])
    game_map.add_hex_edge_feature((0, 0), (1, 0), HexEdgeFeature.WALL)
    attacker = _simple_ranged_unit("US_1", "US", 0, 0, suppressed=False)
    defender = _simple_ranged_unit("IT_1", "IT", 1, 0, suppressed=False)
    state = GameState(game_map=game_map, units=[attacker, defender], turn=1, victory=None)
    action = SimpleNamespace(unit_id="US_1", target_id="IT_1")
    ctx = state.create_combat_context(action)
    assert ctx.crossed_obstacle is True


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


def test_10_8_attack_modifier_suppressed_attacker_drops_weakest_die(monkeypatch):
    captured_attack_pool = {}

    class _FakeAttackPool:
        def __init__(self, dice):
            captured_attack_pool["dice"] = list(dice)

        def roll(self):
            return []

    class _FakeDefensePool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    monkeypatch.setattr("assault_model.combat.ranged_combat_resolver.AttackDicePool", _FakeAttackPool)
    monkeypatch.setattr("assault_model.combat.ranged_combat_resolver.DefenseDicePool", _FakeDefensePool)
    monkeypatch.setattr(
        "assault_model.combat.ranged_combat_resolver.compare_dice",
        lambda attacker_dice, defender_dice: {
            "remaining_damage": 0,
            "remaining_criticals": 0,
            "remaining_suppress": 0,
        },
    )

    attacker = _simple_ranged_unit("A1", "US", 0, 0, suppressed=True)
    target = _simple_ranged_unit("D1", "IT", 1, 0, suppressed=False)
    action = SimpleNamespace(move_fire_defense_bonus=False, attack_mode="DIRECT_FIRE")
    context = SimpleNamespace(game_map=None, terrain_config=None, event_bus=None)

    resolve_ranged_combat(action=action, attacker=attacker, target=target, distance=2, context=context)

    # Base [RED, BLUE, GREEN] -> suppressed attacker removes weakest die (BLUE).
    assert captured_attack_pool["dice"] == [DiceColor.RED, DiceColor.GREEN]


def test_10_9_defense_modifier_hindered_los_adds_green_die():
    base = [DiceColor.BLUE]
    out = TerrainModifier(defense_bonus=[], los=LineOfSight.HINDERED).modify_defense(base)
    assert out == [DiceColor.BLUE, DiceColor.GREEN]


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
