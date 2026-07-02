from assault_bench.runner import run_benchmark


def test_benchmark_returns_results():
    payload = run_benchmark(config_path="assault_bench/configs/benchmark_config.test.yaml")
    assert "results" in payload
    assert len(payload["results"]) >= 2
    assert "terminal_reasons" in payload["results"][0]
    assert "phase_2_9_train_eval" in payload
    assert "phase_2_9_promotion_gate" in payload
    muzero_row = next(r for r in payload["results"] if r["agent_name"] == "muzero_stub")
    assert "phase_2_9_eval_kpis" in muzero_row
    assert "reaction_fire_count" in muzero_row["phase_2_9_eval_kpis"]
