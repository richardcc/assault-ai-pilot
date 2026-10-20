from __future__ import annotations

import torch
import pytest
from types import SimpleNamespace

from voec_sim.core.simulator import VOECSimulator
from agents.efficientzero_v2.core.adapter_voec import EZV2VOECAdapter, EZV2Observation
from agents.efficientzero_v2.core.observation import (
    observation_to_tensor,
    encode_doctrine_role,
    DOCTRINE_ROLE_CODES,
    _unit_feature_table,
)
from agents.efficientzero_v2.train.train_engine import _channel_name


def test_doctrine_role_encodings_validity():
    """Verify all canonical roles have distinct normalized floats in (0, 1]."""
    assert len(DOCTRINE_ROLE_CODES) == 5
    for role, code in DOCTRINE_ROLE_CODES.items():
        assert 0.0 < code <= 1.0
        assert encode_doctrine_role(role) == code
        assert encode_doctrine_role(role.lower()) == code

    # Fallback to SCREEN
    assert encode_doctrine_role(None) == DOCTRINE_ROLE_CODES["SCREEN"]
    assert encode_doctrine_role("UNKNOWN_ROLE") == DOCTRINE_ROLE_CODES["SCREEN"]


def test_unit_feature_table_contains_doctrine_fields():
    """Verify that the unit feature table caches doctrine profile metadata."""
    feat = _unit_feature_table()
    table = feat["table"]
    assert len(table) > 0

    for ukey, udata in table.items():
        assert "default_role" in udata
        assert "optimal_range_min" in udata
        assert "optimal_range_max" in udata
        assert "cohesion_weight" in udata
        assert "fallback_threshold_hp" in udata
        assert udata["optimal_range_min"] <= udata["optimal_range_max"]


def test_ezv2_adapter_exposes_doctrine_profile_and_role():
    """Verify EZV2VOECAdapter populates doctrine_role and doctrine_profile in EZV2Observation.units."""
    sim = VOECSimulator()
    adapter = EZV2VOECAdapter(sim)
    obs = adapter.initial_state("battaglia_cittadina_2_1", seed=42)

    assert isinstance(obs, EZV2Observation)
    assert len(obs.units) > 0

    for u in obs.units:
        assert "doctrine_role" in u
        assert "doctrine_profile" in u
        assert u["doctrine_role"] in DOCTRINE_ROLE_CODES
        assert isinstance(u["doctrine_profile"], dict)
        assert "optimal_engagement_range" in u["doctrine_profile"]


def test_observation_tensor_2d_optimal_range_projection():
    """Verify that optimal engagement range projects a 2D footprint in channel 24/25."""
    obs = SimpleNamespace(
        turn=1,
        max_turns=8,
        done=False,
        to_play="ALLIES",
        units=[
            {
                "unit_id": "us_hmg_1",
                "unit_key": "GE_HEAVY_MG_42",
                "side": "ALLIES",
                "q": 0,
                "r": 0,
                "alive": True,
                "hp": 6,
                "doctrine_role": "FIRE_SUPPORT",
                "doctrine_profile": {
                    "default_role": "FIRE_SUPPORT",
                    "optimal_engagement_range": [3, 8],
                },
            },
            {
                "unit_id": "it_mmg_1",
                "unit_key": "IT_BREDA_MMG",
                "side": "AXIS",
                "q": 10,
                "r": 10,
                "alive": True,
                "hp": 6,
                "doctrine_role": "FIRE_SUPPORT",
                "doctrine_profile": {
                    "default_role": "FIRE_SUPPORT",
                    "optimal_engagement_range": [3, 6],
                },
            },
        ],
        playable_hexes=[
            {"q": 0, "r": 0},
            {"q": 1, "r": 0},  # dist 1 (sub-optimal for HMG [3, 8])
            {"q": 3, "r": 0},  # dist 3 (optimal lower bound)
            {"q": 5, "r": 0},  # dist 5 (optimal sweet-spot)
            {"q": 10, "r": 10},
        ],
        vp_hexes=[],
        vp_owner_by_hex={},
        terrain_move_cost_by_hex={},
        terrain_cover_by_hex={},
        terrain_los_block_by_hex={},
    )

    tensor = observation_to_tensor(obs, channels=32, height=16, width=16)

    # Unit cell itself has direct_range_norm
    # And hexes in [3, 8] range receive 2D footprint > 0 in channel 24
    assert float(tensor[24].abs().sum().item()) > 0.0
    # Channel 8 receives FIRE_SUPPORT support weight
    assert float(tensor[8].abs().sum().item()) > 0.0


def test_observation_extended_channels_with_doctrine():
    """Verify that when channels=36, channels 32..35 carry dedicated doctrine channels."""
    obs = SimpleNamespace(
        turn=1,
        max_turns=8,
        done=False,
        to_play="ALLIES",
        units=[
            {
                "unit_id": "us_rangers_1",
                "unit_key": "US_RANGERS_43",
                "side": "ALLIES",
                "q": 0,
                "r": 0,
                "alive": True,
                "hp": 8,
                "doctrine_role": "RECON",
            },
            {
                "unit_id": "ge_grenadiers_1",
                "unit_key": "GE_GRENADIERS_43",
                "side": "AXIS",
                "q": 2,
                "r": 2,
                "alive": True,
                "hp": 8,
                "doctrine_role": "SPEARHEAD",
            },
        ],
        playable_hexes=[
            {"q": 0, "r": 0},
            {"q": 1, "r": 1},
            {"q": 2, "r": 2},
        ],
        vp_hexes=[],
        vp_owner_by_hex={},
        terrain_move_cost_by_hex={},
        terrain_cover_by_hex={},
        terrain_los_block_by_hex={},
    )

    tensor = observation_to_tensor(obs, channels=36, height=16, width=16)
    assert tensor.shape == (36, 16, 16)

    # Channel 32: ally_doctrine_role (RECON = 0.5)
    assert float(tensor[32].abs().sum().item()) > 0.0
    # Channel 33: enemy_doctrine_role (SPEARHEAD = 1.0)
    assert float(tensor[33].abs().sum().item()) > 0.0

    # Semantic names
    assert _channel_name(32) == "ally_doctrine_role"
    assert _channel_name(33) == "enemy_doctrine_role"
    assert _channel_name(34) == "ally_optimal_range_2d"
    assert _channel_name(35) == "enemy_optimal_range_2d"


def test_observation_turn_urgency_and_paralysis_channels():
    """Verify that when channels=38, channels 36 and 37 are populated and channel 18 is modulated."""
    obs = SimpleNamespace(
        turn=4,
        max_turns=8,
        done=False,
        to_play="ALLIES",
        units=[
            {
                "unit_id": "us_rangers_1",
                "unit_key": "US_RANGERS_43",
                "side": "ALLIES",
                "q": 0,
                "r": 0,
                "alive": True,
                "hp": 8,
                "doctrine_role": "RECON",
            },
            {
                "unit_id": "ge_grenadiers_1",
                "unit_key": "GE_GRENADIERS_43",
                "side": "AXIS",
                "q": 5,
                "r": 5,
                "alive": True,
                "hp": 8,
                "doctrine_role": "SPEARHEAD",
            },
        ],
        playable_hexes=[
            {"q": 0, "r": 0},
            {"q": 2, "r": 2},
            {"q": 5, "r": 5},
        ],
        vp_hexes=[{"q": 2, "r": 2}],
        vp_owner_by_hex={"2,2": "AXIS"},
        terrain_move_cost_by_hex={},
        terrain_cover_by_hex={"0,0": 0.1, "2,2": 0.5, "5,5": 0.5},
        terrain_los_block_by_hex={},
    )

    tensor_38 = observation_to_tensor(obs, channels=38, height=16, width=16)
    assert tensor_38.shape == (38, 16, 16)

    # Channel 18: vp_distance_field modulated by (1 + 0.5 * tau)
    # tau = 4/8 = 0.5 -> mult = 1.25
    assert float(tensor_38[18].abs().sum().item()) > 0.0

    # Channel 36: turn_urgency_pressure (tau = 0.5 broadcasted around uncaptured VP)
    assert float(tensor_38[36].abs().sum().item()) > 0.0

    # Channel 37: paralysis_exposure_risk (unit at 0,0 has cover 0.1 < 0.35, dist to VP 2,2 > 0)
    assert float(tensor_38[37].abs().sum().item()) > 0.0

    # Semantic names
    assert _channel_name(36) == "turn_urgency_pressure"
    assert _channel_name(37) == "paralysis_exposure_risk"


def test_default_observation_channels_is_38():
    """Verify DEFAULT_OBS_CHANNELS is 38 and observation_to_tensor defaults to 38 channels."""
    from agents.efficientzero_v2.core.observation import DEFAULT_OBS_CHANNELS
    assert DEFAULT_OBS_CHANNELS == 38

    obs = SimpleNamespace(
        turn=1,
        max_turns=8,
        done=False,
        to_play="ALLIES",
        units=[],
        playable_hexes=[{"q": 0, "r": 0}],
        vp_hexes=[],
        vp_owner_by_hex={},
        terrain_move_cost_by_hex={},
        terrain_cover_by_hex={},
        terrain_los_block_by_hex={},
    )
    t = observation_to_tensor(obs)
    assert t.shape == (38, 16, 16)


def test_observation_tensor_vp_value_scaling():
    """Verify that observation channels 13, 14, and 18 scale with intrinsic VP values."""
    from agents.efficientzero_v2.core.observation import observation_to_tensor

    # VP1 (standard 2.0 VP) at (2, 0) owned by ALLIES
    # VP2 (key 3.0 VP) at (0, 2) owned by AXIS
    obs = SimpleNamespace(
        turn=1,
        max_turns=8,
        done=False,
        to_play="ALLIES",
        units=[],
        playable_hexes=[
            {"q": 0, "r": 0},
            {"q": 1, "r": 0},
            {"q": 0, "r": 1},
            {"q": 2, "r": 0},
            {"q": 0, "r": 2},
        ],
        vp_hexes=[
            {"q": 2, "r": 0, "value": 2.0},
            {"q": 0, "r": 2, "value": 3.0},
        ],
        vp_owner_by_hex={
            "2,0": "ALLIES",
            "0,2": "AXIS",
        },
        terrain_move_cost_by_hex={},
        terrain_cover_by_hex={},
        terrain_los_block_by_hex={},
    )
    tensor = observation_to_tensor(obs, channels=38, height=16, width=16)

    # In observation coordinate mapping: x = q, y = r
    # VP1: q=2, r=0 -> x=2, y=0
    # VP2: q=0, r=2 -> x=0, y=2
    # Channel 13: vp_mask
    assert float(tensor[13, 0, 2].item()) == 1.0  # standard 2 VP -> 1.0
    assert float(tensor[13, 2, 0].item()) == 1.5  # key 3 VP -> 1.5

    # Channel 14: vp_owner_relative (+v_rel for friendly, -v_rel for enemy)
    assert float(tensor[14, 0, 2].item()) == 1.0   # friendly 2 VP -> +1.0
    assert float(tensor[14, 2, 0].item()) == -1.5  # enemy 3 VP -> -1.5

    # Channel 18: vp_distance_field at adjacent hexes
    # Adjacent to VP1 at (1, 0) -> distance 1 from VP1 (2 VP -> v_rel=1.0)
    # Adjacent to VP2 at (0, 1) -> distance 1 from VP2 (3 VP -> v_rel=1.5)
    grad_near_vp1 = float(tensor[18, 0, 1].item())
    grad_near_vp2 = float(tensor[18, 1, 0].item())
    assert grad_near_vp2 > grad_near_vp1, (
        f"Gradient near 3-VP hex ({grad_near_vp2}) must be stronger than near 2-VP hex ({grad_near_vp1})"
    )



