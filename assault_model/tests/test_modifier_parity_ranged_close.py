from types import SimpleNamespace

import pytest

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.line_of_sight import LineOfSight
from assault_model.combat.modifiers.terrain_modifier import TerrainModifier
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.critical_table import CRITICAL_TABLE
from assault_model.combat.unit_class import UnitClass
from assault_model.combat.critical_effect import CriticalEffect
from assault_model.combat.ranged_combat_resolver import resolve_critical
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex import Hex
from assault_model.map.map import Map
from assault_model.map.terrain import Terrain
from assault_model.map.hex_edge_feature import HexEdgeFeature
from assault_model.state.game_state import GameState
from assault_model.actions.combat_mode import CombatMode
from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.close_combat_context import CombatResolutionContext
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.dice_face import DiceFace


def _mk_unit(*, unit_id: str, side: str, suppressed: bool = False, category: str = "INFANTRY"):
    unit_type = SimpleNamespace(
        category=SimpleNamespace(name=category, value=category),
        get_attack_dice=lambda distance, target_category: [DiceColor.RED, DiceColor.BLUE, DiceColor.GREEN],
        get_defense_dice=lambda sector: [],
        get_close_combat_attack_dice=lambda _target_category: [DiceColor.RED],
        _resolve_attack_mode=lambda _distance: "DIRECT_FIRE",
        traits=[],
    )
    return SimpleNamespace(
        unit_id=unit_id,
        side=side,
        suppressed=suppressed,
        alive=True,
        hp=10,
        position=HexCoord(0, 0),
        unit_type=unit_type,
        apply_damage=lambda _dmg: None,
        apply_suppression=lambda: None,
        is_suppressed=lambda: False,
        is_in_fallback=lambda: False,
    )


def test_rf001_los_hindered_adds_green_defense_die():
    base = [DiceColor.BLUE]
    mod = TerrainModifier(defense_bonus=[], los=LineOfSight.HINDERED)
    out = mod.modify_defense(base)
    assert out == [DiceColor.BLUE, DiceColor.GREEN]


def test_rf003_terrain_defense_bonus_clear_infantry():
    fake_hex = SimpleNamespace(get_terrain=lambda: "clear")
    infantry = _mk_unit(unit_id="U1", side="US", category="INFANTRY")
    mod = TerrainModifier.from_hex(fake_hex, infantry, los=LineOfSight.CLEAR)
    out = mod.modify_defense([])
    # Canonical table currently defines clear/INFANTRY => [GREEN].
    assert out == [DiceColor.GREEN]


def test_rf002_suppressed_attacker_loses_weakest_die(monkeypatch):
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

    attacker = _mk_unit(unit_id="A1", side="US", suppressed=True, category="INFANTRY")
    target = _mk_unit(unit_id="D1", side="IT", suppressed=False, category="INFANTRY")
    target.position = HexCoord(1, 0)
    action = SimpleNamespace(move_fire_defense_bonus=False, attack_mode="DIRECT_FIRE")
    context = SimpleNamespace(game_map=None, terrain_config=None, event_bus=None)

    resolve_ranged_combat(
        action=action,
        attacker=attacker,
        target=target,
        distance=2,
        context=context,
    )

    # Input [RED, BLUE, GREEN] -> suppressed drops weakest (BLUE).
    assert captured_attack_pool["dice"] == [DiceColor.RED, DiceColor.GREEN]


def test_rf004_fortification_bonus_appended_to_defense_pool(monkeypatch):
    captured_defense_pool = {}

    class _FakeAttackPool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    class _FakeDefensePool:
        def __init__(self, dice):
            captured_defense_pool["dice"] = list(dice)

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
    monkeypatch.setattr(
        "assault_model.combat.ranged_combat_resolver.check_line_of_sight",
        lambda *args, **kwargs: LineOfSight.CLEAR,
    )
    monkeypatch.setattr(
        "assault_model.combat.ranged_combat_resolver.can_spot",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "assault_model.combat.ranged_combat_resolver.FortificationRules.defense_bonus",
        lambda fort_type, unit_category, sector: [DiceColor.YELLOW],
    )

    attacker = _mk_unit(unit_id="A1", side="US", suppressed=False, category="INFANTRY")
    target = _mk_unit(unit_id="D1", side="IT", suppressed=False, category="INFANTRY")
    attacker.position = HexCoord(0, 0)
    target.position = HexCoord(1, 0)
    game_map = SimpleNamespace(
        get_hex=lambda q, r: SimpleNamespace(get_terrain=lambda: "clear"),
        get_hex_fortification=lambda q, r: "trench",
    )
    context = SimpleNamespace(game_map=game_map, terrain_config=None, event_bus=None)
    action = SimpleNamespace(move_fire_defense_bonus=False, attack_mode="DIRECT_FIRE")

    resolve_ranged_combat(
        action=action,
        attacker=attacker,
        target=target,
        distance=2,
        context=context,
    )

    assert DiceColor.YELLOW in captured_defense_pool["dice"]


def test_rf005_spotting_failure_blocks_resolution(monkeypatch):
    class _FailIfCalledAttackPool:
        def __init__(self, _dice):
            raise AssertionError("Attack pool should not be built when spotting fails")

    class _FailIfCalledDefensePool:
        def __init__(self, _dice):
            raise AssertionError("Defense pool should not be built when spotting fails")

    monkeypatch.setattr("assault_model.combat.ranged_combat_resolver.AttackDicePool", _FailIfCalledAttackPool)
    monkeypatch.setattr("assault_model.combat.ranged_combat_resolver.DefenseDicePool", _FailIfCalledDefensePool)
    monkeypatch.setattr(
        "assault_model.combat.ranged_combat_resolver.check_line_of_sight",
        lambda *args, **kwargs: LineOfSight.HINDERED,
    )
    monkeypatch.setattr(
        "assault_model.combat.ranged_combat_resolver.can_spot",
        lambda *args, **kwargs: False,
    )

    attacker = _mk_unit(unit_id="A1", side="US", suppressed=False, category="INFANTRY")
    target = _mk_unit(unit_id="D1", side="IT", suppressed=False, category="INFANTRY")
    attacker.position = HexCoord(0, 0)
    target.position = HexCoord(1, 0)
    game_map = SimpleNamespace(
        get_hex=lambda q, r: SimpleNamespace(get_terrain=lambda: "clear"),
        get_hex_fortification=lambda q, r: None,
    )
    context = SimpleNamespace(game_map=game_map, terrain_config=None, event_bus=None)
    action = SimpleNamespace(move_fire_defense_bonus=False, attack_mode="DIRECT_FIRE")

    result = resolve_ranged_combat(
        action=action,
        attacker=attacker,
        target=target,
        distance=2,
        context=context,
    )

    assert result.attack_roll == []
    assert result.defense_roll == []
    assert result.criticals == []


def test_cr002_vehicle_critical_table_maps_to_damaged():
    assert CRITICAL_TABLE[UnitClass.VEHICLE] == CriticalEffect.DAMAGED


def test_cr001_infantry_artillery_critical_mapping():
    inf = resolve_critical(DiceFace.CRITICAL, UnitClass.INFANTRY)
    art = resolve_critical(DiceFace.CRITICAL, UnitClass.ARTILLERY)
    assert inf["effect"] == CriticalEffect.ELIMINATED.value
    assert art["effect"] == CriticalEffect.SUPPRESSED.value


def test_cr003_building_fortification_route_not_modeled_yet():
    # Current combat model has no UnitClass for building/fortification targets.
    # This keeps CR-003 explicitly visible as a model gap.
    unit_class_names = {u.name for u in UnitClass}
    assert "BUILDING" not in unit_class_names
    assert "FORTIFICATION" not in unit_class_names


def test_cc001_crossed_obstacle_flag_is_set_in_context():
    attacker = _mk_unit(unit_id="A1", side="US", category="INFANTRY")
    defender = _mk_unit(unit_id="D1", side="IT", category="INFANTRY")
    attacker.position = HexCoord(0, 0)
    defender.position = HexCoord(1, 0)

    game_map = Map([Hex(0, 0, Terrain.CLEAR), Hex(1, 0, Terrain.CLEAR)])
    game_map.add_hex_edge_feature((0, 0), (1, 0), HexEdgeFeature.WALL)
    state = GameState(game_map=game_map, units=[attacker, defender], turn=1, victory=None)
    action = SimpleNamespace(unit_id="A1", target_id="D1", combat_mode=CombatMode.ASSAULT)

    ctx = state.create_combat_context(action)
    assert ctx.crossed_obstacle is True


def test_cc001_obstacle_crossing_removes_weakest_attack_die_round1(monkeypatch):
    captured_first_attacker_attack = {}

    class _FakeAttackPool:
        call_idx = 0

        def __init__(self, dice):
            _FakeAttackPool.call_idx += 1
            # First AttackDicePool call per round is attacker_attack.
            if _FakeAttackPool.call_idx == 1:
                captured_first_attacker_attack["dice"] = list(dice)

        def roll(self):
            return []

    class _FakeDefensePool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    monkeypatch.setattr("assault_model.combat.close_combat_resolver.AttackDicePool", _FakeAttackPool)
    monkeypatch.setattr("assault_model.combat.close_combat_resolver.DefenseDicePool", _FakeDefensePool)
    monkeypatch.setattr(
        "assault_model.combat.close_combat_resolver.compare_dice",
        lambda attacker_dice, defender_dice: {
            "remaining_damage": 0,
            "remaining_criticals": 0,
            "remaining_suppress": 0,
        },
    )

    attacker = _mk_unit(unit_id="A1", side="US", category="INFANTRY")
    defender = _mk_unit(unit_id="D1", side="IT", category="INFANTRY")
    ctx = CombatResolutionContext(
        attacker=attacker,
        defender=defender,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )
    ctx.crossed_obstacle = True

    resolve_close_combat(ctx=ctx, context=SimpleNamespace(game_map=None, event_bus=None))

    # _mk_unit close-combat dice = [RED]; CC-001 removes weakest => empty pool.
    assert captured_first_attacker_attack["dice"] == []


def test_cc003_activated_penalty_removes_weakest_attack_die_round1(monkeypatch):
    captured_first_attacker_attack = {}

    class _FakeAttackPool:
        call_idx = 0

        def __init__(self, dice):
            _FakeAttackPool.call_idx += 1
            if _FakeAttackPool.call_idx == 1:
                captured_first_attacker_attack["dice"] = list(dice)

        def roll(self):
            return []

    class _FakeDefensePool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    monkeypatch.setattr("assault_model.combat.close_combat_resolver.AttackDicePool", _FakeAttackPool)
    monkeypatch.setattr("assault_model.combat.close_combat_resolver.DefenseDicePool", _FakeDefensePool)
    monkeypatch.setattr(
        "assault_model.combat.close_combat_resolver.compare_dice",
        lambda attacker_dice, defender_dice: {
            "remaining_damage": 0,
            "remaining_criticals": 0,
            "remaining_suppress": 0,
        },
    )

    attacker = _mk_unit(unit_id="A1", side="US", category="INFANTRY")
    attacker.activated = True
    defender = _mk_unit(unit_id="D1", side="IT", category="INFANTRY")
    # make attack pool richer for weakest-die check
    attacker.unit_type.get_close_combat_attack_dice = lambda _target_category: [DiceColor.RED, DiceColor.GREEN]
    ctx = CombatResolutionContext(
        attacker=attacker,
        defender=defender,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )

    resolve_close_combat(ctx=ctx, context=SimpleNamespace(game_map=None, event_bus=None))

    # Activated penalty removes weakest (GREEN), keeps RED.
    assert captured_first_attacker_attack["dice"] == [DiceColor.RED]


def test_cc002_outflank_reroll_applies_in_flank_or_rear(monkeypatch):
    # Deterministic setup: initial attacker die misses, reroll gives damage.
    class _FakeAttackPool:
        call_idx = 0

        def __init__(self, _dice):
            _FakeAttackPool.call_idx += 1
            self.which = _FakeAttackPool.call_idx

        def roll(self):
            if self.which == 1:
                # attacker attack
                return [DiceResult(DiceColor.RED, tuple())]
            # defender attack
            return []

    class _FakeDefensePool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    class _FakeBattleDie:
        def __init__(self, color):
            self.color = color

        def roll(self):
            return DiceResult(self.color, (DiceFace.DAMAGE,))

    monkeypatch.setattr("assault_model.combat.close_combat_resolver.AttackDicePool", _FakeAttackPool)
    monkeypatch.setattr("assault_model.combat.close_combat_resolver.DefenseDicePool", _FakeDefensePool)
    monkeypatch.setattr("assault_model.combat.close_combat_resolver.BattleDie", _FakeBattleDie)
    monkeypatch.setattr(
        "assault_model.combat.close_combat_resolver.compare_dice",
        lambda attacker_dice, defender_dice: {
            "remaining_damage": 0,
            "remaining_criticals": 0,
            "remaining_suppress": 0,
        },
    )

    attacker = _mk_unit(unit_id="A1", side="US", category="INFANTRY")
    defender = _mk_unit(unit_id="D1", side="IT", category="INFANTRY")
    ctx = CombatResolutionContext(
        attacker=attacker,
        defender=defender,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.REAR,
    )

    result = resolve_close_combat(ctx=ctx, context=SimpleNamespace(game_map=None, event_bus=None))
    first_round = result.rounds[0]
    assert len(first_round.attacker_attack_dice) == 1
    assert first_round.attacker_attack_dice[0].faces == (DiceFace.DAMAGE,)


def test_cc004_suppressed_attacker_loses_weakest_attack_die(monkeypatch):
    captured_first_attacker_attack = {}

    class _FakeAttackPool:
        call_idx = 0

        def __init__(self, dice):
            _FakeAttackPool.call_idx += 1
            if _FakeAttackPool.call_idx == 1:
                captured_first_attacker_attack["dice"] = list(dice)

        def roll(self):
            return []

    class _FakeDefensePool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    monkeypatch.setattr("assault_model.combat.close_combat_resolver.AttackDicePool", _FakeAttackPool)
    monkeypatch.setattr("assault_model.combat.close_combat_resolver.DefenseDicePool", _FakeDefensePool)
    monkeypatch.setattr(
        "assault_model.combat.close_combat_resolver.compare_dice",
        lambda attacker_dice, defender_dice: {
            "remaining_damage": 0,
            "remaining_criticals": 0,
            "remaining_suppress": 0,
        },
    )

    attacker = _mk_unit(unit_id="A1", side="US", category="INFANTRY")
    attacker.suppressed = True
    attacker.unit_type.get_close_combat_attack_dice = lambda _target_category: [DiceColor.RED, DiceColor.GREEN]
    defender = _mk_unit(unit_id="D1", side="IT", category="INFANTRY")
    ctx = CombatResolutionContext(
        attacker=attacker,
        defender=defender,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )

    resolve_close_combat(ctx=ctx, context=SimpleNamespace(game_map=None, event_bus=None))
    assert captured_first_attacker_attack["dice"] == [DiceColor.RED]


def test_cc005_ambush_adds_green_attack_die_round1(monkeypatch):
    captured_first_attacker_attack = {}

    class _FakeAttackPool:
        call_idx = 0

        def __init__(self, dice):
            _FakeAttackPool.call_idx += 1
            if _FakeAttackPool.call_idx == 1:
                captured_first_attacker_attack["dice"] = list(dice)

        def roll(self):
            return []

    class _FakeDefensePool:
        def __init__(self, _dice):
            pass

        def roll(self):
            return []

    monkeypatch.setattr("assault_model.combat.close_combat_resolver.AttackDicePool", _FakeAttackPool)
    monkeypatch.setattr("assault_model.combat.close_combat_resolver.DefenseDicePool", _FakeDefensePool)
    monkeypatch.setattr(
        "assault_model.combat.close_combat_resolver.compare_dice",
        lambda attacker_dice, defender_dice: {
            "remaining_damage": 0,
            "remaining_criticals": 0,
            "remaining_suppress": 0,
        },
    )

    attacker = _mk_unit(unit_id="A1", side="US", category="INFANTRY")
    attacker.ambush = True
    attacker.unit_type.get_close_combat_attack_dice = lambda _target_category: [DiceColor.RED]
    defender = _mk_unit(unit_id="D1", side="IT", category="INFANTRY")
    ctx = CombatResolutionContext(
        attacker=attacker,
        defender=defender,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )

    resolve_close_combat(ctx=ctx, context=SimpleNamespace(game_map=None, event_bus=None))
    assert captured_first_attacker_attack["dice"] == [DiceColor.RED, DiceColor.GREEN]
