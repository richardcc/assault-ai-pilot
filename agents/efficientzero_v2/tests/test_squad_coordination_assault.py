# agents/efficientzero_v2/tests/test_squad_coordination_assault.py
"""
Test Suite for Roadmap Task 2.4:
Coordinación de Escuadras para Asalto a VPs (Base of Fire + Maneuver Element).
Verifies:
1. Base of Fire boost for ROLE_FIRE_SUPPORT suppressing enemies on/near target VPs.
2. Coordinated assault boost (1.40x) for infantry assaulting suppressed defenders.
3. Anti-suicidal solo charge pruning: solo assault on unsuppressed defender is penalized (0.20x)
   and marked as sterile in MCTS PUCT.
4. Combined squad assault: adjacent friendly squad enables assault on unsuppressed enemy.
5. Close combat resolver CC-006: weakest attack die removed in round 1 for unsuppressed solo frontal assault.
"""

from types import SimpleNamespace
import pytest

from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner, MacroPlan
from assault_model.combat.close_combat_context import CombatResolutionContext
from assault_model.combat.close_combat_resolver import _apply_cc006_unsuppressed_solo_frontal_penalty, resolve_close_combat
from assault_model.combat.dice_color import DiceColor


def test_base_of_fire_boost_on_vp_defender():
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=2,
        max_turns=8,
        friendly_units=[
            {
                "unit_id": "us_mg",
                "unit_key": "US_INF_30CAL",
                "q": 0,
                "r": 0,
                "doctrine_profile": {"canonical_role": "ROLE_FIRE_SUPPORT"},
            }
        ],
        enemy_units=[
            {
                "unit_id": "ge_def_vp",
                "unit_key": "GE_INF_RIFLE",
                "q": 2,
                "r": 1,
                "is_suppressed": False,
            },
            {
                "unit_id": "ge_far",
                "unit_key": "GE_INF_RIFLE",
                "q": 8,
                "r": 8,
                "is_suppressed": False,
            },
        ],
        vp_cells=[{"q": 2, "r": 2, "vp_id": "VP_TOWN"}],
        board_state={"vp_owner_by_hex": {"2,2": "GE"}},
    )
    plan = planner.compute_macro_plan(obs)
    vp_owner = {"2,2": "GE"}

    # Firing on defender adjacent to target VP (Base of Fire)
    bof_boost = planner.compute_action_boost("FIRE:us_mg:ge_def_vp", plan, vp_owner, "US")
    # Firing on distant enemy far from VP
    far_boost = planner.compute_action_boost("FIRE:us_mg:ge_far", plan, vp_owner, "US")

    assert bof_boost > far_boost
    assert pytest.approx(bof_boost, rel=1e-3) == planner.support_boost * 1.35
    assert pytest.approx(far_boost, rel=1e-3) == planner.support_boost


def test_unsuppressed_solo_frontal_assault_penalized_and_sterile():
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=2,
        max_turns=8,
        friendly_units=[
            {
                "unit_id": "us_rifle",
                "unit_key": "US_INF_RIFLE",
                "q": 1,
                "r": 1,
                "doctrine_profile": {"canonical_role": "ROLE_SPEARHEAD"},
            }
        ],
        enemy_units=[
            {
                "unit_id": "ge_guard",
                "unit_key": "GE_INF_RIFLE",
                "q": 2,
                "r": 1,
                "is_suppressed": False,
            }
        ],
        vp_cells=[{"q": 2, "r": 1, "vp_id": "VP_HILL"}],
        board_state={"vp_owner_by_hex": {"2,1": "GE"}},
    )
    plan = planner.compute_macro_plan(obs)
    vp_owner = {"2,1": "GE"}

    # Unsuppressed solo assault
    solo_boost = planner.compute_action_boost("ASSAULT:us_rifle:ge_guard", plan, vp_owner, "US")
    is_sterile = planner.is_sterile_action("ASSAULT:us_rifle:ge_guard", plan, vp_owner, "US")

    # Should be heavily penalized (0.20x) and marked sterile
    assert solo_boost < 0.5
    assert is_sterile is True


def test_coordinated_assault_boost_on_suppressed_enemy():
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=2,
        max_turns=8,
        friendly_units=[
            {
                "unit_id": "us_rifle",
                "unit_key": "US_INF_RIFLE",
                "q": 1,
                "r": 1,
                "doctrine_profile": {"canonical_role": "ROLE_SPEARHEAD"},
            }
        ],
        enemy_units=[
            {
                "unit_id": "ge_suppressed",
                "unit_key": "GE_INF_RIFLE",
                "q": 2,
                "r": 1,
                "is_suppressed": True,  # Suppressed by Base of Fire!
            }
        ],
        vp_cells=[{"q": 2, "r": 1, "vp_id": "VP_HILL"}],
        board_state={"vp_owner_by_hex": {"2,1": "GE"}},
    )
    plan = planner.compute_macro_plan(obs)
    vp_owner = {"2,1": "GE"}

    # Assault on suppressed defender
    coord_boost = planner.compute_action_boost("ASSAULT:us_rifle:ge_suppressed", plan, vp_owner, "US")
    is_sterile = planner.is_sterile_action("ASSAULT:us_rifle:ge_suppressed", plan, vp_owner, "US")

    # Should receive coordinated boost (1.40x) and NOT be sterile
    assert coord_boost > planner.assault_boost
    assert is_sterile is False


def test_combined_assault_with_adjacent_friendly_support():
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=2,
        max_turns=8,
        friendly_units=[
            {
                "unit_id": "us_spearhead",
                "unit_key": "US_INF_RIFLE",
                "q": 1,
                "r": 1,
                "doctrine_profile": {"canonical_role": "ROLE_SPEARHEAD"},
            },
            {
                "unit_id": "us_supporting_squad",
                "unit_key": "US_INF_RIFLE",
                "q": 2,
                "r": 2,  # Adjacent to target at (2,1)
                "doctrine_profile": {"canonical_role": "ROLE_MANEUVER"},
            },
        ],
        enemy_units=[
            {
                "unit_id": "ge_guard",
                "unit_key": "GE_INF_RIFLE",
                "q": 2,
                "r": 1,
                "is_suppressed": False,  # Defender unsuppressed, but friendly squad is adjacent!
            }
        ],
        vp_cells=[{"q": 2, "r": 1, "vp_id": "VP_HILL"}],
        board_state={"vp_owner_by_hex": {"2,1": "GE"}},
    )
    plan = planner.compute_macro_plan(obs)
    vp_owner = {"2,1": "GE"}

    boost = planner.compute_action_boost("ASSAULT:us_spearhead:ge_guard", plan, vp_owner, "US")
    is_sterile = planner.is_sterile_action("ASSAULT:us_spearhead:ge_guard", plan, vp_owner, "US")

    # With friendly support, assault is viable and boosted (1.20x), not pruned
    assert boost >= planner.assault_boost
    assert is_sterile is False


def test_cc006_unsuppressed_solo_frontal_die_penalty():
    from assault_model.actions.combat_mode import CombatMode
    from assault_model.combat.attack_sector import AttackSector

    # 1. Unsuppressed solo frontal assault: drops weakest die
    dice = [DiceColor.RED, DiceColor.YELLOW, DiceColor.BLUE]
    penalized = _apply_cc006_unsuppressed_solo_frontal_penalty(dice)
    # BLUE is weakest in close combat attack hierarchy: RED(4) > YELLOW(3) > GREEN(2) > BLUE(1)
    assert penalized == [DiceColor.RED, DiceColor.YELLOW]

    # 2. In full combat context with penalty enabled:
    atk = SimpleNamespace(unit_id="us_squad", suppressed=False)
    dfn = SimpleNamespace(unit_id="ge_guard", suppressed=False)
    ctx = CombatResolutionContext(
        attacker=atk,
        defender=dfn,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )
    ctx.unsuppressed_solo_frontal_penalty_enabled = True
    assert ctx.is_unsuppressed_solo_frontal_assault is True

    # 3. If defender is suppressed, no penalty
    dfn_suppressed = SimpleNamespace(unit_id="ge_guard", suppressed=True)
    ctx_suppressed = CombatResolutionContext(
        attacker=atk,
        defender=dfn_suppressed,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )
    ctx_suppressed.unsuppressed_solo_frontal_penalty_enabled = True
    assert ctx_suppressed.is_unsuppressed_solo_frontal_assault is False

    # 4. If supported by adjacent friendly squad, no penalty
    ctx_supported = CombatResolutionContext(
        attacker=atk,
        defender=dfn,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FRONT,
    )
    ctx_supported.supporting_attackers = ["us_squad_2"]
    ctx_supported.unsuppressed_solo_frontal_penalty_enabled = True
    assert ctx_supported.is_unsuppressed_solo_frontal_assault is False

    # 5. If flanking / rear assault, no frontal penalty
    ctx_flank = CombatResolutionContext(
        attacker=atk,
        defender=dfn,
        combat_mode=CombatMode.ASSAULT,
        attack_sector=AttackSector.FLANK_LEFT,
    )
    ctx_flank.unsuppressed_solo_frontal_penalty_enabled = True
    assert ctx_flank.is_unsuppressed_solo_frontal_assault is False
