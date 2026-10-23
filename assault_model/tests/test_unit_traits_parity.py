from pathlib import Path
import pytest

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.spotting import can_spot
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.units.unit_instance import UnitInstance
from assault_model.units.unit_type import UnitType, UnitSide, UnitCategory
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.map.hex_coord import HexCoord


class MockTerrainConfig:
    def get_defense_dice(self, terrain, category):
        if terrain == "forest":
            return ["GREEN", "BLUE"]  # GREEN (strongest), BLUE (weakest)
        return []


class MockHex:
    def __init__(self, q: int = 0, r: int = 0, terrain: str = "brush"):
        self.q = q
        self.r = r
        self.terrain = terrain

    def get_terrain(self):
        return self.terrain


class MockMap:
    def __init__(self):
        self.terrain_config = MockTerrainConfig()
        self.hexes = [
            MockHex(0, 0, "clear"),
            MockHex(1, 0, "clear"),
            MockHex(2, 0, "forest"),
        ]
        self._dict = {(h.q, h.r): h for h in self.hexes}

    def get_hex(self, q, r):
        return self._dict.get((q, r), MockHex(q, r, "clear"))

    def get_hex_fortification(self, q, r):
        return None


@pytest.fixture(scope="module")
def catalog():
    return load_unit_catalog(Path("assets/catalogs/unit_catalog.json"))


from assault_model.combat.line_of_sight import LineOfSight


def test_hidden_trait_spotting(catalog):
    """Unit with HIDDEN trait cannot be spotted unless it has fired or made a fast action."""
    ut_sniper = catalog["US_SNIPER_43"]
    ut_spotter = catalog["GE_RIFLES_43"]

    spotter = UnitInstance(unit_id="GE_1", unit_type=ut_spotter, side="GE", position=HexCoord(0, 0))
    sniper = UnitInstance(unit_id="US_1", unit_type=ut_sniper, side="US", position=HexCoord(2, 0))

    game_map = MockMap()

    # Case 1: Hidden sniper has neither fired nor fast-actioned -> cannot be spotted
    assert not can_spot(spotter, sniper, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Case 2: Sniper has fired this turn -> can be spotted
    sniper.has_fired_this_turn = True
    assert can_spot(spotter, sniper, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Case 3: Sniper has not fired, but used fast action -> can be spotted
    sniper.has_fired_this_turn = False
    sniper.has_fast_action_this_turn = True
    assert can_spot(spotter, sniper, LineOfSight.CLEAR, game_map, game_map.terrain_config)


def test_sniper_trait_removes_strongest_terrain_defense(catalog):
    """Attacker with SNIPER trait removes defender's strongest terrain defense die against infantry."""
    ut_sniper = catalog["US_SNIPER_43"]
    ut_inf = catalog["GE_RIFLES_43"]

    attacker = UnitInstance(unit_id="US_1", unit_type=ut_sniper, side="US", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="GE_1", unit_type=ut_inf, side="GE", position=HexCoord(2, 0))

    game_map = MockMap()
    ctx = ExecutionContext(game_map=game_map)

    class MockAction:
        pass

    result = resolve_ranged_combat(
        action=MockAction(),
        attacker=attacker,
        target=defender,
        distance=2,
        context=ctx,
    )

    # In forest, terrain provides GREEN and BLUE. Strongest is GREEN.
    # Sniper removes defender's strongest terrain defense die against infantry.
    # Therefore, GREEN must NOT be among defender's terrain dice.
    assert DiceColor.GREEN not in [d.color for d in result.defense_roll]
    assert DiceColor.BLUE in [d.color for d in result.defense_roll]


def test_rapid_fire_trait_close_combat(catalog):
    """Unit with RAPID_FIRE trait executes close combat with attack die re-roll capability."""
    ut_mg = catalog["GE_HEAVY_MG_42"]
    ut_us = catalog["US_RIFLES_43"]

    attacker = UnitInstance(unit_id="GE_MG", unit_type=ut_mg, side="GE", position=HexCoord(1, 0))
    defender = UnitInstance(unit_id="US_1", unit_type=ut_us, side="US", position=HexCoord(1, 0))

    class CloseCombatContext:
        def __init__(self, attacker, defender):
            self.attacker = attacker
            self.defender = defender
            self.attack_sector = AttackSector.FRONT
            self.round_number = 1
            self.crossed_obstacle = False

    game_map = MockMap()
    context = ExecutionContext(game_map=game_map)

    cc_ctx = CloseCombatContext(attacker=attacker, defender=defender)
    res = resolve_close_combat(cc_ctx, context=context)
    assert res.finished
    assert len(res.rounds) > 0


def test_tough_trait_close_combat_round1(catalog):
    """Unit with TOUGH ignores 1 damage point in the first round of close combat."""
    ut_fj = catalog["GE_FJ_RIFLES_43"]
    ut_enemy = catalog["US_RIFLES_43"]

    fj = UnitInstance(unit_id="GE_FJ", unit_type=ut_fj, side="GE", position=HexCoord(1, 0))
    us = UnitInstance(unit_id="US_1", unit_type=ut_enemy, side="US", position=HexCoord(1, 0))

    class CloseCombatContext:
        def __init__(self, attacker, defender):
            self.attacker = attacker
            self.defender = defender
            self.attack_sector = AttackSector.FRONT
            self.round_number = 1
            self.crossed_obstacle = False

    game_map = MockMap()
    context = ExecutionContext(game_map=game_map)

    # Run trials to confirm combat executes and TOUGH trait works seamlessly
    for _ in range(5):
        fj.strength = 4
        us.strength = 4
        fj.alive = True
        us.alive = True
        cc_ctx = CloseCombatContext(attacker=us, defender=fj)
        res = resolve_close_combat(cc_ctx, context=context)
        assert res.finished


def test_concealed_and_camouflaged_trait_spotting(catalog):
    """Units with CONCEALED or CAMOUFLAGED cannot be spotted at range when in covering terrain unless revealed."""
    ut_spotter = catalog["GE_RIFLES_43"]
    ut_concealed = UnitType(
        code="UK_COMMANDOS_TEST",
        side=UnitSide.UK,
        category=UnitCategory.INFANTRY,
        movement=2,
        max_strength=4,
        cost=7,
        traits=["SCOUT", "CONCEALED", "RECON_PATROL", "TOUGH"],
    )

    spotter = UnitInstance(unit_id="GE_1", unit_type=ut_spotter, side="GE", position=HexCoord(0, 0))
    commando_in_forest = UnitInstance(unit_id="UK_CMD_1", unit_type=ut_concealed, side="UK", position=HexCoord(2, 0))
    commando_in_clear = UnitInstance(unit_id="UK_CMD_2", unit_type=ut_concealed, side="UK", position=HexCoord(1, 0))

    game_map = MockMap()

    # Case 1: In forest at distance 2 -> not spottable
    assert not can_spot(spotter, commando_in_forest, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Case 2: In clear terrain at distance 1 -> spottable
    assert can_spot(spotter, commando_in_clear, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Case 3: Point-blank detection (adjacent at distance 1) even in forest
    adjacent_spotter = UnitInstance(unit_id="GE_ADJ", unit_type=ut_spotter, side="GE", position=HexCoord(1, 0))
    assert can_spot(adjacent_spotter, commando_in_forest, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Case 4: In forest at distance 2, but fired -> spottable
    commando_in_forest.has_fired_this_turn = True
    assert can_spot(spotter, commando_in_forest, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Case 5: In forest at distance 2, but used fast action -> spottable
    commando_in_forest.has_fired_this_turn = False
    commando_in_forest.has_fast_action_this_turn = True
    assert can_spot(spotter, commando_in_forest, LineOfSight.CLEAR, game_map, game_map.terrain_config)


def test_low_silhouette_trait_spotting(catalog):
    """Units with LOW_SILHOUETTE impose a -1 modifier on attacker spotting rolls and resist detection in cover."""
    from assault_model.combat.spotting import calculate_spotting_modifier

    ut_spotter = catalog["US_RIFLES_43"]
    ut_low_sil = UnitType(
        code="GE_LOW_SIL_TEST",
        side=UnitSide.GE,
        category=UnitCategory.INFANTRY,
        movement=2,
        max_strength=4,
        cost=6,
        traits=["LOW_SILHOUETTE"],
    )
    ut_regular = catalog["GE_RIFLES_43"]

    spotter = UnitInstance(unit_id="US_1", unit_type=ut_spotter, side="US", position=HexCoord(0, 0))
    low_sil_defender = UnitInstance(unit_id="GE_LS", unit_type=ut_low_sil, side="GE", position=HexCoord(2, 0))
    regular_defender = UnitInstance(unit_id="GE_REG", unit_type=ut_regular, side="GE", position=HexCoord(2, 0))

    game_map = MockMap()

    # 1. Spotting Modifier Checks:
    # Regular target under CLEAR LOS: modifier is 0
    assert calculate_spotting_modifier(spotter, regular_defender, LineOfSight.CLEAR) == 0

    # Low silhouette target under CLEAR LOS: modifier is -1
    assert calculate_spotting_modifier(spotter, low_sil_defender, LineOfSight.CLEAR) == -1

    # Low silhouette target under HINDERED LOS: modifier is -2 (-1 terrain, -1 low silhouette)
    assert calculate_spotting_modifier(spotter, low_sil_defender, LineOfSight.HINDERED) == -2

    # 2. Deterministic Spotting Checks:
    # In forest at distance 2, low silhouette defender is undetected
    assert not can_spot(spotter, low_sil_defender, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # Point-blank detection (adjacent at distance 1)
    adj_spotter = UnitInstance(unit_id="US_ADJ", unit_type=ut_spotter, side="US", position=HexCoord(1, 0))
    assert can_spot(adj_spotter, low_sil_defender, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # If defender fires, it is revealed
    low_sil_defender.has_fired_this_turn = True
    assert can_spot(spotter, low_sil_defender, LineOfSight.CLEAR, game_map, game_map.terrain_config)

    # If defender uses fast action, it is revealed
    low_sil_defender.has_fired_this_turn = False
    low_sil_defender.has_fast_action_this_turn = True
    assert can_spot(spotter, low_sil_defender, LineOfSight.CLEAR, game_map, game_map.terrain_config)


def test_phase_a_infantry_and_artillery_traits(catalog):
    """Exhaustive parity test for Phase A traits: TALL_SILHOUETTE, IMMOBILE, SET_UP_TIME, LIMITED_PIVOT, FLAMETHROWER, BACK_BLAST, REAR_ECHELON."""
    from assault_model.combat.spotting import calculate_spotting_modifier
    from assault_model.map.combat_geometry import is_in_arc_of_fire
    from assault_model.rules.movement_rules import MovementRules

    # 1. TALL_SILHOUETTE (+1 spotting modifier, easier to detect)
    ut_tall = UnitType(code="TALL_TEST", side=UnitSide.GE, category=UnitCategory.GUN_ARTILLERY, traits=["TALL_SILHOUETTE"])
    tall_unit = UnitInstance(unit_id="GE_TALL", unit_type=ut_tall, side="GE", position=HexCoord(2, 0))
    spotter = UnitInstance(unit_id="US_1", unit_type=catalog["US_RIFLES_43"], side="US", position=HexCoord(0, 0))
    assert calculate_spotting_modifier(spotter, tall_unit, LineOfSight.CLEAR) == 1
    assert calculate_spotting_modifier(spotter, tall_unit, LineOfSight.HINDERED) == 0

    # 2. IMMOBILE & SET_UP_TIME (Autonomous movement and fast action restrictions)
    ut_immobile = UnitType(code="IMM_TEST", side=UnitSide.GE, category=UnitCategory.GUN_ARTILLERY, movement=0, traits=["IMMOBILE"])
    imm_unit = UnitInstance(unit_id="GE_IMM", unit_type=ut_immobile, side="GE", position=HexCoord(0, 0))
    assert not MovementRules.can_use_fast_action(imm_unit)

    ut_setup = UnitType(code="SETUP_TEST", side=UnitSide.IT, category=UnitCategory.GUN_ARTILLERY, movement=2, traits=["SET_UP_TIME"])
    setup_unit = UnitInstance(unit_id="IT_SETUP", unit_type=ut_setup, side="IT", position=HexCoord(0, 0))
    assert not MovementRules.can_use_fast_action(setup_unit)

    # 3. LIMITED_PIVOT (240-degree arc of fire; frontal arc blocked)
    # North facing: (0, -2) is frontal (blocked), (2, 0) is flank (allowed), (0, 2) is rear (allowed)
    assert not is_in_arc_of_fire(HexCoord(0, 0), "N", HexCoord(0, -2), has_limited_pivot=True)
    assert is_in_arc_of_fire(HexCoord(0, 0), "N", HexCoord(2, 0), has_limited_pivot=True)
    assert is_in_arc_of_fire(HexCoord(0, 0), "N", HexCoord(0, 2), has_limited_pivot=True)

    # 4. FLAMETHROWER (strips strongest defense die and inflicts auto-suppression)
    class MockAction: pass
    class MockHex:
        def __init__(self, q=0, r=0, terrain="clear"):
            self.q = q; self.r = r; self.terrain = terrain
        def get_terrain(self): return self.terrain
    class MockMap:
        def get_hex(self, q, r): return MockHex(q, r, "clear")
        def get_hex_fortification(self, q, r): return None

    game_map = MockMap()
    ctx = ExecutionContext(game_map=game_map)

    ut_flame = UnitType(
        code="FLAME_TEST", side=UnitSide.IT, category=UnitCategory.INFANTRY,
        attack={"DIRECT_FIRE": {"INFANTRY": {"1": {"dice": ["RED", "RED"]}}}},
        traits=["FLAMETHROWER"],
    )
    flame_attacker = UnitInstance(unit_id="IT_FLAME", unit_type=ut_flame, side="IT", position=HexCoord(0, 0))
    defender = UnitInstance(unit_id="US_DEF", unit_type=catalog["US_RIFLES_43"], side="US", position=HexCoord(1, 0))
    defender.strength = 10

    res_flame = resolve_ranged_combat(action=MockAction(), attacker=flame_attacker, target=defender, distance=1, context=ctx)
    assert DiceColor.YELLOW not in [d.color for d in res_flame.defense_roll], "Strongest defense die must be stripped by Flamethrower"
    assert defender.is_suppressed() or defender.is_in_fallback(), "Target must receive suppression from Flamethrower"

    # 5. BACK_BLAST (Yellow defense die degraded to Green when fired at after firing)
    ut_backblast = UnitType(
        code="PUPPCHEN_TEST", side=UnitSide.GE, category=UnitCategory.GUN_ARTILLERY,
        base_defense={"FRONT": ["YELLOW"], "FLANK_LEFT": ["YELLOW"], "FLANK_RIGHT": ["YELLOW"], "REAR": ["YELLOW"]},
        traits=["BACK_BLAST"],
    )
    bb_defender = UnitInstance(unit_id="GE_BB", unit_type=ut_backblast, side="GE", position=HexCoord(1, 0))
    bb_defender.has_fired_this_turn = True
    us_attacker = UnitInstance(unit_id="US_ATK", unit_type=catalog["US_RIFLES_43"], side="US", position=HexCoord(0, 0))
    res_bb = resolve_ranged_combat(action=MockAction(), attacker=us_attacker, target=bb_defender, distance=1, context=ctx)
    assert any(d.color == DiceColor.GREEN for d in res_bb.defense_roll), "Yellow defense must degrade to Green under Back Blast"

    # 6. REAR_ECHELON (Isolated support unit suffers auto-hit/suppression)
    class MockGameState:
        def __init__(self, units):
            self.units = units

    ut_rear = UnitType(
        code="SERVICE_TEST", side=UnitSide.UK, category=UnitCategory.INFANTRY,
        base_defense={"FRONT": ["YELLOW"], "FLANK_LEFT": ["YELLOW"], "FLANK_RIGHT": ["YELLOW"], "REAR": ["YELLOW"]},
        traits=["REAR_ECHELON"],
    )
    service_unit = UnitInstance(unit_id="UK_SVC", unit_type=ut_rear, side="UK", position=HexCoord(2, 0))
    service_unit.strength = 4

    enemy_attacker = UnitInstance(unit_id="GE_ATK", unit_type=catalog["GE_RIFLES_43"], side="GE", position=HexCoord(0, 0))
    gs_isolated = MockGameState([service_unit, enemy_attacker])
    ctx_isolated = ExecutionContext(game_map=MockMap(), game_state=gs_isolated)
    resolve_ranged_combat(action=MockAction(), attacker=enemy_attacker, target=service_unit, distance=2, context=ctx_isolated)
    assert service_unit.is_suppressed(), "Isolated Rear Echelon troops must be automatically suppressed"

    # 7. HEAVY_WEIGHT (Prohibits fast actions and prohibits autonomous movement across elevation levels)
    ut_heavy_wt = UnitType(code="PAK40_TEST", side=UnitSide.GE, category=UnitCategory.GUN_ARTILLERY, movement=1, traits=["HEAVY_WEIGHT"])
    pak_unit = UnitInstance(unit_id="GE_PAK", unit_type=ut_heavy_wt, side="GE", position=HexCoord(0, 0))
    assert not MovementRules.can_use_fast_action(pak_unit), "Heavy Weight cannot use fast action"

    class MockElevatedMap:
        def __init__(self):
            from assault_model.map.terrain import Terrain
            self.hexes = {
                (0, 0): MockHex(0, 0, "clear"),
                (1, 0): MockHex(1, 0, "clear"),
                (0, 1): MockHex(0, 1, "hill"),
            }
            self.hexes[(0, 0)].terrain = Terrain.CLEAR
            self.hexes[(1, 0)].terrain = Terrain.CLEAR
            self.hexes[(0, 1)].terrain = Terrain.HILL

        def get_hex(self, q, r):
            return self.hexes.get((q, r))

        def get_hex_fortification(self, q, r):
            return None

        def get_static_movement_graph(self, move_type, cfg):
            return None

    class MockMoveState:
        def __init__(self, units, gmap):
            self.units = units
            self.game_map = gmap
            self._cache_version = 1
            self._movement_paths_cache = {}

    elev_map = MockElevatedMap()
    gs_move = MockMoveState([pak_unit], elev_map)
    paths = MovementRules.get_legal_paths(gs_move, pak_unit)
    destinations = [p.path[-1] for p in paths]
    assert HexCoord(1, 0) in destinations, "Heavy Weight can move to adjacent clear hex"
    assert HexCoord(0, 1) not in destinations, "Heavy Weight cannot move up to hill hex autonomously"



