from __future__ import annotations

from typing import Any


def run_experiment(*args: Any, **kwargs: Any):
    # Lazy import avoids circular dependency during package initialization:
    # assault_bench.runner -> mlops.catalog_publisher_v2 -> mlops (__init__) -> orchestrator.run -> assault_bench.runner
    from mlops.orchestrator.run import run_experiment as _run_experiment

    return _run_experiment(*args, **kwargs)


__all__ = ["run_experiment"]
