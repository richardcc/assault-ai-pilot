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


def test_macro_planner_hyde_cohesion_bua_and_anti_pursuit():
    """
    Verify Henry Hyde (2015) Wargaming Compendium transfers:
    1. SUPPORTED (<=3 hexes) vs. ISOLATED (>6 hexes) proximity cohesion tiers.
    2. 50% Strength Retirement (ROLE_RECOVER) in open terrain vs. BUA Desperation in fortified buildings.
    3. Anti-Impetuous Pursuit guardrail preventing OBJECTIVE_DEFENDER from abandoning captured VPs.
    """
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="ALLIES",
        turn=4,
        units=[
            # u_def holds captured VP at (2,0)
            {"unit_id": "u_def", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 2, "r": 0, "alive": True, "strength": 6, "max_strength": 6},
            # u_hurt is in open terrain at (3,0) (within 1 hex of u_def -> SUPPORTED) but below 50% strength (2/6) -> ROLE_RECOVER
            {"unit_id": "u_hurt", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 3, "r": 0, "alive": True, "strength": 2, "max_strength": 6},
            # u_bua is below 50% strength (2/6) at (4,0) inside a fortified stone BUA -> fights on (ROLE_SPEARHEAD, not ROLE_RECOVER)
            {"unit_id": "u_bua", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 4, "r": 0, "alive": True, "strength": 2, "max_strength": 6},
            # u_iso is isolated at (12,12) (>6 hexes from all friends -> ISOLATED)
            {"unit_id": "u_iso", "unit_key": "US_INFANTRY_RIFLES", "side": "ALLIES", "q": 12, "r": 12, "alive": True, "strength": 6, "max_strength": 6},
        ],
        vp_hexes=[
            {"vp_id": "vp_home", "q": 2, "r": 0},
            {"vp_id": "vp_target", "q": 5, "r": 0},
        ],
        vp_owner_by_hex={"2,0": "ALLIES", "5,0": "AXIS"},
        terrain_cover_by_hex={"4,0": 0.45},
        terrain_los_block_by_hex={"4,0": 0.60},
        fortification_type_by_hex={"4,0": "bunker"},
    )

    plan = planner.compute_macro_plan(obs)
    assert plan.get_role("u_def") == "ROLE_OBJECTIVE_DEFENDER"
    assert plan.get_role("u_hurt") == "ROLE_RECOVER"
    assert plan.get_role("u_bua") == "ROLE_SPEARHEAD"
    assert plan.get_cohesion("u_def") == "SUPPORTED"
    assert plan.get_cohesion("u_iso") == "ISOLATED"

    # Anti-pursuit & anti-isolation modulation check
    legal = [
        "DEFEND:u_def:2,0",
        "MOVE:u_def:3,1",       # Abandoning captured VP -> penalized
        "RALLY:u_hurt:3,0",     # Recovering below 50% -> boosted
        "ASSAULT:u_hurt:5,0",   # Frontal assault below 50% -> penalized
        "MOVE:u_iso:10,10",     # Moving closer to friends -> boosted
        "MOVE:u_iso:14,14",     # Moving deeper into isolation -> penalized
    ]
    base_priors = {a: 1.0 / len(legal) for a in legal}
    mod = planner.modulate_priors(base_priors, plan, legal, {"2,0": "ALLIES"}, "ALLIES")

    assert mod["DEFEND:u_def:2,0"] > mod["MOVE:u_def:3,1"]
    assert mod["RALLY:u_hurt:3,0"] > mod["ASSAULT:u_hurt:5,0"]
    assert mod["MOVE:u_iso:10,10"] > mod["MOVE:u_iso:14,14"]


def test_macro_planner_colon_action_and_vp_capture_detection():
    """Verify colon-formatted engine actions (e.g. MOVE:u1:2:0) correctly detect VP captures and approach."""
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=1,
        units=[
            {"unit_id": "US_1", "unit_key": "US_RIFLES_43", "side": "US", "q": 0, "r": 9, "alive": True},
            {"unit_id": "US_2", "unit_key": "US_RIFLES_43", "side": "US", "q": 1, "r": 9, "alive": True},
        ],
        vp_hexes=[
            {"vp_id": "IT_VP_1", "q": 2, "r": 6},
            {"vp_id": "US_VP_1", "q": 8, "r": 9},
        ],
        vp_owner_by_hex={"2,6": "IT", "8,9": "US"},
    )
    plan = planner.compute_macro_plan(obs)
    assert plan.posture == "ASSAULT_VP"
    assert plan.target_vp_id == "IT_VP_1"
    assert plan.target_vp_coords == (2, 6)

    # Actions formatted with colons as in real engine:
    # MOVE:US_1:2:6 is moving directly into the enemy VP (capture)
    # MOVE:US_1:1:8 is advancing towards the enemy VP (closer)
    # MOVE:US_1:0:10 is moving away/backwards
    legal = [
        "MOVE:US_1:2:6",
        "MOVE:US_1:1:8",
        "MOVE:US_1:0:10",
    ]
    base_priors = {a: 1.0 / len(legal) for a in legal}
    mod = planner.modulate_priors(base_priors, plan, legal, {"2,6": "IT", "8,9": "US"}, "US")

    # Direct capture into enemy VP gets highest boost
    assert mod["MOVE:US_1:2:6"] > mod["MOVE:US_1:1:8"]
    # Advancing closer gets higher boost than moving backwards
    assert mod["MOVE:US_1:1:8"] > mod["MOVE:US_1:0:10"]


def test_dynamic_mutation_rule_1_vp_deficit_spearhead():
    """Verify Rule 1: Units with allow_spearhead_if_vp_deficit mutate to SPEARHEAD when behind in VPs."""
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=5,
        max_turns=6,  # Late game: turn 5 of 6
        units=[
            {
                "unit_id": "screen_1",
                "unit_key": "GE_RIFLES_43",
                "side": "US",
                "q": 0,
                "r": 0,
                "alive": True,
                "doctrine_profile": {
                    "default_role": "SCREEN",
                    "mutation_rules": {"allow_spearhead_if_vp_deficit": True},
                },
            },
            {
                "unit_id": "support_no_mut",
                "unit_key": "US_81MM_MORTAR",
                "side": "US",
                "q": 0,
                "r": 1,
                "alive": True,
                "doctrine_profile": {
                    "default_role": "FIRE_SUPPORT",
                    "mutation_rules": {"allow_spearhead_if_vp_deficit": False},
                },
            },
        ],
        vp_hexes=[
            {"vp_id": "enemy_vp", "q": 3, "r": 0},
        ],
        vp_owner_by_hex={"3,0": "GE"},  # Friendly: 0, Enemy: 1 -> Deficit!
    )
    plan = planner.compute_macro_plan(obs)

    # screen_1 mutates to SPEARHEAD due to VP deficit
    assert plan.get_role("screen_1") == "ROLE_SPEARHEAD"
    assert plan.is_mutated("screen_1") is True
    assert plan.get_mutation_reason("screen_1") == "VP_DEFICIT_PRESSURE"

    # support_no_mut does NOT mutate because allow_spearhead_if_vp_deficit is False
    assert plan.get_role("support_no_mut") == "ROLE_FIRE_SUPPORT"
    assert plan.is_mutated("support_no_mut") is False
    assert plan.get_mutation_reason("support_no_mut") == "DEFAULT_PROFILE"


def test_dynamic_mutation_rule_2_morale_degradation_recovery():
    """Verify Rule 2: Suppressed or low-HP spearhead units mutate to RECOVER."""
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="US",
        turn=2,
        units=[
            {
                "unit_id": "spearhead_suppressed",
                "unit_key": "US_AIRBORNE_RIFLES_43",
                "side": "US",
                "q": 1,
                "r": 0,
                "alive": True,
                "suppressed": True,
                "hp": 4,
                "max_strength": 4,
                "doctrine_profile": {
                    "default_role": "SPEARHEAD",
                    "fallback_threshold_hp": 2,
                },
            },
            {
                "unit_id": "spearhead_critically_wounded",
                "unit_key": "US_AIRBORNE_RIFLES_43",
                "side": "US",
                "q": 2,
                "r": 0,
                "alive": True,
                "hp": 1,
                "strength": 1,
                "max_strength": 4,
                "doctrine_profile": {
                    "default_role": "SPEARHEAD",
                    "fallback_threshold_hp": 2,  # hp <= 2 triggers recover
                },
            },
            {
                "unit_id": "spearhead_healthy",
                "unit_key": "US_AIRBORNE_RIFLES_43",
                "side": "US",
                "q": 3,
                "r": 0,
                "alive": True,
                "hp": 4,
                "max_strength": 4,
                "doctrine_profile": {
                    "default_role": "SPEARHEAD",
                    "fallback_threshold_hp": 1,
                },
            },
        ],
        vp_hexes=[
            {"vp_id": "vp_obj", "q": 4, "r": 0},
        ],
        vp_owner_by_hex={},
    )
    plan = planner.compute_macro_plan(obs)

    # Suppressed spearhead mutates to ROLE_RECOVER
    assert plan.get_role("spearhead_suppressed") == "ROLE_RECOVER"
    assert plan.is_mutated("spearhead_suppressed") is True
    assert plan.get_mutation_reason("spearhead_suppressed") == "MORALE_OR_HEALTH_DEGRADATION"

    # Critically wounded spearhead mutates to ROLE_RECOVER
    assert plan.get_role("spearhead_critically_wounded") == "ROLE_RECOVER"
    assert plan.is_mutated("spearhead_critically_wounded") is True
    assert plan.get_mutation_reason("spearhead_critically_wounded") == "MORALE_OR_HEALTH_DEGRADATION"

    # Healthy spearhead stays SPEARHEAD
    assert plan.get_role("spearhead_healthy") == "ROLE_SPEARHEAD"
    assert plan.is_mutated("spearhead_healthy") is False


def test_dynamic_mutation_rule_3_flanked_close_defense():
    """Verify Rule 3: Heavy fire support flanked by adjacent enemy without escort mutates to CLOSE_DEFENSE."""
    planner = MacroStrategyPlanner()
    obs = SimpleNamespace(
        to_play="ALLIES",
        turn=2,
        units=[
            # Heavy MG at (0, 0)
            {
                "unit_id": "hmg_flanked",
                "unit_key": "GE_HEAVY_MG_42",
                "side": "ALLIES",
                "q": 0,
                "r": 0,
                "alive": True,
                "hp": 6,
                "doctrine_profile": {
                    "default_role": "FIRE_SUPPORT",
                    "optimal_engagement_range": [3, 8],
                    "mutation_rules": {"allow_close_defense_on_flank": True},
                },
            },
            # Friendly escort far away at (5, 5) (> 1 hex)
            {
                "unit_id": "friendly_far",
                "unit_key": "US_RIFLES_43",
                "side": "ALLIES",
                "q": 5,
                "r": 5,
                "alive": True,
            },
            # Adjacent enemy infantry at (1, 0) (distance 1 hex)
            {
                "unit_id": "enemy_adjacent",
                "unit_key": "IT_RIFLES_43",
                "side": "AXIS",
                "q": 1,
                "r": 0,
                "alive": True,
            },
        ],
        vp_hexes=[],
        vp_owner_by_hex={},
    )
    plan = planner.compute_macro_plan(obs)

    # Flanked heavy weapon mutates to ROLE_CLOSE_DEFENSE
    assert plan.get_role("hmg_flanked") == "ROLE_CLOSE_DEFENSE"
    assert plan.is_mutated("hmg_flanked") is True
    assert plan.get_mutation_reason("hmg_flanked") == "FLANKED_CLOSE_DEFENSE"

    # Prior modulation check for CLOSE_DEFENSE
    legal = [
        "DEFEND:hmg_flanked:0,0",
        "ATTACK:hmg_flanked:enemy_adjacent",
        "MOVE:hmg_flanked:1,1",  # Rejoining towards friendly_far at (5,5)
        "MOVE:hmg_flanked:-1,-1",  # Moving away deeper into isolated void
    ]
    base_priors = {a: 0.25 for a in legal}
    mod = planner.modulate_priors(base_priors, plan, legal, {}, "ALLIES")

    # Defense and close-combat fire receive boost
    assert mod["DEFEND:hmg_flanked:0,0"] > mod["MOVE:hmg_flanked:-1,-1"]
    assert mod["ATTACK:hmg_flanked:enemy_adjacent"] > mod["MOVE:hmg_flanked:-1,-1"]
    # Rejoining friendly escort gets higher boost than moving away into isolation
    assert mod["MOVE:hmg_flanked:1,1"] > mod["MOVE:hmg_flanked:-1,-1"]
    # Sum of priors is normalized
    assert abs(sum(mod.values()) - 1.0) < 1e-5


def test_macro_planner_vp_value_prioritization():
    """
    Verify that MacroPlanner prioritizes uncaptured VPs with higher intrinsic values
    when distance is equal.
    """
    planner = MacroStrategyPlanner()

    # Friendly unit at (0, 0)
    # VP1 (standard 2.0 VP) at (2, 0) -> distance 2
    # VP2 (high 3.0 VP) at (0, 2) -> distance 2
    obs = SimpleNamespace(
        to_play="US",
        units=[
            {"unit_id": "u1", "side": "US", "q": 0, "r": 0, "hp": 3, "alive": True},
        ],
        vp_hexes=[
            {"q": 2, "r": 0, "value": 2.0, "vp_id": "vp_standard_2"},
            {"q": 0, "r": 2, "value": 3.0, "vp_id": "vp_high_3"},
        ],
        vp_owner_by_hex={
            "2,0": "NEUTRAL",
            "0,2": "NEUTRAL",
        },
    )

    plan = planner.compute_macro_plan(obs)

    # MacroPlanner must select the 3-VP hex (0, 2) over the 2-VP hex (2, 0)
    assert plan.target_vp_coords == (0, 2)
    assert plan.target_vp_id == "vp_high_3"




