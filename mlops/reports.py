from __future__ import annotations

from typing import Any


def build_comparison_summary(bench_payload: dict[str, Any]) -> dict[str, Any]:
    rows = list(bench_payload.get("results", []) or [])
    by_name = {str(r.get("agent_name", "")): dict(r) for r in rows}
    muzero = by_name.get("muzero_stub", {})
    baseline = by_name.get("baseline_random", {})
    return {
        "scenario_id": bench_payload.get("scenario_id", ""),
        "run_id": bench_payload.get("run_id", ""),
        "agents": sorted([k for k in by_name.keys() if k]),
        "metrics": {
            "muzero_win_rate": float(muzero.get("win_rate", 0.0) or 0.0),
            "baseline_win_rate": float(baseline.get("win_rate", 0.0) or 0.0),
            "win_rate_delta_vs_baseline": float(muzero.get("win_rate", 0.0) or 0.0)
            - float(baseline.get("win_rate", 0.0) or 0.0),
        },
        "phase_2_9_promotion_gate": dict(bench_payload.get("phase_2_9_promotion_gate", {}) or {}),
    }


def build_decision_report(comparison_summary: dict[str, Any]) -> dict[str, Any]:
    gate = dict(comparison_summary.get("phase_2_9_promotion_gate", {}) or {})
    status = str(gate.get("status", "UNKNOWN")).upper()
    return {
        "decision": "PROMOTE" if status == "PASS" else "HOLD",
        "gate_status": status,
        "checks": dict(gate.get("checks", {}) or {}),
        "advisory": dict(gate.get("advisory", {}) or {}),
    }
