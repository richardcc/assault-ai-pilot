"""
Unit tests for VPPotentialCalculator and Potential-Based Reward Shaping (Ng et al. 1999).
"""

from __future__ import annotations

import pytest
from voec_sim.core.reward_calculator import VPPotentialCalculator
from agents.efficientzero_v2.core.support import compute_potential_difference



def test_vp_potential_basic_properties():
    calc = VPPotentialCalculator(default_unit_weight=1.0, controlled_vp_bonus=2.0)

    units = [
        {"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0, "doctrine_role": "ROLE_SPEARHEAD"},
        {"side": "US", "alive": True, "hp": 3, "q": 5, "r": 5, "doctrine_role": "ROLE_FIRE_SUPPORT"},
        {"side": "GE", "alive": True, "hp": 3, "q": 10, "r": 10, "doctrine_role": "ROLE_MANEUVER"},
    ]
    vp_hexes = [{"q": 1, "r": 0}, {"q": 10, "r": 10}]
    vp_owner = {"1,0": "NEUTRAL", "10,10": "GE"}

    breakdown = calc.compute_potential(units, vp_hexes, vp_owner, "US")

    assert breakdown.friendly_units_alive == 2
    assert breakdown.controlled_vps == 0
    assert breakdown.uncontrolled_vps_targeted == 2
    assert breakdown.distance_potential > 0.0
    assert breakdown.control_potential == 0.0
    assert breakdown.phi_total == breakdown.distance_potential


def test_vp_potential_closing_distance_increases_phi():
    calc = VPPotentialCalculator(default_unit_weight=1.0, controlled_vp_bonus=2.0)
    vp_hexes = [{"q": 5, "r": 5}]
    vp_owner = {"5,5": "NEUTRAL"}

    far_units = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]
    close_units = [{"side": "US", "alive": True, "hp": 3, "q": 4, "r": 5}]  # Distance 1 vs distance 5

    phi_far = calc.compute_potential(far_units, vp_hexes, vp_owner, "US").phi_total
    phi_close = calc.compute_potential(close_units, vp_hexes, vp_owner, "US").phi_total

    assert phi_close > phi_far


def test_vp_potential_step_shaping_positive_on_advance():
    calc = VPPotentialCalculator(gamma=0.99)
    vp_hexes = [{"q": 5, "r": 5}]
    vp_owner = {"5,5": "NEUTRAL"}

    before_units = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]
    after_units = [{"side": "US", "alive": True, "hp": 3, "q": 4, "r": 5}]

    shaping, meta = calc.compute_step_shaping(
        before_units=before_units,
        after_units=after_units,
        vp_hexes=vp_hexes,
        before_vp_owner=vp_owner,
        after_vp_owner=vp_owner,
        side="US",
        done=False,
    )

    assert shaping > 0.0
    assert meta["phi_after"] > meta["phi_before"]


def test_vp_potential_step_shaping_negative_on_retreat():
    calc = VPPotentialCalculator(gamma=0.99)
    vp_hexes = [{"q": 5, "r": 5}]
    vp_owner = {"5,5": "NEUTRAL"}

    before_units = [{"side": "US", "alive": True, "hp": 3, "q": 4, "r": 5}]
    after_units = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]

    shaping, meta = calc.compute_step_shaping(
        before_units=before_units,
        after_units=after_units,
        vp_hexes=vp_hexes,
        before_vp_owner=vp_owner,
        after_vp_owner=vp_owner,
        side="US",
        done=False,
    )

    assert shaping < 0.0


def test_ng_telescoping_sum_invariance():
    """
    Verifies Ng et al. (1999) invariant:
    The sum of discounted shaping over any trajectory telescopes to:
        sum_{t=0}^{T-1} gamma^t * F(s_t, a_t, s_{t+1}) = -Phi(s_0)
    since Phi(s_T) = 0 on terminal step.
    """
    gamma = 0.95
    calc = VPPotentialCalculator(gamma=gamma)
    vp_hexes = [{"q": 3, "r": 0}]
    vp_owner = {"3,0": "NEUTRAL"}

    # Simulate 3 steps: (0,0) -> (1,0) -> (2,0) -> (3,0) [capture/terminal]
    states = [
        [{"side": "US", "alive": True, "hp": 1, "q": 0, "r": 0}],
        [{"side": "US", "alive": True, "hp": 1, "q": 1, "r": 0}],
        [{"side": "US", "alive": True, "hp": 1, "q": 2, "r": 0}],
        [{"side": "US", "alive": True, "hp": 1, "q": 3, "r": 0}],
    ]

    phi_initial = calc.compute_potential(states[0], vp_hexes, vp_owner, "US").phi_total

    discounted_sum = 0.0
    for t in range(len(states) - 1):
        is_done = (t == len(states) - 2)
        shaping, _ = calc.compute_step_shaping(
            before_units=states[t],
            after_units=states[t + 1],
            vp_hexes=vp_hexes,
            before_vp_owner=vp_owner,
            after_vp_owner={"3,0": "US"} if is_done else vp_owner,
            side="US",
            done=is_done,
        )
        discounted_sum += (gamma ** t) * shaping

    # Theoretical expectation: discounted_sum == -phi_initial
    assert abs(discounted_sum - (-phi_initial)) < 1e-6


def test_turn_urgency_exponential_decay_when_no_vp_controlled():
    """Verify that when 0 VPs are controlled, potential decays exponentially with t/T."""
    calc = VPPotentialCalculator(urgency_decay_lambda=1.2)
    units = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]
    vp_hexes = [{"q": 5, "r": 5}]
    vp_owner = {"5,5": "NEUTRAL"}

    breakdown_t0 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=0, max_turns=8)
    breakdown_t4 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=4, max_turns=8)
    breakdown_t8 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=8, max_turns=8)

    assert breakdown_t0.controlled_vps == 0
    assert breakdown_t0.turn_urgency_factor == 0.0
    assert breakdown_t0.turn_urgency_decay == 1.0

    assert breakdown_t4.turn_urgency_factor == 0.5
    # decay = exp(-1.2 * 0.5) = exp(-0.6) ~ 0.54881
    assert abs(breakdown_t4.turn_urgency_decay - 0.5488116) < 1e-4
    assert breakdown_t4.phi_total < breakdown_t0.phi_total
    assert abs(breakdown_t4.phi_total - (breakdown_t0.phi_total * breakdown_t4.turn_urgency_decay)) < 1e-5

    # At final turn (tau = 1.0), decay = exp(-1.2) ~ 0.30119
    assert abs(breakdown_t8.turn_urgency_decay - 0.3011942) < 1e-4
    assert breakdown_t8.phi_total < breakdown_t4.phi_total


def test_turn_urgency_no_decay_when_vp_controlled():
    """Verify that when at least 1 VP is controlled, turn urgency decay is frozen at 1.0."""
    calc = VPPotentialCalculator(urgency_decay_lambda=1.2)
    units = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]
    vp_hexes = [{"q": 0, "r": 0}, {"q": 5, "r": 5}]
    vp_owner = {"0,0": "US", "5,5": "NEUTRAL"}

    breakdown_t0 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=0, max_turns=8)
    breakdown_t6 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=6, max_turns=8)

    assert breakdown_t6.controlled_vps == 1
    assert breakdown_t6.turn_urgency_decay == 1.0
    assert breakdown_t0.phi_total == breakdown_t6.phi_total


def test_devlin_kudenko_time_dependent_pbrs_telescoping_invariance():
    """
    Verify Devlin & Kudenko (2012) Dynamic PBRS policy invariance:
    Even with time-dependent potentials Phi(s, t) that decay with t/T,
    the discounted shaping sum telescopes strictly to -Phi(s_0, t_0).
    """
    gamma = 0.95
    calc = VPPotentialCalculator(gamma=gamma, urgency_decay_lambda=1.5)
    vp_hexes = [{"q": 4, "r": 0}]
    vp_owner = {"4,0": "NEUTRAL"}

    states = [
        [{"unit_id": "u1", "side": "US", "alive": True, "hp": 1, "q": 0, "r": 0}],
        [{"unit_id": "u1", "side": "US", "alive": True, "hp": 1, "q": 1, "r": 0}],
        [{"unit_id": "u1", "side": "US", "alive": True, "hp": 1, "q": 2, "r": 0}],
        [{"unit_id": "u1", "side": "US", "alive": True, "hp": 1, "q": 3, "r": 0}],
        [{"unit_id": "u1", "side": "US", "alive": True, "hp": 1, "q": 4, "r": 0}],
    ]
    max_turns = 10

    phi_initial = calc.compute_potential(states[0], vp_hexes, vp_owner, "US", turn=0, max_turns=max_turns).phi_total

    discounted_sum = 0.0
    passivity_tracker: dict[str, int] = {}
    for t in range(len(states) - 1):
        is_done = (t == len(states) - 2)
        shaping, meta = calc.compute_step_shaping(
            before_units=states[t],
            after_units=states[t + 1],
            vp_hexes=vp_hexes,
            before_vp_owner=vp_owner,
            after_vp_owner={"4,0": "US"} if is_done else vp_owner,
            side="US",
            done=is_done,
            turn_before=t,
            turn_after=t + 1,
            max_turns=max_turns,
            passivity_tracker=passivity_tracker,
        )
        discounted_sum += (gamma ** t) * meta["pbrs_shaping"]

    # Theoretical expectation under Devlin & Kudenko (2012): discounted PBRS sum telescopes to -phi_initial
    assert abs(discounted_sum - (-phi_initial)) < 1e-5


def test_paralysis_penalty_and_streak_accumulation_and_reset():
    """Verify paralysis penalty accumulation on idle exposed units and reset upon maneuvering/attacking."""
    calc = VPPotentialCalculator(paralysis_penalty_weight=0.1, cover_threshold=0.35)
    target_vps = [(5, 5)]
    controlled_vp_coords = []
    terrain_cover = {"0,0": 0.1, "0,1": 0.2, "1,0": 0.5}  # (0,0) and (0,1) are open (<0.35), (1,0) is heavy cover

    passivity_tracker: dict[str, int] = {}

    unit_idle = [{"unit_id": "u1", "side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]

    # Step 1: Unit stays at (0,0), open cover, does not advance, does not fire
    pen1, cnt1, _ = calc.compute_paralysis_penalty(
        before_units=unit_idle,
        after_units=unit_idle,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vp_coords,
        terrain_cover_by_hex=terrain_cover,
        side="US",
        action_kind="PASS",
        actor_unit_id="u1",
        damage_dealt=0.0,
        passivity_tracker=passivity_tracker,
    )
    assert abs(pen1 - (-0.1)) < 1e-6  # streak = 1 -> mult = 1.0 -> -0.1 * 1.0 = -0.1
    assert cnt1 == 1
    assert passivity_tracker["u1"] == 1

    # Step 2: Still idle in open ground
    pen2, cnt2, _ = calc.compute_paralysis_penalty(
        before_units=unit_idle,
        after_units=unit_idle,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vp_coords,
        terrain_cover_by_hex=terrain_cover,
        side="US",
        action_kind="PASS",
        actor_unit_id="u1",
        damage_dealt=0.0,
        passivity_tracker=passivity_tracker,
    )
    assert abs(pen2 - (-0.15)) < 1e-6  # streak = 2 -> mult = 1.0 + 0.5*(2-1) = 1.5 -> -0.15
    assert cnt2 == 1
    assert passivity_tracker["u1"] == 2

    # Step 3: Action dealing damage resets streak
    pen3, cnt3, _ = calc.compute_paralysis_penalty(
        before_units=unit_idle,
        after_units=unit_idle,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vp_coords,
        terrain_cover_by_hex=terrain_cover,
        side="US",
        action_kind="ATTACK",
        actor_unit_id="u1",
        damage_dealt=2.0,
        passivity_tracker=passivity_tracker,
    )
    assert pen3 == 0.0
    assert cnt3 == 0
    assert passivity_tracker["u1"] == 0

    # Step 4: Unit enters cover (1,0) (cover=0.5 >= 0.35) -> no penalty, streak 0
    unit_in_cover = [{"unit_id": "u1", "side": "US", "alive": True, "hp": 3, "q": 1, "r": 0}]
    pen4, cnt4, _ = calc.compute_paralysis_penalty(
        before_units=unit_in_cover,
        after_units=unit_in_cover,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vp_coords,
        terrain_cover_by_hex=terrain_cover,
        side="US",
        action_kind="PASS",
        actor_unit_id="u1",
        damage_dealt=0.0,
        passivity_tracker=passivity_tracker,
    )
    assert pen4 == 0.0
    assert cnt4 == 0
    assert passivity_tracker["u1"] == 0


def test_vp_intrinsic_value_weighting_potential():
    """
    Verify that VPs with higher intrinsic values (e.g. 3 VP vs 2 VP)
    produce higher distance potential and control potential.
    """
    calc = VPPotentialCalculator(default_unit_weight=1.0, controlled_vp_bonus=2.0)

    # VP1 has standard value 2.0 at (2, 0)
    # VP2 has high value 3.0 at (-2, 0)
    vp_hexes = [
        {"q": 2, "r": 0, "value": 2.0, "vp_id": "vp_standard"},
        {"q": -2, "r": 0, "value": 3.0, "vp_id": "vp_high"},
    ]
    vp_owner_neutral = {"2,0": "NEUTRAL", "-2,0": "NEUTRAL"}

    # Unit advancing towards 2-VP hex: (1, 0) -> dist 1 to VP1, dist 3 to VP2
    unit_towards_vp1 = [{"side": "US", "alive": True, "hp": 3, "q": 1, "r": 0}]
    # Unit advancing towards 3-VP hex: (-1, 0) -> dist 3 to VP1, dist 1 to VP2
    unit_towards_vp2 = [{"side": "US", "alive": True, "hp": 3, "q": -1, "r": 0}]

    phi_towards_vp1 = calc.compute_potential(unit_towards_vp1, vp_hexes, vp_owner_neutral, "US").phi_total
    phi_towards_vp2 = calc.compute_potential(unit_towards_vp2, vp_hexes, vp_owner_neutral, "US").phi_total

    # Advancing towards 3-VP hex must yield higher potential than towards 2-VP hex
    assert phi_towards_vp2 > phi_towards_vp1, (
        f"Potential towards 3-VP hex ({phi_towards_vp2}) must exceed 2-VP hex ({phi_towards_vp1})"
    )

    # Verify control potential: controlling 3-VP hex yields 1.5x control bonus vs 2-VP hex
    vp_owner_ctrl_vp1 = {"2,0": "US", "-2,0": "NEUTRAL"}
    vp_owner_ctrl_vp2 = {"2,0": "NEUTRAL", "-2,0": "US"}

    ctrl_vp1 = calc.compute_potential(unit_towards_vp1, vp_hexes, vp_owner_ctrl_vp1, "US").control_potential
    ctrl_vp2 = calc.compute_potential(unit_towards_vp1, vp_hexes, vp_owner_ctrl_vp2, "US").control_potential

    assert ctrl_vp1 == 2.0  # 1.0 relative value * 2.0 bonus
    assert ctrl_vp2 == 3.0  # 1.5 relative value * 2.0 bonus



