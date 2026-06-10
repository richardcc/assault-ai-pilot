from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_report(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_rows(report: dict) -> list[dict]:
    rows = []
    by_side = report.get("by_side", {}) or {}
    for side, scenarios in by_side.items():
        for scenario, payload in (scenarios or {}).items():
            summary = payload.get("summary", {}) or {}
            mission = payload.get("mission", {}) or {}
            rows.append(
                {
                    "side": side,
                    "scenario": scenario,
                    "true_win_rate": float(summary.get("true_win_rate", 0.0) or 0.0),
                    "loss_rate": float(summary.get("loss_rate", 0.0) or 0.0),
                    "draw_rate": float(summary.get("draw_rate", 0.0) or 0.0),
                    "captured_final_counts": dict(summary.get("captured_final_counts", {}) or {}),
                    "vp_entry_missed_rate": mission.get("vp_entry_missed_rate"),
                    "strategy_stuck_ratio": float(mission.get("strategy_stuck_ratio", 0.0) or 0.0),
                }
            )
    return rows


def _score_captured_45(captured_final_counts: dict) -> int:
    c4 = int(captured_final_counts.get("4", 0) or 0)
    c5 = int(captured_final_counts.get("5", 0) or 0)
    return c4 + c5


def _gate_status(row: dict, min_true_win_rate: float, max_loss_rate: float, max_stuck_ratio: float) -> tuple[str, list[str]]:
    reasons = []
    if row["true_win_rate"] < min_true_win_rate:
        reasons.append(f"true_win_rate<{min_true_win_rate:.2f}")
    if row["loss_rate"] > max_loss_rate:
        reasons.append(f"loss_rate>{max_loss_rate:.2f}")
    if row["strategy_stuck_ratio"] > max_stuck_ratio:
        reasons.append(f"strategy_stuck_ratio>{max_stuck_ratio:.2f}")
    if row["vp_entry_missed_rate"] is not None and float(row["vp_entry_missed_rate"]) >= 1.0:
        reasons.append("vp_entry_missed_rate_saturated")
    if _score_captured_45(row["captured_final_counts"]) <= 0:
        reasons.append("captured_4_5_zero")
    return ("GO", reasons) if not reasons else ("NO-GO", reasons)


def main():
    parser = argparse.ArgumentParser(description="Summarize SB3 eval gates from report JSON.")
    parser.add_argument("--report", type=str, required=True, help="Path to metrics_sb3_report_*.json")
    parser.add_argument("--min-true-win-rate", type=float, default=0.10)
    parser.add_argument("--max-loss-rate", type=float, default=0.60)
    parser.add_argument("--max-stuck-ratio", type=float, default=0.70)
    args = parser.parse_args()

    report_path = Path(args.report)
    report = _load_report(report_path)
    rows = _extract_rows(report)
    if not rows:
        raise SystemExit("No evaluable rows found in report.")

    print(f"Report: {report_path}")
    for row in rows:
        status, reasons = _gate_status(
            row=row,
            min_true_win_rate=args.min_true_win_rate,
            max_loss_rate=args.max_loss_rate,
            max_stuck_ratio=args.max_stuck_ratio,
        )
        print(
            f"[{status}] side={row['side']} scenario={row['scenario']} "
            f"true_win_rate={row['true_win_rate']:.3f} "
            f"loss_rate={row['loss_rate']:.3f} "
            f"draw_rate={row['draw_rate']:.3f} "
            f"vp_entry_missed_rate={row['vp_entry_missed_rate']} "
            f"strategy_stuck_ratio={row['strategy_stuck_ratio']:.3f} "
            f"captured_4_5={_score_captured_45(row['captured_final_counts'])}"
        )
        if reasons:
            print(f"  reasons: {', '.join(reasons)}")


if __name__ == "__main__":
    main()
