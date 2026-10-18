from assault_model.combat.dice_color import DiceColor
from assault_model.combat.dice_face import DiceFace
from assault_model.combat.battle_die import DiceResult
from assault_model.combat.ranged_combat_resolver import resolve_ranged_combat
from assault_model.units.unit_type import UnitType, UnitCategory, UnitSide
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.runtime.execution_context import ExecutionContext


class MockUnit:
    def __init__(self, unit_id, unit_type, position, hp=4):
        self.unit_id = unit_id
        self.unit_type = unit_type
        self.position = position
        self.hp = hp
        self.alive = True
        self.facing = "N"
        self.suppressed = False
        self.spotted_enemies = []

    def is_suppressed(self):
        return self.suppressed

    def apply_damage(self, amount):
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.alive = False


class MockHex:
    def __init__(self, terrain="forest"):
        self.terrain = terrain

    def get_terrain(self):
        return self.terrain


class MockMap:
    def __init__(self):
        self.hexes = {}

    def get_hex(self, q, r):
        return self.hexes.get((q, r), MockHex("forest"))

    def get_hex_fortification(self, q, r):
        return None


def test_indirect_fire_profile_compilation():
    ut = UnitType(
        code="TEST_MORTAR",
        side=UnitSide.US,
        category=UnitCategory.INFANTRY,
        attack={
            "INDIRECT_FIRE": {
                "3-8": {"dice": ["GREEN", "GREEN", "BLUE"]},
                "defense_loss": "WEAKEST_TERRAIN",
                "reroll": True,
            },
            "DIRECT_FIRE": {"INFANTRY": {"0-2": {"dice": ["YELLOW"]}}},
        },
    )
    assert ut.indirect_fire_profile is not None
    assert ut.indirect_fire_profile["defense_loss"] == "WEAKEST_TERRAIN"
    assert ut.indirect_fire_profile["reroll"] is True
    # Range bands shouldn't include defense_loss or reroll
    assert ut._mode_ranges["INDIRECT_FIRE"] == [(3, 8)]


def test_indirect_fire_reroll_and_defense_loss(monkeypatch):
    attacker_type = UnitType(
        code="TEST_GRENADES",
        side=UnitSide.GE,
        category=UnitCategory.INFANTRY,
        classification="INDIRECT_FIRE_UNIT",
        attack={
            "INDIRECT_FIRE": {
                "1-3": {"dice": ["GREEN"]},
                "defense_loss": "WEAKEST_TERRAIN",
                "reroll": True,
            },
            "DIRECT_FIRE": {"INFANTRY": {"0-1": {"dice": ["YELLOW"]}}},
        },
    )
    target_type = UnitType(
        code="TEST_DEFENDER",
        side=UnitSide.US,
        category=UnitCategory.INFANTRY,
        base_defense={"FRONT": ["YELLOW"], "FLANK_LEFT": ["YELLOW"], "FLANK_RIGHT": ["YELLOW"], "REAR": ["YELLOW"]},
        attack={"DIRECT_FIRE": {"INFANTRY": {"0": {"dice": []}}}},
    )

    from assault_model.map.hex_coord import HexCoord

    attacker = MockUnit("ATTACKER", attacker_type, HexCoord(0, 0))
    target = MockUnit("TARGET", target_type, HexCoord(0, 2))

    gmap = MockMap()
    ctx = ExecutionContext(game_map=gmap)

    action = RangedIndirectAttack("ATTACKER", (0, 2))
    action.attack_mode = "INDIRECT_FIRE"

    # Verify combat resolution runs cleanly with indirect properties active
    res = resolve_ranged_combat(action=action, attacker=attacker, target=target, distance=2, context=ctx)
    assert res is not None
    assert len(res.attack_roll) == 1
