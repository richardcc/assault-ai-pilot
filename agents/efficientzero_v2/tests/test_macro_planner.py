import pytest
from types import SimpleNamespace

from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner, MacroPlan


def test_macro_planner_posture_and_role_assignment():
    """Verify MacroStrategyPlanner computes postures (ASSAULT, DEFENSE, SUPPRESS) and unit roles."""
    planner = MacroStrategyPlanner()

    # Scenario: Tied VPs -> Should choose ASSAULT_VP on the closest neutral VP
    obs_assault = SimpleNamespace(
        to_play="ALLIES",
        turn=1,
        units=[
            {"unit_id": "u1", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 0, "r": 0, "alive": True},
            {"unit_id": "u2", "unit_key": "US_SUPPORT_MMG", "side": "ALLIES", "q": 0, "r": 1, "alive": True},
            {"unit_id": "e1", "unit_key": "GER_INFANTRY_RIFLES", "side": "AXIS", "q": 5, "r": 5, "alive": True},
        ],
        vp_hexes=[
            {"vp_id": "vp_center", "q": 2, "r": 0},
        ],
        vp_owner_by_hex={},
    )

    plan = planner.compute_macro_plan(obs_assault)
    assert plan.posture == "ASSAULT_VP"
    assert plan.target_vp_id == "vp_center"
    assert plan.target_vp_coords == (2, 0)
    # Unit 1 is close to target VP -> SPEARHEAD
    assert plan.get_role("u1") == "ROLE_SPEARHEAD"
    # Unit 2 is MMG -> FIRE_SUPPORT
    assert plan.get_role("u2") == "ROLE_FIRE_SUPPORT"

    # Prior modulation check
    legal_actions = ["MOVE:u1:1,0", "CAPTURE:u1:2,0", "ATTACK:u2:GER_1", "MOVE:u2:0,2"]
    base_priors = {a: 0.25 for a in legal_actions}
    modulated = planner.modulate_priors(base_priors, plan, legal_actions, {}, "ALLIES")

    # Capture action for Spearhead should receive maximum boost
    assert modulated["CAPTURE:u1:2,0"] > modulated["MOVE:u1:1,0"]
    # Attack action for Fire Support should receive boost
    assert modulated["ATTACK:u2:GER_1"] > modulated["MOVE:u2:0,2"]
    # Sum of priors must remain 1.0
    assert abs(sum(modulated.values()) - 1.0) < 1e-5


def test_macro_planner_defensive_hold_when_leading():
    """Verify MacroStrategyPlanner switches to DEFENSIVE_HOLD when leading in VPs."""
    planner = MacroStrategyPlanner()

    obs_defend = SimpleNamespace(
        to_play="ALLIES",
        turn=3,
        units=[
            {"unit_id": "u1", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 2, "r": 0, "alive": True},
        ],
        vp_hexes=[
            {"vp_id": "vp_1", "q": 2, "r": 0},
            {"vp_id": "vp_2", "q": 8, "r": 8},
        ],
        vp_owner_by_hex={"2,0": "ALLIES"},
    )

    plan = planner.compute_macro_plan(obs_defend)
    assert plan.posture == "DEFENSIVE_HOLD"
    assert plan.friendly_vp_count == 1
    assert plan.enemy_vp_count == 0
    # Unit on the friendly VP should be OBJECTIVE_DEFENDER
    assert plan.get_role("u1") == "ROLE_OBJECTIVE_DEFENDER"


def test_macro_planner_neural_intent_and_dunnigan_reserve():
    """
    Verify MacroStrategyPlanner integrates learned objective_intent_logits,
    multi_vp_pred, and assigns Dunnigan's ROLE_TACTICAL_RESERVE to rear units
    when friendly force has >= 4 units.
    """
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="ALLIES",
        turn=2,
        units=[
            {"unit_id": "u1", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 1, "r": 0, "alive": True},
            {"unit_id": "u2", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 1, "r": 1, "alive": True},
            {"unit_id": "u3", "unit_key": "US_SUPPORT_MMG", "side": "ALLIES", "q": 2, "r": 1, "alive": True},
            {"unit_id": "u_rear", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 9, "r": 9, "alive": True},
            {"unit_id": "e1", "unit_key": "GER_INFANTRY_RIFLES", "side": "AXIS", "q": 2, "r": 0, "alive": True},
        ],
        vp_hexes=[
            {"vp_id": "vp_0", "q": 2, "r": 0},
            {"vp_id": "vp_1", "q": 4, "r": 0},
        ],
        vp_owner_by_hex={"2,0": "AXIS", "4,0": "AXIS"},
    )
    # Neural intent logits strongly favor VP index 1 (vp_1 at (4,0))
    intent_logits = [-2.0, 5.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0]
    multi_vp_pred = [0.2, 0.9, 0.8, 0.5]

    plan = planner.compute_macro_plan(obs, intent_logits=intent_logits, multi_vp_pred=multi_vp_pred)
    assert plan.target_vp_id == "vp_1"
    assert plan.target_vp_coords == (4, 0)
    assert plan.get_role("u_rear") == "ROLE_TACTICAL_RESERVE"

