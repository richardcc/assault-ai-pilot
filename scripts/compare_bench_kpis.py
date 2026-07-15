from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_row(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results") or payload.get("rows") or []
    if not rows:
        raise ValueError(f"No benchmark rows in {path}")
    return dict(rows[0] or {})


def _safe_rate(bucket: dict[str, Any], key: str) -> float:
    try:
        return float(bucket.get(key, 0.0))
    except Exception:
        return 0.0


def _kpi_view(row: dict[str, Any]) -> dict[str, Any]:
    winner_rates = dict(row.get("winner_side_rates") or {})
    outcome_rates = dict(row.get("scenario_outcome_class_rates") or {})
    vp_net = dict(row.get("vp_net_avg_by_side") or row.get("avg_vp_net_by_side") or {})
    return {
        "tracked_side": row.get("tracked_side"),
        "tracked_captured_avg": float(row.get("tracked_captured_avg") or 0.0),
        "winner_it_rate": _safe_rate(winner_rates, "IT"),
        "winner_us_rate": _safe_rate(winner_rates, "US"),
        "defeat_rate": _safe_rate(outcome_rates, "defeat"),
        "victory_rate": _safe_rate(outcome_rates, "victory"),
        "vp_net_it": float(vp_net.get("IT", 0.0)),
        "vp_net_us": float(vp_net.get("US", 0.0)),
    }


def _delta(v2: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in v2.items():
        base_val = baseline.get(key)
        if isinstance(val, (int, float)) and isinstance(base_val, (int, float)):
            out[key] = float(val) - float(base_val)
        else:
            out[key] = None if val == base_val else {"baseline": base_val, "v2": val}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare KPI deltas across two bench JSON files.")
    parser.add_argument("--baseline", required=True, help="Baseline bench JSON path.")
    parser.add_argument("--v2", required=True, help="V2 bench JSON path.")
    args = parser.parse_args()

    baseline_path = Path(args.baseline).resolve()
    v2_path = Path(args.v2).resolve()

    baseline_row = _load_row(baseline_path)
    v2_row = _load_row(v2_path)

    baseline_kpis = _kpi_view(baseline_row)
    v2_kpis = _kpi_view(v2_row)
    delta_kpis = _delta(v2_kpis, baseline_kpis)

    report = {
        "baseline_file": str(baseline_path),
        "v2_file": str(v2_path),
        "baseline": baseline_kpis,
        "v2": v2_kpis,
        "delta_v2_minus_baseline": delta_kpis,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
