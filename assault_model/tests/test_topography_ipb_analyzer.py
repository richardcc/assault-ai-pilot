import pytest
from types import SimpleNamespace

from assault_model.map.topography_analyzer import (
    Hex5DProfile,
    TopographyProfile,
    TopographyAnalyzer,
    analyze_battlefield_topography,
)
from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner


def test_topography_analyzer_5d_profile_and_classifications():
    """Verify TopographyAnalyzer computes the 5D metric vector and OAKOC classifications."""
    # Synthetic grid with varied terrain
    hex_data = [
        {"q": 0, "r": 0, "terrain": "dense_woods"},
        {"q": 1, "r": 0, "terrain": "building"},
        {"q": 2, "r": 0, "terrain": "clear"},  # Near VP, open -> Killzone candidate
        {"q": 3, "r": 0, "terrain": "clear"},
        {"q": 4, "r": 0, "terrain": "hill_crest"},  # High ground -> Base of Fire candidate
        {"q": 0, "r": 1, "terrain": "trench"},
        {"q": 1, "r": 1, "terrain": "water"},  # Impassable
        {"q": 2, "r": 1, "terrain": "clear"},  # Flanked by water at (1,1) and (3,1) -> Chokepoint
        {"q": 3, "r": 1, "terrain": "water"},  # Impassable
        {"q": 4, "r": 1, "terrain": "clear"},
        {"q": 2, "r": 2, "terrain": "building"},  # Key Terrain (VP)
    ]
    vp_hexes = [{"q": 2, "r": 2, "vp_id": "vp_objective"}]

    analyzer = TopographyAnalyzer()
    profile = analyzer.analyze(hex_data, vp_hexes=vp_hexes, scenario_id="synth_test")

    # 1. Key Terrain check
    assert profile.is_key_terrain(2, 2)
    assert profile.get_classification(2, 2) == "KEY_TERRAIN"

    # 2. Defilade Corridor check (woods or building)
    assert profile.is_defilade(0, 0)
    assert profile.get_classification(0, 0) == "DEFILADE_CORRIDOR"
    prof_woods = profile.hex_profiles[(0, 0)]
    assert prof_woods.cover_rating >= 0.70
    assert prof_woods.los_exposure <= 0.35

    # 3. Killzone check: (2, 0) is open clear terrain close to VP
    assert profile.is_killzone(2, 0)
    prof_kz = profile.hex_profiles[(2, 0)]
    assert prof_kz.cover_rating < 0.35
    assert prof_kz.los_exposure >= 0.60

    # 4. Base of Fire check: (4, 0) is hill_crest commanding elevation overlooking battle
    assert profile.is_base_of_fire(4, 0)
    prof_bof = profile.hex_profiles[(4, 0)]
    assert prof_bof.elevation_dominance >= 0.75

    # 5. Chokepoint check: (2, 1) flanked by water at (1, 1) and (3, 1)
    assert profile.is_chokepoint(2, 1)

    # 6. Serialization contract
    d = profile.to_dict()
    assert "scenario_id" in d
    assert "counts" in d
    assert d["counts"]["key_terrain"] == 1
    assert len(d["hex_profiles"]) == len(hex_data)


def test_macro_planner_topography_integration_and_boosts():
    """Verify MacroStrategyPlanner integrates TopographyProfile into prior modulation."""
    planner = MacroStrategyPlanner()

    hex_data = [
        {"q": 0, "r": 0, "terrain": "clear"},        # Starting point
        {"q": 1, "r": 0, "terrain": "dense_woods"},  # Defilade corridor towards VP
        {"q": 2, "r": 0, "terrain": "building"},     # VP (Key Terrain)
        {"q": 0, "r": 1, "terrain": "clear"},        # Open killzone candidate
        {"q": 1, "r": 1, "terrain": "water"},        # Impassable
        {"q": 2, "r": 1, "terrain": "hill_crest"},   # Base of Fire overlooking VP
    ]
    vp_hexes = [{"q": 2, "r": 0, "vp_id": "vp_target"}]

    obs = SimpleNamespace(
        to_play="US",
        turn=1,
        max_turns=8,
        scenario_id="ipb_test_scenario",
        playable_hexes=hex_data,
        vp_hexes=vp_hexes,
        vp_owner_by_hex={},
        units=[
            {"unit_id": "u_inf", "unit_key": "US_INFANTRY_RIFLES", "side": "US", "q": 0, "r": 0, "alive": True},
            {"unit_id": "u_mg", "unit_key": "US_SUPPORT_MMG", "side": "US", "q": 1, "r": 0, "alive": True},
        ],
    )

    plan = planner.compute_macro_plan(obs)
    assert plan.topography is not None
    assert plan.topography.is_key_terrain(2, 0)
    assert plan.topography.is_defilade(1, 0)
    assert plan.topography.is_base_of_fire(2, 1)

    # 1. Advance through Defilade Corridor towards VP receives reward
    # Moving from (0,0) [d=2] to (1,0) [d=1] -> delta_d = +1
    boost_defilade = planner.compute_action_boost("MOVE:u_inf:1,0", plan, {}, "US", modulation_scale=1.0)
    assert boost_defilade > 1.20

    # 2. Moving laterally into open Killzone without closing distance receives attenuation
    boost_kz = planner.compute_action_boost("MOVE:u_inf:0,1", plan, {}, "US", modulation_scale=1.0)
    assert boost_kz < 1.0

    # 3. Fire Support moving to Base of Fire receives commanding position boost
    plan.unit_roles["u_mg"] = "ROLE_FIRE_SUPPORT"
    boost_bof = planner.compute_action_boost("MOVE:u_mg:2,1", plan, {}, "US", modulation_scale=1.0)
    assert boost_bof > 1.20

    # 4. Pure neural ablation mode (scale=0.0): all boosts must collapse to neutral 1.0
    boost_pure = planner.compute_action_boost("MOVE:u_inf:1,0", plan, {}, "US", modulation_scale=0.0)
    assert boost_pure == 1.0
