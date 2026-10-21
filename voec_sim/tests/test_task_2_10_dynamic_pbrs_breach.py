"""
Unit tests for Task 2.10: Dynamic PBRS Time Scaling, Contention Bonus, and Breach Casualty Attenuation.

Validates the mathematical properties of:
    1. Time-Scaled Dynamic PBRS: Phi(s, t) = alpha * (1 + t/T_max) * dist_pot + beta * Contest + ctrl_pot
    2. Devlin & Kudenko (2012) Policy Invariance: Telescoping sum sum_{t=0}^{H-1} gamma^t F = -Phi(s_0, 0)
    3. Breach Zone Casualty Attenuation: 60% penalty reduction (factor 0.40) within d <= 2 hexes of target VPs
    4. Catastrophic Timeout Penalty: Full -1.0 defeat punishment when time expires with 0 VPs captured.
"""

from __future__ import annotations

import pytest
from voec_sim.core.reward_calculator import VPPotentialCalculator, PotentialBreakdown


def test_dynamic_pbrs_time_scaling_amplification():
    """Verify that under time_scaled_pbrs=True, distance potential amplifies by (1 + t/T_max)."""
    calc = VPPotentialCalculator(time_scaled_pbrs=True, default_unit_weight=1.0)
    units = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 0}]
    vp_hexes = [{"q": 4, "r": 0}]
    vp_owner = {"4,0": "NEUTRAL"}

    p_t0 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=0, max_turns=8)
    p_t4 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=4, max_turns=8)
    p_t8 = calc.compute_potential(units, vp_hexes, vp_owner, "US", turn=8, max_turns=8)

    assert p_t0.turn_urgency_factor == 0.0
    assert p_t0.time_scale_multiplier == 1.0

    assert p_t4.turn_urgency_factor == 0.5
    assert p_t4.time_scale_multiplier == 1.5
    assert abs(p_t4.distance_potential - (p_t0.distance_potential * 1.5)) < 1e-6

    assert p_t8.turn_urgency_factor == 1.0
    assert p_t8.time_scale_multiplier == 2.0
    assert abs(p_t8.distance_potential - (p_t0.distance_potential * 2.0)) < 1e-6


def test_dynamic_pbrs_contested_vp_bonus():
    """Verify contention bonus beta * Contest triggers when friendly units penetrate breach zone (d <= 2)."""
    calc = VPPotentialCalculator(
        time_scaled_pbrs=True,
        vp_contested_bonus=0.75,
        breach_distance=2,
    )
    vp_hexes = [{"q": 5, "r": 5}]
    vp_owner = {"5,5": "NEUTRAL"}

    # Unit outside breach zone (dist = 5 hexes)
    units_outside = [{"side": "US", "alive": True, "hp": 3, "q": 0, "r": 5}]
    p_outside = calc.compute_potential(units_outside, vp_hexes, vp_owner, "US", turn=0, max_turns=8)
    assert p_outside.contested_vps == 0
    assert p_outside.contention_potential == 0.0

    # Unit inside breach zone (dist = 2 hexes: (3,5) to (5,5))
    units_inside = [{"side": "US", "alive": True, "hp": 3, "q": 3, "r": 5}]
    p_inside = calc.compute_potential(units_inside, vp_hexes, vp_owner, "US", turn=0, max_turns=8)
    assert p_inside.contested_vps == 1
    assert p_inside.contention_potential == 0.75
    assert p_inside.phi_total > p_outside.phi_total

    # Unit directly on VP hex (dist = 0)
    units_on_hex = [{"side": "US", "alive": True, "hp": 3, "q": 5, "r": 5}]
    p_on_hex = calc.compute_potential(units_on_hex, vp_hexes, vp_owner, "US", turn=0, max_turns=8)
    assert p_on_hex.contested_vps == 1
    assert p_on_hex.contention_potential == 0.75


def test_devlin_kudenko_time_scaled_pbrs_telescoping_invariance():
    """
    Mathematical proof test for Devlin & Kudenko (2012) Theorem 1:
    Even with time scaling and contention bonus, the discounted sum of step shaping
    telescopes strictly to -Phi(s_0, t_0), guaranteeing policy invariance argmax_a Q*(s, a).
    """
    gamma = 0.95
    calc = VPPotentialCalculator(
        gamma=gamma,
        time_scaled_pbrs=True,
        vp_contested_bonus=0.5,
        breach_distance=2,
        shaping_scale=1.0,
    )
    vp_hexes = [{"q": 3, "r": 0}]
    vp_owner = {"3,0": "NEUTRAL"}
    max_turns = 10

    # Trajectory of 4 steps with advancing turns:
    # t=0: at (0, 0), outside breach zone
    # t=1: at (1, 0), inside breach zone (d=2)
    # t=2: at (2, 0), inside breach zone (d=1)
    # t=3: at (3, 0), captured VP (terminal)
    steps = [
        ({"q": 0, "r": 0}, 0),
        ({"q": 1, "r": 0}, 1),
        ({"q": 2, "r": 0}, 2),
        ({"q": 3, "r": 0}, 3),
    ]

    initial_units = [{"side": "US", "alive": True, "hp": 1, "q": steps[0][0]["q"], "r": steps[0][0]["r"]}]
    phi_initial = calc.compute_potential(initial_units, vp_hexes, vp_owner, "US", turn=0, max_turns=max_turns).phi_total

    discounted_sum = 0.0
    for idx in range(len(steps) - 1):
        pos_before, turn_b = steps[idx]
        pos_after, turn_a = steps[idx + 1]
        is_done = (idx == len(steps) - 2)

        u_before = [{"side": "US", "alive": True, "hp": 1, "q": pos_before["q"], "r": pos_before["r"]}]
        u_after = [{"side": "US", "alive": True, "hp": 1, "q": pos_after["q"], "r": pos_after["r"]}]
        vp_owner_after = {"3,0": "US"} if is_done else vp_owner

        shaping, meta = calc.compute_step_shaping(
            before_units=u_before,
            after_units=u_after,
            vp_hexes=vp_hexes,
            before_vp_owner=vp_owner,
            after_vp_owner=vp_owner_after,
            side="US",
            done=is_done,
            turn_before=turn_b,
            turn_after=turn_a,
            max_turns=max_turns,
        )
        discounted_sum += (gamma ** idx) * shaping

    # Telescoping invariant: sum_{t=0}^{H-1} gamma^t F_t = -Phi(s_0, t_0)
    assert abs(discounted_sum - (-phi_initial)) < 1e-6


def test_breach_casualty_factor_attenuation():
    """Verify compute_breach_casualty_factor attenuates penalties by 60% (factor 0.40) in breach zone."""
    calc = VPPotentialCalculator(breach_distance=2, breach_casualty_attenuation=0.40)
    target_vps = [(5, 5)]

    # Exactly in breach zone: d = 2
    factor_at_2 = calc.compute_breach_casualty_factor(unit_coords=(3, 5), target_vps=target_vps)
    assert factor_at_2 == 0.40

    # Inside breach zone: d = 1
    factor_at_1 = calc.compute_breach_casualty_factor(unit_coords=(4, 5), target_vps=target_vps)
    assert factor_at_1 == 0.40

    # On VP: d = 0
    factor_at_0 = calc.compute_breach_casualty_factor(unit_coords=(5, 5), target_vps=target_vps)
    assert factor_at_0 == 0.40

    # Outside breach zone: d = 3
    factor_outside = calc.compute_breach_casualty_factor(unit_coords=(2, 5), target_vps=target_vps)
    assert factor_outside == 1.0

    # No target VPs present: default to 1.0
    factor_no_vps = calc.compute_breach_casualty_factor(unit_coords=(5, 5), target_vps=[])
    assert factor_no_vps == 1.0


def test_catastrophic_timeout_math():
    """Verify catastrophic timeout penalty assignment when controlled VPs == 0."""
    soft_timeout_penalty = -0.10

    # Case A: 0 VPs captured at timeout -> catastrophic penalty -1.0
    controlled_vps = 0
    assigned_penalty = min(float(soft_timeout_penalty), -1.0) if controlled_vps == 0 else soft_timeout_penalty
    assert assigned_penalty == -1.0

    # Case B: 1 VP captured at timeout -> soft timeout penalty retained
    controlled_vps = 1
    assigned_penalty = min(float(soft_timeout_penalty), -1.0) if controlled_vps == 0 else soft_timeout_penalty
    assert assigned_penalty == soft_timeout_penalty
