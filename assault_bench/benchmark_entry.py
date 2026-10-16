from __future__ import annotations

import argparse
import faulthandler
import json
import traceback

from assault_bench import run_benchmark


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VOEC benchmark matrix.")
    parser.add_argument(
        "--config",
        default="assault_bench/configs/benchmark_config.yaml",
        help="Path to benchmark YAML config file.",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help=(
            "Optional checkpoint path; empty or 'latest' auto-selects newest checkpoint "
            "under runs/muzero_* or runs/efficientzero_v2_*."
        ),
    )
    parser.add_argument(
        "--muzero-config",
        default="",
        help=(
            "Optional model config path used to build network shape when --checkpoint is set. "
            "If omitted, inferred by checkpoint engine."
        ),
    )
    parser.add_argument(
        "--mlflow-experiment",
        default="assault_bench",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--mlflow-run-name",
        default="",
        help="Optional MLflow run name.",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda", "auto"),
        default="",
        help="Optional benchmark device override; when unset, benchmark config device is used.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Print full benchmark payload JSON to stdout (default prints concise summary).",
    )
    return parser


def main() -> None:
    # Emit Python/native fault dumps (segfault, access violation) to stderr.
    try:
        faulthandler.enable(all_threads=True)
    except Exception:
        pass
    args = _build_arg_parser().parse_args()
    try:
        payload = run_benchmark(
            config_path=args.config,
            checkpoint_path=args.checkpoint,
            muzero_config_path=args.muzero_config,
            mlflow_experiment=args.mlflow_experiment,
            mlflow_run_name=args.mlflow_run_name,
            device=args.device,
        )
        if bool(args.print_json):
            print(json.dumps(payload))
        else:
            result_rows = list(dict(payload or {}).get("results", []) or [])
            gate_status = str(
                dict(dict(payload or {}).get("phase_2_9_promotion_gate", {}) or {}).get("status", "")
            )
            timing = dict(dict(payload or {}).get("benchmark_timing", {}) or {})
            total_wall_s = float(timing.get("total_wall_s", 0.0) or 0.0)
            eps = float(timing.get("episodes_per_second", 0.0) or 0.0)
            print(
                "[Bench] completed "
                f"run_id={str(dict(payload or {}).get('run_id', '') or '')} "
                f"scenario_id={str(dict(payload or {}).get('scenario_id', '') or '')} "
                f"results={int(len(result_rows))} "
                f"gate={gate_status or 'n/a'} "
                f"wall_s={total_wall_s:.2f} eps={eps:.3f}"
            )
    except BaseException:
        print("[Bench][FATAL] benchmark_entry uncaught exception:", flush=True)
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
