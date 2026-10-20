import math
import pytest
from voec_sim.core.simulator import VOECSimulator
from voec_sim.core.reward_calculator import VPPotentialCalculator
from agents.efficientzero_v2.core.observation import observation_to_tensor
from agents.efficientzero_v2.core.adapter_voec import EZV2Observation


def test_voec_simulator_reward_shaping_and_urgency_integration():
    """
    Test that VOECSimulator with reward_shaping computes PBRS potential,
    turn urgency decay, and paralysis penalty on steps.
    """
    shaping_cfg = {
        "vp_potential_weight": 1.0,
        "vp_potential_gamma": 0.997,
        "vp_potential_ctrl_bonus": 2.0,
        "vp_urgency_lambda": 1.2,
        "paralysis_penalty_weight": 0.05,
        "cover_threshold": 0.35,
    }
    sim = VOECSimulator(reward_shaping=shaping_cfg)
    sim.new_episode(scenario_id="battaglia_cittadina_2_1", seed=42)

    legal = sim.legal_actions()
    assert len(legal) > 0

    first_action = legal[0]
    rec = sim.step(first_action)

    assert "pbrs" in rec.info
    assert "turn_urgency_factor" in rec.info
    assert "turn_urgency_decay" in rec.info
    assert "paralysis_penalty" in rec.info
    assert "paralysis_units_count" in rec.info

    pbrs = rec.info["pbrs"]
    assert "phi_before" in pbrs
    assert "phi_after" in pbrs
    assert "turn_urgency_decay_before" in pbrs
    assert 0.0 <= rec.info["turn_urgency_factor"] <= 1.0
    assert 0.0 < rec.info["turn_urgency_decay"] <= 1.0


def test_turn_urgency_exponential_decay_math():
    """
    Verify the mathematical formulation Psi_urgency(t, T) = exp(-lambda * (t/T))
    strictly holds when friendly side controls 0 VPs, and is bypassed when controlling VPs.
    """
    calc = VPPotentialCalculator(
        controlled_vp_bonus=2.0,
        gamma=0.997,
        shaping_scale=1.0,
        urgency_decay_lambda=1.2,
        paralysis_penalty_weight=0.05,
    )

    friendly_units = [{"side": "AXIS", "alive": True, "hp": 4, "q": 0, "r": 0}]
    vp_hexes = [{"q": 5, "r": 5}]

    # Case 1: 0 VPs controlled -> exponential decay with t/T
    b_early = calc.compute_potential(
        units=friendly_units,
        vp_hexes=vp_hexes,
        vp_owner_by_hex={"5,5": "ALLIED"},
        side="AXIS",
        turn=1,
        max_turns=10,
    )
    b_mid = calc.compute_potential(
        units=friendly_units,
        vp_hexes=vp_hexes,
        vp_owner_by_hex={"5,5": "ALLIED"},
        side="AXIS",
        turn=5,
        max_turns=10,
    )
    b_late = calc.compute_potential(
        units=friendly_units,
        vp_hexes=vp_hexes,
        vp_owner_by_hex={"5,5": "ALLIED"},
        side="AXIS",
        turn=10,
        max_turns=10,
    )

    expected_decay_early = math.exp(-1.2 * 0.1)
    expected_decay_mid = math.exp(-1.2 * 0.5)
    expected_decay_late = math.exp(-1.2 * 1.0)

    assert pytest.approx(b_early.turn_urgency_decay, rel=1e-4) == expected_decay_early
    assert pytest.approx(b_mid.turn_urgency_decay, rel=1e-4) == expected_decay_mid
    assert pytest.approx(b_late.turn_urgency_decay, rel=1e-4) == expected_decay_late
    assert b_early.distance_potential > b_mid.distance_potential > b_late.distance_potential

    # Case 2: 1 VP controlled -> decay is bypassed
    b_ctrl = calc.compute_potential(
        units=friendly_units,
        vp_hexes=vp_hexes,
        vp_owner_by_hex={"5,5": "AXIS"},
        side="AXIS",
        turn=10,
        max_turns=10,
    )
    assert b_ctrl.turn_urgency_decay == 1.0
    assert b_ctrl.control_potential == 2.0


def test_cumulative_paralysis_penalty_streak_and_reset():
    """
    Verify cumulative paralysis penalty on units remaining outside cover without
    maneuvering toward objectives or firing, scaling with consecutive streaks,
    and resetting upon combat action or entering cover.
    """
    calc = VPPotentialCalculator(paralysis_penalty_weight=0.05, cover_threshold=0.35)

    u_before = [{"unit_id": "u1", "side": "AXIS", "alive": True, "hp": 4, "q": 2, "r": 2}]
    u_after_passive = [{"unit_id": "u1", "side": "AXIS", "alive": True, "hp": 4, "q": 2, "r": 2}]
    terrain_open = {"2,2": 0.0}  # Open ground (cover < 0.35)
    target_vps = [(10, 10)]
    controlled_vps = []

    tracker = {}

    # Turn 1: passive in open ground -> streak 1
    pen1, count1, tracker = calc.compute_paralysis_penalty(
        before_units=u_before,
        after_units=u_after_passive,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vps,
        terrain_cover_by_hex=terrain_open,
        side="AXIS",
        action_kind="WAIT",
        actor_unit_id="u1",
        damage_dealt=0.0,
        passivity_tracker=tracker,
    )
    assert count1 == 1
    assert tracker["u1"] == 1
    assert pen1 == -0.05

    # Turn 2: still passive -> streak 2 (scales by +50% -> 1.5x)
    pen2, count2, tracker = calc.compute_paralysis_penalty(
        before_units=u_before,
        after_units=u_after_passive,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vps,
        terrain_cover_by_hex=terrain_open,
        side="AXIS",
        action_kind="WAIT",
        actor_unit_id="u1",
        damage_dealt=0.0,
        passivity_tracker=tracker,
    )
    assert count2 == 1
    assert tracker["u1"] == 2
    assert pytest.approx(pen2, rel=1e-4) == -0.05 * 1.5

    # Turn 3: combat fire action -> streak resets to 0, penalty 0.0
    pen3, count3, tracker = calc.compute_paralysis_penalty(
        before_units=u_before,
        after_units=u_after_passive,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vps,
        terrain_cover_by_hex=terrain_open,
        side="AXIS",
        action_kind="FIRE:u1:target_allied",
        actor_unit_id="u1",
        damage_dealt=1.0,
        passivity_tracker=tracker,
    )
    assert count3 == 0
    assert tracker["u1"] == 0
    assert pen3 == 0.0

    # Turn 4: unit enters heavy cover (cover = 0.50 >= 0.35) -> no penalty
    terrain_cover = {"2,2": 0.50}
    pen4, count4, tracker = calc.compute_paralysis_penalty(
        before_units=u_before,
        after_units=u_after_passive,
        target_vps=target_vps,
        controlled_vp_coords=controlled_vps,
        terrain_cover_by_hex=terrain_cover,
        side="AXIS",
        action_kind="WAIT",
        actor_unit_id="u1",
        damage_dealt=0.0,
        passivity_tracker=tracker,
    )
    assert count4 == 0
    assert tracker["u1"] == 0
    assert pen4 == 0.0


def test_observation_turn_urgency_and_paralysis_encoding():
    """
    Verify Channels 18, 36, and 37 correctly reflect turn urgency pressure
    and paralysis exposure risk.
    """
    obs = EZV2Observation(
        turn=6,
        to_play="AXIS",
        done=False,
        units=[
            {
                "unit_id": "u_open",
                "unit_key": "AXIS_RIFLE",
                "unit_label": "Axis Rifle",
                "side": "AXIS",
                "q": 1,
                "r": 1,
                "hp": 4,
                "alive": True,
                "doctrine_role": "ROLE_SCREEN",
            },
            {
                "unit_id": "u_covered",
                "unit_key": "AXIS_RIFLE",
                "unit_label": "Axis Rifle 2",
                "side": "AXIS",
                "q": 3,
                "r": 3,
                "hp": 4,
                "alive": True,
                "doctrine_role": "ROLE_SPEARHEAD",
            },
        ],
        playable_hexes=[
            {"q": 1, "r": 1},
            {"q": 3, "r": 3},
            {"q": 5, "r": 5},
        ],
        vp_hexes=[{"q": 5, "r": 5}],
        vp_owner_by_hex={"5,5": "ALLIED"},
        terrain_cover_by_hex={
            "1,1": 0.10,  # Exposed open ground (< 0.35)
            "3,3": 0.50,  # Defensible stone building (>= 0.35)
            "5,5": 0.20,
        },
        max_turns=8,
    )

    tensor_38 = observation_to_tensor(obs, channels=38)

    # Channel 36: turn_urgency_pressure
    # t=6, max_turns=8 -> urgency_ratio = 6/8 = 0.75
    ch36 = tensor_38[36]
    assert ch36.max().item() >= 0.75

    # Channel 37: paralysis_exposure_risk
    # Unit at (1,1) has cover 0.10 (< 0.35) -> risk > 0
    # Unit at (3,3) has cover 0.50 (>= 0.35) -> risk == 0
    ch37 = tensor_38[37]
    assert ch37.max().item() > 0.0

    tensor_32 = observation_to_tensor(obs, channels=32)
    # Channel 18: vp_distance_field modulated by urgency
    ch18 = tensor_32[18]
    assert ch18.max().item() > 0.0
