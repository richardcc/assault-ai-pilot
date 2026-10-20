"""
Tests for Roadmap Task 2.2: VP Race Prior Biasing and Sterile Wandering Pruning (~40%).
"""

from __future__ import annotations

from types import SimpleNamespace
import pytest

from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner, MacroPlan
from agents.efficientzero_v2.core.mcts import run_mcts_puct


def test_assault_vp_posture_prior_biasing_and_sterile_pruning():
    planner = MacroStrategyPlanner()

    # Plan with ASSAULT_VP posture towards target VP at (2, 0)
    plan = MacroPlan(
        posture="ASSAULT_VP",
        target_vp_id="vp_1",
        target_vp_coords=(2, 0),
        unit_roles={"u1": "ROLE_SPEARHEAD", "u2": "ROLE_MANEUVER"},
        unit_coords={"u1": (0, 0), "u2": (0, 1)},
    )

    legal_actions = [
        "MOVE:u1:1,0",   # Closes distance to VP (0,0 -> 1,0: dist 2 -> 1, delta = +1)
        "CAPTURE:u1:2,0",# Direct capture/arrival at VP
        "MOVE:u1:-1,0",  # Sterile wandering away from VP (dist 2 -> 3, delta = -1)
        "WAIT:u1",       # Sterile passivity under assault
        "MOVE:u2:0,2",   # u2 moving away from VP
    ]
    vp_owner = {}
    to_play = "US"

    # Verify sterile action identification
    assert planner.is_sterile_action("MOVE:u1:-1,0", plan, vp_owner, to_play) is True
    assert planner.is_sterile_action("WAIT:u1", plan, vp_owner, to_play) is True
    assert planner.is_sterile_action("MOVE:u1:1,0", plan, vp_owner, to_play) is False
    assert planner.is_sterile_action("CAPTURE:u1:2,0", plan, vp_owner, to_play) is False

    # Verify VP race bonus calculation
    bonus_advance = planner.compute_vp_race_bonus("MOVE:u1:1,0", plan, vp_owner, to_play)
    bonus_capture = planner.compute_vp_race_bonus("CAPTURE:u1:2,0", plan, vp_owner, to_play)
    bonus_retreat = planner.compute_vp_race_bonus("MOVE:u1:-1,0", plan, vp_owner, to_play)
    bonus_wait = planner.compute_vp_race_bonus("WAIT:u1", plan, vp_owner, to_play)

    assert bonus_advance > 0.0
    assert bonus_capture >= 1.0
    assert bonus_retreat == 0.0
    assert bonus_wait == 0.0

    # Test prior modulation
    base_priors = {a: 0.20 for a in legal_actions}
    modulated = planner.modulate_priors(base_priors, plan, legal_actions, vp_owner, to_play)

    # In ASSAULT_VP:
    # Advancing actions receive high boost, sterile moves receive ~40% penalty
    assert modulated["CAPTURE:u1:2,0"] > modulated["MOVE:u1:1,0"]
    assert modulated["MOVE:u1:1,0"] > modulated["MOVE:u1:-1,0"]
    assert modulated["MOVE:u1:-1,0"] < base_priors["MOVE:u1:-1,0"]
    assert modulated["WAIT:u1"] < base_priors["WAIT:u1"]
    assert abs(sum(modulated.values()) - 1.0) < 1e-5


def test_run_mcts_puct_vp_race_prior_biasing_and_sterile_pruning():
    legal_actions = ["MOVE:u1:1,0", "MOVE:u1:-1,0", "WAIT:u1"]
    base_priors = {"MOVE:u1:1,0": 0.33, "MOVE:u1:-1,0": 0.33, "WAIT:u1": 0.34}

    vp_race_bonus = {"MOVE:u1:1,0": 0.80, "MOVE:u1:-1,0": 0.0, "WAIT:u1": 0.0}
    sterile_mask = {"MOVE:u1:1,0": False, "MOVE:u1:-1,0": True, "WAIT:u1": True}

    output = run_mcts_puct(
        legal_actions=legal_actions,
        num_simulations=64,
        priors_by_action=base_priors,
        vp_race_prior_biasing=True,
        vp_race_bonus_by_action=vp_race_bonus,
        sterile_action_mask=sterile_mask,
        sterile_prune_penalty=0.40,
    )

    # Sterile branches were pruned
    assert output.sterile_branches_pruned_count == 2
    # Advancing action should receive the vast majority of visits and chosen action
    assert output.chosen_action == "MOVE:u1:1,0"
    advance_idx = legal_actions.index("MOVE:u1:1,0")
    assert output.visits[advance_idx] > sum(output.visits[i] for i in range(len(legal_actions)) if i != advance_idx)

    # Check breakdown metadata
    breakdown = {row["action_id"]: row for row in output.root_candidate_breakdown}
    assert breakdown["MOVE:u1:1,0"]["vp_race_bonus"] == 0.80
    assert breakdown["MOVE:u1:1,0"]["is_sterile"] is False
    assert breakdown["MOVE:u1:-1,0"]["is_sterile"] is True
    assert breakdown["WAIT:u1"]["is_sterile"] is True
