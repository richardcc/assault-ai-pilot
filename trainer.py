# trainer.py
"""
Canonical Root Training Entrypoint for Assault Project.
Strict Enforcement: Operates exclusively with EfficientZero V2 (MuZero is 100% decommissioned).
Delegates to agents.efficientzero_v2.train.train_efficientzero_v2 and exposes EfficientZeroV2Trainer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict

from agents.efficientzero_v2.train.trainer import EfficientZeroV2Trainer
from agents.efficientzero_v2.train.train_efficientzero_v2 import run_training


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assault Engine - EfficientZero V2 Canonical Trainer"
    )
    parser.add_argument(
        "--config",
        default="agents/efficientzero_v2/configs/efficientzero_v2_config.yaml",
        help="Path to YAML training configuration file.",
    )
    parser.add_argument(
        "--mlflow-experiment",
        default="assault_efficientzero_v2",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--mlflow-run-name",
        default="",
        help="MLflow run name identifier.",
    )
    parser.add_argument(
        "--scenario-id",
        default="",
        help="Optional scenario override for training (e.g. vp_phase1_unoccupied_3hex, battaglia_cittadina_2_1).",
    )
    args = parser.parse_args()

    print(f"[Trainer] Launching Canonical EfficientZero V2 Trainer with config: {args.config}")
    res = run_training(
        config_path=str(args.config),
        mlflow_experiment=str(args.mlflow_experiment),
        mlflow_run_name=str(args.mlflow_run_name),
    )
    print(f"[Trainer] Completed training run: {res.get('run_id')} (Status: {res.get('catalog_publish_status')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
