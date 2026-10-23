"""
Unit and Integration Tests for Causal Profiler and Forensic SitRep Service.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mlops.reporting.causal_profiler import (
    build_forensic_sitrep,
    correlate_tactical_heads,
    detect_turning_points,
    generate_executive_narrative,
    get_or_compute_causal_sitrep,
)


def _make_dummy_step(
    step: int = 0,
    turn: int = 1,
    side: str = "US",
    unit_id: str = "US_01",
    vp_map: dict[str, str] | None = None,
    damage_dealt: float = 0.0,
    kills_dealt: int = 0,
    enemy_damage: float = 0.0,
    suppressed: bool = False,
    threat_val: float = 0.1,
    target_vp: str = "",
) -> dict[str, Any]:
    return {
        "step": step,
        "turn": turn,
        "to_play": side,
        "unit_id": unit_id,
        "unit_side": side,
        "action_id": f"FIRE:{unit_id}:0:0",
        "action_kind": "FIRE",
        "target_q": 1,
        "target_r": 2,
        "vp_map": vp_map or {"0,0": ""},
        "vp_map_after": vp_map or {"0,0": ""},
        "damage_dealt": damage_dealt,
        "kills_dealt": kills_dealt,
        "enemy_damage": enemy_damage,
        "unit_suppressed_map": {unit_id: suppressed},
        "unit_alive_map": {unit_id: True},
        "unit_hp_map": {unit_id: 3.0},
        "obs_enemy_reaction_fire_risk": threat_val,
        "target_vp": target_vp,
    }


def test_detect_turning_points_vp_capture():
    steps = [
        _make_dummy_step(step=0, turn=1, vp_map={"1,1": ""}),
        _make_dummy_step(step=1, turn=1, vp_map={"1,1": "US"}),
        _make_dummy_step(step=2, turn=2, vp_map={"1,1": "IT"}),
    ]
    tps = detect_turning_points(steps)
    assert len(tps) == 2
    assert tps[0].event_type == "VP_CAPTURE"
    assert tps[0].actor_side == "US"
    assert tps[1].event_type == "VP_CAPTURE"
    assert tps[1].actor_side == "IT"
    assert tps[1].target_side == "US"
    assert tps[1].severity == "CRITICAL"


def test_detect_turning_points_elimination_and_attrition():
    steps = [
        _make_dummy_step(step=0, turn=1, damage_dealt=3.0, kills_dealt=1),
        _make_dummy_step(step=1, turn=1, damage_dealt=2.5, kills_dealt=0),
    ]
    tps = detect_turning_points(steps)
    assert len(tps) == 2
    types = [tp.event_type for tp in tps]
    assert "UNIT_ELIMINATION" in types
    assert "HEAVY_ATTRITION" in types


def test_detect_turning_points_morale_failure():
    steps = [
        _make_dummy_step(step=0, turn=1, unit_id="US_01", suppressed=False),
        _make_dummy_step(step=1, turn=1, unit_id="US_01", suppressed=True),
    ]
    tps = detect_turning_points(steps)
    assert len(tps) == 1
    assert tps[0].event_type == "MORALE_FAILURE"
    assert tps[0].severity == "HIGH"
    assert "US_01" in tps[0].description


def test_detect_turning_points_surprise_ambush():
    steps = [
        _make_dummy_step(step=0, turn=1, enemy_damage=2.0, threat_val=0.05),
    ]
    tps = detect_turning_points(steps)
    assert len(tps) == 1
    assert tps[0].event_type == "SURPRISE_DAMAGE"
    assert "ambush" in tps[0].title.lower()


def test_correlate_tactical_heads():
    steps = [
        _make_dummy_step(step=0, threat_val=0.8, enemy_damage=0.0, target_vp="1,1"),
        _make_dummy_step(step=1, threat_val=0.9, enemy_damage=2.0, target_vp="1,1"),
        _make_dummy_step(step=2, threat_val=0.1, enemy_damage=0.0, vp_map={"1,1": "US"}),
    ]
    corrs = correlate_tactical_heads(steps)
    assert "threat_map" in corrs
    assert "morale" in corrs
    assert "objective_intent" in corrs

    tm = corrs["threat_map"]
    assert tm["danger_exposure_count"] >= 1
    assert tm["anticipation_accuracy"] > 0.0

    obj = corrs["objective_intent"]
    assert obj["total_vps_targeted"] == 1
    assert obj["vps_captured_count"] == 1
    assert obj["conversion_rate"] == 1.0


def test_generate_executive_narrative():
    match_meta = {
        "winner": "US",
        "attacker_side": "US",
        "defender_side": "IT",
        "scenario_id": "test_scenario_v1",
    }
    steps = [
        _make_dummy_step(step=0, turn=1, vp_map={"0,0": ""}),
        _make_dummy_step(step=1, turn=2, vp_map={"0,0": "US"}),
    ]
    tps = detect_turning_points(steps)
    corrs = correlate_tactical_heads(steps)
    summary, phases, recs = generate_executive_narrative(
        match_meta=match_meta,
        turning_points=tps,
        head_correlations=corrs,
        total_steps=2,
        total_turns=2,
    )
    assert "US" in summary
    assert len(phases) == 3
    assert len(recs) >= 1


def test_build_forensic_sitrep_structure():
    match_meta = {
        "match_id": "match_alpha",
        "episode_id": "episode_0",
        "scenario_id": "scenario_bocage",
        "attacker_side": "US",
        "defender_side": "GE",
        "winner": "US",
    }
    steps = [
        _make_dummy_step(step=0, turn=1, vp_map={"1,1": ""}, target_vp="1,1"),
        _make_dummy_step(step=1, turn=2, damage_dealt=3.0, kills_dealt=1, vp_map={"1,1": "US"}),
    ]
    sitrep = build_forensic_sitrep(match_meta=match_meta, steps=steps, rag_enabled=True)
    assert sitrep["schema_version"] == "causal_sitrep_v1"
    assert sitrep["attacker_side"] == "US"
    assert sitrep["winner"] == "US"
    assert len(sitrep["turning_points"]) >= 1
    assert "threat_map" in sitrep["head_correlations"]
    assert "objective_intent" in sitrep["head_correlations"]
    assert "battlefield_profile" in sitrep
    assert "forces_oob" in sitrep
    assert "attacker" in sitrep["forces_oob"]
    assert "defender" in sitrep["forces_oob"]
    assert sitrep["battlefield_profile"]["map_dimensions"]["total_hexes"] > 0


def test_get_or_compute_causal_sitrep_real_replay():
    replay_file = Path("runs/efficientzero_v2_0088157a/xai/bench_replay_index_latest.json")
    if not replay_file.exists():
        pytest.skip("Replay index not present in test environment")

    result = get_or_compute_causal_sitrep(
        eval_source_path=str(replay_file),
        episode_id="episode_0",
        repo_root=Path("."),
        force_recompute=True,
    )
    assert result.get("ok") is True
    sitrep = result.get("sitrep", {})
    assert sitrep.get("schema_version") == "causal_sitrep_v1"
    assert len(sitrep.get("executive_summary", "")) > 20

    # Second call should return cached payload
    cached_result = get_or_compute_causal_sitrep(
        eval_source_path=str(replay_file),
        episode_id="episode_0",
        repo_root=Path("."),
        force_recompute=False,
    )
    assert cached_result.get("ok") is True
    assert cached_result.get("sitrep", {}).get("cached") is True


def test_get_or_compute_causal_sitrep_missing_file():
    res = get_or_compute_causal_sitrep(
        eval_source_path="non_existent_replay.json",
        episode_id="episode_0",
        repo_root=Path("."),
    )
    assert res.get("ok") is False
    assert "not found" in res.get("error", "").lower()

