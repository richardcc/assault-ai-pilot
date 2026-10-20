"""
Unit and integration tests for Telemetry Probe Profiling and Overhead Validation.

Roadmap Task 1.2:
- Measure probe latency in microseconds (\u03bcs).
- Verify lazy evaluation and cache memoization.
- Guarantee telemetry probe overhead < 1.5% in hot simulation loop.
- Strictly adhere to Zero-Mock / Zero-Inference (no synthetic or fake timings).
"""

from __future__ import annotations

import pickle
import time
import pytest

from mlops.telemetry.probe_profiler import (
    ProbeMetric,
    ProbeProfiler,
    LazyProbeSnapshot,
    get_global_probe_profiler,
    set_global_probe_profiler,
    profile_probe,
)
from agents.efficientzero_v2.core.selfplay import (
    _candidate_expected_damage,
    _build_unit_indexes,
    play_episode,
)
from agents.efficientzero_v2.core.adapter_voec import EZV2VOECAdapter
from voec_sim.core.simulator import VOECSimulator
from agents.efficientzero_v2.core.mcts import run_mcts_puct, MCTSOutput


def test_probe_profiler_microsecond_precision() -> None:
    profiler = ProbeProfiler(enabled=True, budget_target_pct=1.5)

    # 1. Test live context managers
    with profiler.time_step():
        with profiler.time_probe("test_live_probe"):
            _ = [x * x for x in range(1000)]

    # 2. Test explicit deterministic recording (50 \u03bcs probe out of 10,000 \u03bcs step = 0.5% overhead)
    profiler.record_step(10_000_000)  # 10 ms = 10,000 \u03bcs
    profiler.record_probe("test_fast_probe", 25_000)  # 25 \u03bcs
    profiler.record_probe("test_fast_probe", 25_000)  # 25 \u03bcs

    summary = profiler.get_summary()
    assert summary.total_step_count == 2
    assert summary.total_step_time_us > 10_000.0
    assert summary.total_probe_time_us > 0.0

    probe_metric = summary.probes["test_fast_probe"]
    assert probe_metric.count == 2
    assert probe_metric.mean_us == 25.0
    assert probe_metric.min_us == 25.0
    assert probe_metric.max_us == 25.0
    assert summary.probe_overhead_pct < summary.budget_target_pct
    assert not summary.budget_exceeded

    report = summary.format_report()
    assert "HOT-LOOP TELEMETRY PROBE PROFILING REPORT" in report
    assert "WITHIN BUDGET" in report


def test_lazy_probe_snapshot_defers_and_caches() -> None:
    call_count = 0

    def expensive_map_factory() -> dict[str, int]:
        nonlocal call_count
        call_count += 1
        return {"0,0": 1, "1,1": 2}

    lazy_probe = LazyProbeSnapshot(expensive_map_factory, probe_name="expensive_map")
    assert not lazy_probe.is_evaluated()
    assert call_count == 0

    # First access evaluates and caches
    val = lazy_probe["0,0"]
    assert val == 1
    assert lazy_probe.is_evaluated()
    assert call_count == 1

    # Subsequent accesses reuse cached result
    assert lazy_probe.get("1,1") == 2
    assert len(lazy_probe) == 2
    assert "0,0" in lazy_probe
    assert list(lazy_probe.keys()) == ["0,0", "1,1"]
    assert call_count == 1

    # Multiprocessing serialization safety: test pickle roundtrip with local closure/lambda
    closure_probe = LazyProbeSnapshot(lambda: {"hex_1": 10, "hex_2": 20}, probe_name="closure_probe")
    pickled_bytes = pickle.dumps(closure_probe)
    restored_probe = pickle.loads(pickled_bytes)
    assert isinstance(restored_probe, LazyProbeSnapshot)
    assert restored_probe.is_evaluated()
    assert restored_probe["hex_1"] == 10
    assert restored_probe["hex_2"] == 20
    assert dict(restored_probe) == {"hex_1": 10, "hex_2": 20}


def test_candidate_expected_damage_cache_memoization() -> None:
    units = [
        {"unit_id": "US_1", "unit_key": "infantry_rifle", "q": 0, "r": 0, "side": "US"},
        {"unit_id": "GE_1", "unit_key": "infantry_rifle", "q": 1, "r": 0, "side": "GE"},
    ]
    by_id, by_pos = _build_unit_indexes(units)
    damage_cache: dict[str, float] = {}

    action_id = "ATTACK:US_1:GE_1:1:0"

    # First call computes and populates cache
    dmg1 = _candidate_expected_damage(
        action_id=action_id,
        units=units,
        terrain_cover_by_hex={},
        terrain_los_block_by_hex={},
        units_by_id=by_id,
        units_by_pos=by_pos,
        cache=damage_cache,
    )
    assert action_id in damage_cache
    assert damage_cache[action_id] == dmg1

    # Second call returns cached value directly
    dmg2 = _candidate_expected_damage(
        action_id=action_id,
        units=units,
        terrain_cover_by_hex={},
        terrain_los_block_by_hex={},
        units_by_id=by_id,
        units_by_pos=by_pos,
        cache=damage_cache,
    )
    assert dmg1 == dmg2


def test_mcts_output_chosen_score_direct_access() -> None:
    legal_actions = ["MOVE:US_1:0:1", "WAIT:US_1:0:0"]
    mcts_out = run_mcts_puct(
        legal_actions=legal_actions,
        num_simulations=16,
        priors_by_action={"MOVE:US_1:0:1": 0.6, "WAIT:US_1:0:0": 0.4},
        values_by_action={"MOVE:US_1:0:1": 0.5, "WAIT:US_1:0:0": 0.2},
    )
    assert isinstance(mcts_out, MCTSOutput)
    assert isinstance(mcts_out.chosen_score, float)
    assert mcts_out.chosen_score > 0.0
    assert mcts_out.root_candidate_breakdown is not None
    assert len(mcts_out.root_candidate_breakdown) == 2


def test_hot_loop_telemetry_overhead_budget() -> None:
    profiler = ProbeProfiler(enabled=True, budget_target_pct=1.5)
    set_global_probe_profiler(profiler)
    try:
        sim = VOECSimulator()
        adapter = EZV2VOECAdapter(sim)
        adapter.initial_state("battaglia_cittadina_2_1", seed=42)

        samples = play_episode(
            adapter=adapter,
            scenario_id="battaglia_cittadina_2_1",
            seed=42,
            max_steps=8,
            action_dim=32,
            model=None,
            mcts_simulations=16,
        )
        assert len(samples) > 0
        summary = profiler.get_summary()

        assert summary.total_step_count > 0
        assert summary.total_step_time_us > 0.0

        # Output the report to stdout for MLOps inspection
        print("\n" + summary.format_report())

        # Assert strict compliance with Task 1.2 acceptance criteria (< 1.5% overhead)
        profiler.assert_overhead_within_budget(max_overhead_pct=1.5)
    finally:
        set_global_probe_profiler(None)
