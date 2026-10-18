from __future__ import annotations

import argparse
import json
from pathlib import Path
from agents.efficientzero_v2.train.train_engine import run_training as run_engine_training
from mlops.catalog_publisher_v2 import publish_train_run


def run_training(
    config_path: str = "agents/efficientzero_v2/configs/efficientzero_v2_config.yaml",
    mlflow_experiment: str = "assault_efficientzero_v2",
    mlflow_run_name: str = "",
) -> dict:
    print("[EfficientZeroV2] mode=efficient_core (isolated engine)")
    result = run_engine_training(
        config_path=config_path,
        mlflow_experiment=mlflow_experiment,
        mlflow_run_name=mlflow_run_name,
    )
    repo_root = Path(__file__).resolve().parents[3]
    publish_result = publish_train_run(
        repo_root=repo_root,
        run_id=str(result.get("run_id", "") or ""),
    )
    result["catalog_publish_status"] = str(publish_result.get("publish_status", "unknown"))
    result["catalog_publish_status_path"] = str(
        publish_result.get("publish_status_path", "")
    )
    result["engine_mode"] = str(result.get("engine_mode", "efficient_core") or "efficient_core")
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run EfficientZero v2 training on VOEC.")
    parser.add_argument(
        "--config",
        default="agents/efficientzero_v2/configs/efficientzero_v2_config.yaml",
        help="Path to YAML config file.",
    )
    parser.add_argument(
        "--mlflow-experiment",
        default="assault_efficientzero_v2",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--mlflow-run-name",
        default="",
        help="Optional MLflow run name. Defaults to generated run_id.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    output = run_training(
        config_path=str(args.config),
        mlflow_experiment=str(args.mlflow_experiment),
        mlflow_run_name=str(args.mlflow_run_name),
    )
    run_id = output.get("run_id", "unknown")
    metrics = output.get("metrics", {})
    timing = metrics.get("timing_summary", {})
    print(
        f"[EfficientZeroV2] Training finished successfully! run_id={run_id} | "
        f"loss={metrics.get('loss', 0.0):.4f} | "
        f"total_time={timing.get('total_elapsed_s', 0.0):.1f}s "
        f"(avg_iter={timing.get('iter_avg_s', 0.0):.2f}s) | "
        f"summary saved to metrics/summary.json"
    )

