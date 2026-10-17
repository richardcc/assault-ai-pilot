"""Unit tests for Tactical Quality Metrics engine (mlops/reporting/quality_metrics.py)."""

import math
from mlops.reporting.quality_metrics import (
    compute_anchor_elo,
    compute_side_score,
    compute_tactical_quality_metrics,
)


def test_compute_side_score():
    assert compute_side_score(1.0, 0.0) == 1.0
    assert compute_side_score(0.0, 1.0) == 0.5
    assert compute_side_score(0.0, 0.0) == 0.0
    assert compute_side_score(0.5, 0.5) == 0.75


def test_compute_anchor_elo_calibration():
    # If a model beats random with 50% mirror, its anchor vs random (800) is 800
    elo_neutral = compute_anchor_elo(mirror_score_vs_random=0.5, mirror_score_vs_mcts=0.5)
    # Weighted blend between 800 (weight 1) and 1400 (weight 2.5): (800*1 + 1400*2.5)/3.5 = 1228.6
    assert 1220 <= elo_neutral <= 1240

    # If a model dominates random (90%) and holds parity vs MCTS (50%):
    elo_strong = compute_anchor_elo(mirror_score_vs_random=0.90, mirror_score_vs_mcts=0.50)
    assert elo_strong > elo_neutral


def test_compute_tactical_quality_metrics_empty():
    res = compute_tactical_quality_metrics([])
    assert res["status"] == "empty"
    assert res["tactical_quality_score"] == 0.0
    assert res["tactical_grade"] == "D"


def test_compute_tactical_quality_metrics_mirror_cancels_asymmetry():
    # Synthetic heavily biased scenario: Side A has 90% inherent advantage.
    # Model on Side A vs Random scores 0.95
    # Model on Side B vs Random scores 0.25 (which is brilliant given Side B baseline)
    sample_rows = [
        {
            "scenario_id": "test_scen",
            "matchup_profile": "muzero_vs_random_side_a",
            "controller": "EfficientZeroV2",
            "opponent_controller": "Random",
            "side": "A",
            "episodes": 10,
            "win_rate": 0.90,
            "draw_rate": 0.10,
            "loss_rate": 0.0,
            "score": 0.95,
            "victory_rate": 0.90,
            "defeat_rate": 0.0,
            "total_victory_rate": 0.0,
            "total_defeat_rate": 0.0,
            "vp_net_avg_side": 0.5,
            "tracked_captured_avg": 2.0,
        },
        {
            "scenario_id": "test_scen",
            "matchup_profile": "muzero_vs_random_side_b",
            "controller": "EfficientZeroV2",
            "opponent_controller": "Random",
            "side": "B",
            "episodes": 10,
            "win_rate": 0.20,
            "draw_rate": 0.10,
            "loss_rate": 0.70,
            "score": 0.25,
            "victory_rate": 0.20,
            "defeat_rate": 0.70,
            "total_victory_rate": 0.0,
            "total_defeat_rate": 0.0,
            "vp_net_avg_side": -0.2,
            "tracked_captured_avg": 1.0,
        },
    ]

    metrics = compute_tactical_quality_metrics(sample_rows)
    assert metrics["status"] == "ok"
    # Mirror score should be exactly (0.95 + 0.25)/2 = 0.60
    assert abs(metrics["global_mirror_score_vs_random"] - 0.60) < 1e-3
    assert abs(metrics["mean_asymmetry_gap"] - 0.70) < 1e-3
    assert metrics["tactical_quality_score"] > 50.0
