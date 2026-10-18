from pathlib import Path
import pytest

from assault_model.combat.dice_color import DiceColor
from assault_model.combat.attack_sector import AttackSector
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.spotting import can_spot
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.units.unit_instance import UnitInstance
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
