from assault_bench.runner import run_benchmark


def test_benchmark_uses_shared_scenario():
    payload = run_benchmark(config_path="assault_bench/configs/benchmark_config.test.yaml")
    assert payload["scenario_id"] == "battaglia_cittadina_2_1"
    assert len(payload["results"]) >= 2
