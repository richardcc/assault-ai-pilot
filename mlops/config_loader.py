from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mlops.contracts import ExperimentConfig, ExperimentPaths


def _resolve(base_dir: Path, raw_path: str) -> Path:
    path = Path(str(raw_path))
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _require(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise KeyError(f"Missing required key '{key}'")
    return raw[key]


def load_experiment_config(path: Path) -> ExperimentConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base_dir = path.parent
    paths = dict(payload.get("paths", {}) or {})
    parsed_paths = ExperimentPaths(
        run_root=_resolve(base_dir, str(paths.get("run_root", "runs"))),
        benchmark_config=_resolve(base_dir, str(_require(paths, "benchmark_config"))),
        muzero_config=_resolve(base_dir, str(_require(paths, "muzero_config"))),
        curriculum_config=_resolve(base_dir, str(_require(paths, "curriculum_config"))),
    )
    return ExperimentConfig(
        experiment_name=str(payload.get("experiment_name", "curriculum_eval")),
        agents=[str(x) for x in list(payload.get("agents", ["muzero", "baseline_random"]))],
        paths=parsed_paths,
        execution=dict(payload.get("execution", {}) or {}),
    )
