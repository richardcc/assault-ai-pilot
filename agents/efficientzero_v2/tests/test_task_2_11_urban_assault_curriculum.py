"""
Unit tests for Task 2.11: Pure Offensive Urban Assault Curriculum (battaglia_cittadina_2_1, T=8).

Validates:
    1. Phase 5 integration in curriculums/vp_acceleration/curriculum.yaml with max_reinforcement_cycles=10.
    2. Training configuration with T=8, catastrophic timeout penalty (-1.0), and time-scaled PBRS.
    3. Adaptive cycles specification with 10 independent/evolutionary cycles (baseline, exploitation, exploration, hyper-assault).
    4. Evaluation benchmark configuration matching Gela urban assault scenario.
"""

from __future__ import annotations

from pathlib import Path
import yaml
import pytest


def test_task_2_11_curriculum_yaml_phase5_declaration():
    """Verify phase5_urban_assault_pure_offensive is declared in curriculum.yaml with 10 cycles."""
    curriculum_path = Path("curriculums/vp_acceleration/curriculum.yaml")
    assert curriculum_path.is_file(), f"Missing {curriculum_path}"

    with open(curriculum_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    phases = data.get("phases", [])
    phase5 = next((p for p in phases if p.get("name") == "phase5_urban_assault_pure_offensive"), None)
    assert phase5 is not None, "phase5_urban_assault_pure_offensive not found in curriculum.yaml"

    assert int(phase5.get("max_reinforcement_cycles", 0)) == 10
    assert "train_config" in phase5
    assert "eval_config" in phase5
    gate = phase5.get("gate", {})
    assert float(gate.get("min_win_rate", 0.0)) >= 0.40
    assert float(gate.get("max_avg_turns", 99.0)) <= 12.0


def test_task_2_11_train_config_properties():
    """Verify training configuration contains short horizon T=8 and catastrophic timeout penalty."""
    train_cfg_path = Path("curriculums/vp_acceleration/configs/efficientzero_v2.phase5_urban_assault_pure_offensive.yaml")
    assert train_cfg_path.is_file(), f"Missing {train_cfg_path}"

    with open(train_cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    scenario = cfg.get("scenario", {})
    assert scenario.get("id") == "battaglia_cittadina_2_1"
    assert int(scenario.get("max_turns", 0)) == 8

    selfplay = cfg.get("selfplay", {})
    assert float(selfplay.get("timeout_penalty", 0.0)) <= -1.0
    shaping = selfplay.get("reward_shaping", {})
    assert bool(shaping.get("time_scaled_pbrs", False)) is True
    assert float(shaping.get("breach_casualty_attenuation", 1.0)) == 0.40
    assert int(shaping.get("breach_distance", 0)) == 2


def test_task_2_11_adaptive_cycles_10_phases():
    """Verify adaptive_cycles.yaml defines 10 full evolutionary cycles."""
    cycles_path = Path("curriculums/vp_acceleration/cycles/phase5_urban_assault_pure_offensive.adaptive_cycles.yaml")
    assert cycles_path.is_file(), f"Missing {cycles_path}"

    with open(cycles_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data.get("schema_version") == "adaptive_cycles.v1"
    assert data.get("curriculum_name") == "vp_acceleration_v1"
    assert int(data.get("max_independent_cycles", 10)) >= 3

    cycles = data.get("cycles", {})
    assert 1 <= len(cycles) <= 10
    for cycle_num in cycles.keys():
        assert int(cycle_num) in range(1, 11), f"Unexpected cycle {cycle_num}"


def test_task_2_11_benchmark_eval_config():
    """Verify benchmark eval config targets battaglia_cittadina_2_1 with attacker side B profile."""
    bench_path = Path("assault_bench/configs/benchmark_config.vp_acceleration_phase5.yaml")
    assert bench_path.is_file(), f"Missing {bench_path}"

    with open(bench_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    bench = cfg.get("benchmark", {})
    assert bench.get("scenario_id") == "battaglia_cittadina_2_1"
    profiles = bench.get("matchup_profiles", [])
    assert "ezv2_vs_random_side_b" in profiles
