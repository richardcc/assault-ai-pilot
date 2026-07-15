from mlops.orchestrator import prefect_flow


def test_prefect_wrapper_delegates(monkeypatch) -> None:
    monkeypatch.setattr(
        "mlops.orchestrator.prefect_flow.run_experiment",
        lambda config_path: {"experiment_id": "exp_test", "config_path": config_path},
    )
    out = prefect_flow.run_experiment_prefect(config_path="mlops/configs/experiment_config.yaml")
    assert out["experiment_id"] == "exp_test"
