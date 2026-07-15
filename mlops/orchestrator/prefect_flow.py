from __future__ import annotations

from typing import Any

from mlops.orchestrator.run import run_experiment

try:
    from prefect import flow  # type: ignore
except Exception:
    flow = None


if flow is not None:

    @flow(name="assault-curriculum-eval")
    def run_experiment_prefect(config_path: str = "mlops/configs/experiment_config.yaml") -> dict[str, Any]:
        return run_experiment(config_path=config_path)

else:

    def run_experiment_prefect(config_path: str = "mlops/configs/experiment_config.yaml") -> dict[str, Any]:
        # Graceful fallback: keep same behavior when Prefect is not installed.
        return run_experiment(config_path=config_path)
