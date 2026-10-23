import math
from types import SimpleNamespace
import pytest

from agents.efficientzero_v2.core.macro_planner import (
    MacroStrategyPlanner,
    compute_macro_modulation_schedule,
)


def test_compute_macro_modulation_schedule():
    """Verify dynamic macro modulation schedule calculations for Task 2.8."""
    # Constant schedule
    assert compute_macro_modulation_schedule(0, 10, schedule="constant", start_scale=1.0) == 1.0
    assert compute_macro_modulation_schedule(5, 10, schedule="constant", start_scale=1.0) == 1.0
    assert compute_macro_modulation_schedule(10, 10, schedule="constant", start_scale=1.0) == 1.0

    # Off / Pure Neural free search
    assert compute_macro_modulation_schedule(0, 10, schedule="off") == 0.0
    assert compute_macro_modulation_schedule(5, 10, schedule="pure_neural") == 0.0
    assert compute_macro_modulation_schedule(10, 10, schedule="zero") == 0.0

    # Linear decay (1.0 -> 0.0 over 10 iterations)
    assert compute_macro_modulation_schedule(0, 10, schedule="linear", start_scale=1.0, final_scale=0.0) == 1.0
    assert compute_macro_modulation_schedule(5, 10, schedule="linear", start_scale=1.0, final_scale=0.0) == 0.5
    assert compute_macro_modulation_schedule(10, 10, schedule="linear", start_scale=1.0, final_scale=0.0) == 0.0

    # Cosine decay (1.0 -> 0.0)
    cos_0 = compute_macro_modulation_schedule(0, 10, schedule="cosine", start_scale=1.0, final_scale=0.0)
    cos_5 = compute_macro_modulation_schedule(5, 10, schedule="cosine", start_scale=1.0, final_scale=0.0)
    cos_10 = compute_macro_modulation_schedule(10, 10, schedule="cosine", start_scale=1.0, final_scale=0.0)
    assert abs(cos_0 - 1.0) < 1e-6
    assert abs(cos_5 - 0.5) < 1e-6
    assert abs(cos_10 - 0.0) < 1e-6

    # Step decay
    assert compute_macro_modulation_schedule(4, 10, schedule="step", start_scale=1.0, final_scale=0.0) == 1.0
    assert compute_macro_modulation_schedule(6, 10, schedule="step", start_scale=1.0, final_scale=0.0) == 0.0

    # Partial decay fraction (completes decay by 50% of iterations)
    assert compute_macro_modulation_schedule(5, 10, schedule="linear", decay_fraction=0.5) == 0.0
    assert compute_macro_modulation_schedule(8, 10, schedule="linear", decay_fraction=0.5) == 0.0


def test_macro_planner_action_boost_modulation_scale():
    """Verify compute_action_boost responds deterministically to modulation_scale."""
    planner = MacroStrategyPlanner()

    obs = SimpleNamespace(
        to_play="ALLIES",
        turn=1,
        units=[
            {"unit_id": "u1", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 0, "r": 0, "alive": True},
            {"unit_id": "e1", "unit_key": "GER_INFANTRY_RIFLES", "side": "AXIS", "q": 5, "r": 5, "alive": True},
        ],
        vp_hexes=[
            {"vp_id": "vp_1", "q": 2, "r": 0},
        ],
        vp_owner_by_hex={},
    )
    plan = planner.compute_macro_plan(obs)

    # Move towards VP (delta_d > 0)
    action_move_vp = "MOVE:u1:1,0"

    # Default scale 1.0: should receive boost > 1.0
    boost_full = planner.compute_action_boost(action_move_vp, plan, {}, "ALLIES", modulation_scale=1.0)
    assert boost_full > 1.0

    # Scale 0.0 (Pure neural mode): must return 1.0 exactly
    boost_zero = planner.compute_action_boost(action_move_vp, plan, {}, "ALLIES", modulation_scale=0.0)
    assert boost_zero == 1.0

    # Scale 0.5: delta over 1.0 must be exactly half
    boost_half = planner.compute_action_boost(action_move_vp, plan, {}, "ALLIES", modulation_scale=0.5)
    assert abs((boost_half - 1.0) - 0.5 * (boost_full - 1.0)) < 1e-6


def test_macro_planner_modulate_priors_ablation():
    """Verify modulate_priors leaves distribution untouched under scale=0.0 and shapes under scale=1.0."""
    planner = MacroStrategyPlanner()

    obs = SimpleNamespace(
        to_play="ALLIES",
        turn=1,
        units=[
            {"unit_id": "u1", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 0, "r": 0, "alive": True},
            {"unit_id": "e1", "unit_key": "GER_INFANTRY_RIFLES", "side": "AXIS", "q": 5, "r": 5, "alive": True},
        ],
        vp_hexes=[
            {"vp_id": "vp_1", "q": 2, "r": 0},
        ],
        vp_owner_by_hex={},
    )
    plan = planner.compute_macro_plan(obs)

    legal_actions = ["MOVE:u1:1,0", "MOVE:u1:0,1", "WAIT:u1"]
    base_priors = {"MOVE:u1:1,0": 0.5, "MOVE:u1:0,1": 0.3, "WAIT:u1": 0.2}

    # Variant A: Pure Neural Free Search (scale=0.0)
    priors_pure = planner.modulate_priors(base_priors, plan, legal_actions, {}, "ALLIES", modulation_scale=0.0)
    assert priors_pure == base_priors

    # Variant B: Doctrinal Shaped (scale=1.0)
    priors_doctrinal = planner.modulate_priors(base_priors, plan, legal_actions, {}, "ALLIES", modulation_scale=1.0)
    # Moving toward VP should receive higher proportion
    assert priors_doctrinal["MOVE:u1:1,0"] > base_priors["MOVE:u1:1,0"]
    # Wait/pass under ASSAULT_VP receives penalty
    assert priors_doctrinal["WAIT:u1"] < base_priors["WAIT:u1"]
    # Sum must remain 1.0
    assert abs(sum(priors_doctrinal.values()) - 1.0) < 1e-6
