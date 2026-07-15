from mlops.efficientzero_promotion_gate import evaluate_promotion_gate


def test_efficientzero_promotion_gate_passes_with_expected_improvement() -> None:
    candidate = {
        "run_id": "efficientzero_v2_candidate",
        "phase_2_9_promotion_gate": {"status": "PASS"},
        "results": [
            {"agent_name": "muzero_stub", "tracked_captured_avg": 1.3, "win_rate": 0.60, "avg_steps": 80}
        ],
    }
    baseline = {
        "run_id": "muzero_baseline",
        "results": [
            {"agent_name": "muzero_stub", "tracked_captured_avg": 1.0, "win_rate": 0.55, "avg_steps": 70}
        ],
    }
    report = evaluate_promotion_gate(
        candidate_payload=candidate,
        baseline_payload=baseline,
        seed_count=5,
        min_seeds=5,
        min_capture_improvement_ratio=0.15,
        runtime_ratio_limit=1.4,
    )
    assert report["status"] == "PASS"
    assert report["checks"]["candidate_phase29_gate_pass"] is True


def test_efficientzero_promotion_gate_fails_with_low_seed_count() -> None:
    candidate = {
        "phase_2_9_promotion_gate": {"status": "PASS"},
        "results": [{"agent_name": "muzero_stub", "tracked_captured_avg": 1.2, "win_rate": 0.60, "avg_steps": 90}],
    }
    baseline = {
        "results": [{"agent_name": "muzero_stub", "tracked_captured_avg": 1.0, "win_rate": 0.50, "avg_steps": 70}],
    }
    report = evaluate_promotion_gate(
        candidate_payload=candidate,
        baseline_payload=baseline,
        seed_count=3,
        min_seeds=5,
    )
    assert report["status"] == "FAIL"
    assert report["checks"]["seed_count_min"] is False
