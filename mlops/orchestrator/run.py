from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from assault_bench.runner import run_benchmark
from mlops.config_loader import load_experiment_config
from mlops.contracts import CurriculumStage
from mlops.curriculum.io import load_curriculum_spec
from mlops.registry.default_registry import build_default_registry, get_adapter
from mlops.reports import build_comparison_summary, build_decision_report


def _stage_to_dict(stage: CurriculumStage) -> dict[str, Any]:
    return asdict(stage)


def _start_mlflow_run(experiment_name: str, run_name: str):
    try:
        import mlflow  # type: ignore
    except Exception:
        return None, None
    mlflow.set_experiment(str(experiment_name))
    run = mlflow.start_run(run_name=str(run_name))
    return mlflow, run


def _mlflow_log_metrics(mlflow_mod, metrics: dict[str, Any], step: int = 0) -> None:
    if mlflow_mod is None:
        return
    for key, value in (metrics or {}).items():
        if isinstance(value, (int, float)):
            try:
                mlflow_mod.log_metric(str(key), float(value), step=step)
            except Exception:
                continue


def _build_stage_metrics(stage_payload: dict[str, Any]) -> dict[str, float]:
    comparison = dict(stage_payload.get("comparison_summary", {}) or {})
    decision = dict(stage_payload.get("decision_report", {}) or {})
    metric_payload = dict(comparison.get("metrics", {}) or {})
    gate_status = str(decision.get("gate_status", "UNKNOWN")).upper()
    out = {
        "win_rate_delta_vs_baseline": float(metric_payload.get("win_rate_delta_vs_baseline", 0.0)),
        "muzero_win_rate": float(metric_payload.get("muzero_win_rate", 0.0)),
        "baseline_win_rate": float(metric_payload.get("baseline_win_rate", 0.0)),
        "promotion_gate_pass": 1.0 if gate_status == "PASS" else 0.0,
    }
    return out


def run_experiment(config_path: str = "mlops/configs/experiment_config.yaml") -> dict[str, Any]:
    cfg = load_experiment_config(Path(config_path))
    curriculum = load_curriculum_spec(cfg.paths.curriculum_config)
    registry = build_default_registry(run_root=cfg.paths.run_root)

    exp_id = f"exp_{uuid.uuid4().hex[:8]}"
    exp_root = cfg.paths.run_root / "experiments" / exp_id
    exp_root.mkdir(parents=True, exist_ok=True)
    mlflow_mod, _mlflow_run = _start_mlflow_run(
        experiment_name=str(cfg.execution.get("mlflow_experiment", "assault_mlop")),
        run_name=f"{cfg.experiment_name}_{exp_id}",
    )
    if mlflow_mod is not None:
        try:
            mlflow_mod.log_params(
                {
                    "experiment_id": exp_id,
                    "experiment_name": cfg.experiment_name,
                    "config_path": str(Path(config_path).resolve()),
                    "agents": ",".join(cfg.agents),
                    "curriculum_path": str(cfg.paths.curriculum_config),
                }
            )
        except Exception:
            pass

    stage_outputs: list[dict[str, Any]] = []
    for stage_idx, stage in enumerate(curriculum.stages, start=1):
        stage_name = str(stage.name)
        stage_dir = exp_root / stage_name
        stage_dir.mkdir(parents=True, exist_ok=True)
        train_outputs: dict[str, Any] = {}
        selected_checkpoint = ""
        for agent_name in stage.train_agents:
            adapter = get_adapter(registry, agent_name)
            if adapter is None:
                raise KeyError(f"Unknown agent '{agent_name}' in stage '{stage_name}'")
            if agent_name not in cfg.agents:
                continue
            muzero_cfg = stage.muzero_config or str(cfg.paths.muzero_config)
            out = adapter.train(
                config_path=muzero_cfg,
                stage_name=stage_name,
                scenario_id=stage.scenario_id,
            )
            train_outputs[agent_name] = asdict(out)
            if agent_name == "muzero" and out.checkpoint_path:
                selected_checkpoint = out.checkpoint_path
        bench_cfg = stage.benchmark_config or str(cfg.paths.benchmark_config)
        bench_payload = run_benchmark(
            config_path=bench_cfg,
            checkpoint_path=selected_checkpoint,
            muzero_config_path=str(cfg.paths.muzero_config),
            mlflow_experiment=str(cfg.execution.get("mlflow_experiment", "assault_bench")),
            mlflow_run_name=f"{cfg.experiment_name}_{stage_name}",
        )
        comparison = build_comparison_summary(bench_payload)
        decision = build_decision_report(comparison)
        stage_payload = {
            "stage": _stage_to_dict(stage),
            "train_outputs": train_outputs,
            "benchmark": bench_payload,
            "comparison_summary": comparison,
            "decision_report": decision,
        }
        (stage_dir / "stage_manifest.json").write_text(json.dumps(stage_payload, indent=2), encoding="utf-8")
        _mlflow_log_metrics(mlflow_mod, _build_stage_metrics(stage_payload), step=stage_idx)
        if mlflow_mod is not None:
            try:
                mlflow_mod.log_artifact(str(stage_dir / "stage_manifest.json"))
            except Exception:
                pass
        stage_outputs.append(stage_payload)

    manifest = {
        "experiment_id": exp_id,
        "experiment_name": cfg.experiment_name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": str(Path(config_path).resolve()),
        "stages": stage_outputs,
    }
    (exp_root / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    final_summary = stage_outputs[-1]["comparison_summary"] if stage_outputs else {}
    final_decision = stage_outputs[-1]["decision_report"] if stage_outputs else {}
    (exp_root / "comparison_summary.json").write_text(json.dumps(final_summary, indent=2), encoding="utf-8")
    (exp_root / "decision_report.json").write_text(json.dumps(final_decision, indent=2), encoding="utf-8")
    if mlflow_mod is not None:
        try:
            mlflow_mod.log_artifact(str(exp_root / "experiment_manifest.json"))
            mlflow_mod.log_artifact(str(exp_root / "comparison_summary.json"))
            mlflow_mod.log_artifact(str(exp_root / "decision_report.json"))
            mlflow_mod.end_run()
        except Exception:
            pass
    return {"experiment_id": exp_id, "experiment_root": str(exp_root), "decision_report": final_decision}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run curriculum + evaluation experiment.")
    parser.add_argument(
        "--config",
        default="mlops/configs/experiment_config.yaml",
        help="Path to experiment YAML config file.",
    )
    parser.add_argument(
        "--prefect",
        action="store_true",
        help="Run through Prefect flow wrapper when Prefect is installed.",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    if args.prefect:
        from mlops.orchestrator.prefect_flow import run_experiment_prefect

        print(json.dumps(run_experiment_prefect(config_path=args.config), indent=2))
    else:
        print(json.dumps(run_experiment(config_path=args.config), indent=2))
