import pytest
from assault_model.combat.close_combat_context import CombatResolutionContext
from assault_model.combat.close_combat_resolver import resolve_close_combat
from assault_model.combat.attack_sector import AttackSector
from assault_model.actions.combat_mode import CombatMode
from assault_model.units.unit_instance import UnitInstance
from assault_model.units.unit_type import UnitType, UnitCategory
from assault_model.combat.dice_color import DiceColor


class MockUnitType:
    def __init__(self, code="RIFLE", cat=UnitCategory.INFANTRY):
        self.code = code
        self.category = cat

    def get_close_combat_attack_dice(self, opp_cat):
        return [DiceColor.GREEN, DiceColor.BLUE]

    def get_defense_dice(self, terrain_name=None):
        return [DiceColor.GREEN]


class MockUnit:
    def __init__(self, unit_id, code="RIFLE"):
        self.unit_id = unit_id
        self.unit_type = MockUnitType(code=code)
        self.strength = 10
        self.alive = True
        self.suppressed = False
        self.position = (0, 0)
        self.activated = False
        self.ambush = False
        self.side = "allies"

    @property
    def hp(self):
        return self.strength

    def apply_damage(self, dmg: int):
        self.strength -= dmg
        if self.strength <= 0:
            self.strength = 0
            self.alive = False

    def apply_suppression(self):
        self.suppressed = True


def test_multi_unit_combined_assault_commit():
    atk_main = MockUnit("ATK_MAIN", "RIFLE")
    defender = MockUnit("DEF_MAIN", "RIFLE")
    ctx = CombatResolutionContext(atk_main, defender, CombatMode.ASSAULT, AttackSector.FRONT)

    # Commit adjacent supporting squad (Palma et al. 2025, Sec. 3.3)
    atk_support = MockUnit("ATK_SUP1", "GE_HEAVY_MG_42")
    ctx.commit_support_unit(atk_support, side="attacker", support_type="flank_suppression")

    assert len(ctx.supporting_attackers) == 1
    assert ctx.supporting_attackers[0] is atk_support

    # Commit defender support
    def_support = MockUnit("DEF_SUP1", "US_RIFLES_43")
    ctx.commit_support_unit(def_support, side="defender", support_type="covering_fire")
    assert len(ctx.supporting_defenders) == 1

    # Resolve close combat round with combined support bonus
    res = resolve_close_combat(ctx)
    assert res.finished is True
    assert len(res.rounds) >= 1
    r1 = res.rounds[0]
    # Attacker should have received a bonus RED die from HMG support (base 2 WHITE + 1 RED = 3 dice)
    assert len(r1.attacker_attack_dice) == 3
    # Defender received a bonus WHITE die from rifle support (base 2 WHITE + 1 WHITE = 3 dice)
    assert len(r1.defender_attack_dice) == 3
