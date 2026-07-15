from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _row_by_agent(payload: dict[str, Any], agent_name: str) -> dict[str, Any]:
    for row in list(payload.get("results", []) or []):
        if str(row.get("agent_name", "")) == str(agent_name):
            return dict(row)
    return {}


def evaluate_promotion_gate(
    *,
    candidate_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
    seed_count: int,
    min_seeds: int = 5,
    min_capture_improvement_ratio: float = 0.15,
    runtime_ratio_limit: float = 1.40,
) -> dict[str, Any]:
    cand_row = _row_by_agent(candidate_payload, "muzero_stub")
    base_row = _row_by_agent(baseline_payload, "muzero_stub")
    cand_gate = dict(candidate_payload.get("phase_2_9_promotion_gate", {}) or {})
    cand_pass = str(cand_gate.get("status", "")).upper() == "PASS"
    cand_captured = float(cand_row.get("tracked_captured_avg", 0.0) or 0.0)
    base_captured = float(base_row.get("tracked_captured_avg", 0.0) or 0.0)
    improvement_ratio = (
        (cand_captured - base_captured) / float(max(1e-9, abs(base_captured)))
        if abs(base_captured) > 1e-9
        else (1.0 if cand_captured > 0.0 else 0.0)
    )
    cand_loss_rate = 1.0 - float(cand_row.get("win_rate", 0.0) or 0.0)
    base_loss_rate = 1.0 - float(base_row.get("win_rate", 0.0) or 0.0)
    cand_runtime = float(cand_row.get("avg_steps", 0.0) or 0.0)
    base_runtime = float(base_row.get("avg_steps", 0.0) or 0.0)
    runtime_ratio = cand_runtime / float(max(1e-9, base_runtime))
    checks = {
        "seed_count_min": int(seed_count) >= int(min_seeds),
        "candidate_phase29_gate_pass": bool(cand_pass),
        "capture_improvement_min": float(improvement_ratio) >= float(min_capture_improvement_ratio),
        "loss_rate_no_regression": float(cand_loss_rate) <= float(base_loss_rate) + 1e-9,
        "runtime_ratio_within_limit": float(runtime_ratio) <= float(runtime_ratio_limit),
    }
    return {
        "status": "PASS" if all(bool(v) for v in checks.values()) else "FAIL",
        "checks": checks,
        "metrics": {
            "seed_count": int(seed_count),
            "min_seeds": int(min_seeds),
            "capture_improvement_ratio": float(improvement_ratio),
            "capture_improvement_min": float(min_capture_improvement_ratio),
            "candidate_tracked_captured_avg": float(cand_captured),
            "baseline_tracked_captured_avg": float(base_captured),
            "candidate_loss_rate": float(cand_loss_rate),
            "baseline_loss_rate": float(base_loss_rate),
            "runtime_ratio_proxy": float(runtime_ratio),
            "runtime_ratio_limit": float(runtime_ratio_limit),
        },
        "source": {
            "candidate_run_id": str(candidate_payload.get("run_id", "")),
            "baseline_run_id": str(baseline_payload.get("run_id", "")),
            "candidate_phase29_gate_status": str(cand_gate.get("status", "")),
        },
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate EfficientZero promotion gate.")
    parser.add_argument("--candidate-json", required=True, help="Benchmark JSON for candidate model.")
    parser.add_argument("--baseline-json", required=True, help="Benchmark JSON for baseline model.")
    parser.add_argument("--seed-count", type=int, required=True, help="Number of eval seeds used.")
    parser.add_argument("--min-seeds", type=int, default=5, help="Minimum seeds required for gate.")
    parser.add_argument(
        "--min-capture-improvement-ratio",
        type=float,
        default=0.15,
        help="Minimum tracked-capture improvement ratio vs baseline.",
    )
    parser.add_argument(
        "--runtime-ratio-limit",
        type=float,
        default=1.40,
        help="Maximum candidate runtime ratio vs baseline.",
    )
    parser.add_argument("--out", default="", help="Optional output report JSON path.")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    candidate = json.loads(Path(args.candidate_json).read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline_json).read_text(encoding="utf-8"))
    report = evaluate_promotion_gate(
        candidate_payload=candidate,
        baseline_payload=baseline,
        seed_count=int(args.seed_count),
        min_seeds=int(args.min_seeds),
        min_capture_improvement_ratio=float(args.min_capture_improvement_ratio),
        runtime_ratio_limit=float(args.runtime_ratio_limit),
    )
    if str(args.out).strip():
        out_path = Path(str(args.out)).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
