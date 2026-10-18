from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


CHANNELS = [
    ("mcts_success_prob_proxy", "mcts_success_prob_proxy_source", "mcts_success_prob_proxy_available"),
    ("mcts_success_component", "mcts_success_component_source", "mcts_success_component_available"),
    ("vp_horizon", "vp_horizon_source", "vp_horizon_available"),
    ("reaction_exposure_component", "reaction_exposure_component_source", "reaction_exposure_component_available"),
]


def _iter_step_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    models = list(payload.get("models", []) or [])
    for model in models:
        eval_history = list((model or {}).get("eval_history", []) or [])
        for eval_row in eval_history:
            eval_id = str((eval_row or {}).get("eval_id", "") or "")
            results = list((eval_row or {}).get("results", []) or [])
            for result in results:
                agent_name = str((result or {}).get("agent_name", "") or "")
                matchup_profile = str((result or {}).get("matchup_profile", "") or "")
                steps = list((result or {}).get("eval_decision_steps_top", []) or [])
                for step in steps:
                    row = dict(step or {})
                    row["_eval_id"] = eval_id
                    row["_agent_name"] = agent_name
                    row["_matchup_profile"] = matchup_profile
                    out.append(row)
    return out


def _missing_channels(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for channel, _source_key, available_key in CHANNELS:
        if not bool(row.get(available_key, False)):
            missing.append(channel)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trace channel source/availability per eval decision step."
    )
    parser.add_argument(
        "--catalog",
        default="runs_curriculum/experiments/reporting/model_catalog_latest.json",
        help="Path to model_catalog_latest.json",
    )
    parser.add_argument("--eval-id", default="", help="Filter by eval_id")
    parser.add_argument("--agent-name", default="", help="Filter by result.agent_name")
    parser.add_argument("--matchup-profile", default="", help="Filter by result.matchup_profile")
    parser.add_argument(
        "--out-csv",
        default="",
        help="Optional CSV output path (step-level rows with channel status).",
    )
    parser.add_argument(
        "--max-missing-rows",
        type=int,
        default=120,
        help="Max rows printed in missing rows section.",
    )
    args = parser.parse_args()

    catalog_path = Path(args.catalog).resolve()
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog not found: {catalog_path}")

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    rows = _iter_step_rows(payload)
    if args.eval_id:
        rows = [r for r in rows if str(r.get("_eval_id", "")) == str(args.eval_id)]
    if args.agent_name:
        rows = [r for r in rows if str(r.get("_agent_name", "")) == str(args.agent_name)]
    if args.matchup_profile:
        rows = [
            r
            for r in rows
            if str(r.get("_matchup_profile", "")) == str(args.matchup_profile)
        ]

    print(f"catalog={catalog_path}")
    print(f"rows_total={len(rows)}")
    if not rows:
        return 0

    for channel, source_key, available_key in CHANNELS:
        counts = Counter((str(r.get(source_key, "missing")), bool(r.get(available_key, False))) for r in rows)
        print(f"\n[{channel}]")
        for (src, available), n in counts.most_common():
            print(f"  source={src:28s} available={str(available):5s} rows={n}")

    print("\n[missing_by_step]")
    shown = 0
    for r in rows:
        missing = _missing_channels(r)
        if not missing:
            continue
        step = int(r.get("step", 0) or 0)
        action_id = str(r.get("action_id", "") or "")
        eval_id = str(r.get("_eval_id", "") or "")
        src_tuple = ", ".join(
            f"{ch}:{str(r.get(src_key, 'missing'))}"
            for ch, src_key, _av_key in CHANNELS
        )
        print(
            f"  eval={eval_id} step={step:4d} action={action_id} "
            f"missing={';'.join(missing)} sources=({src_tuple})"
        )
        shown += 1
        if shown >= max(1, int(args.max_missing_rows)):
            print(f"  ... truncated at {shown} rows")
            break

    if args.out_csv:
        out_path = Path(args.out_csv).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "eval_id",
            "agent_name",
            "matchup_profile",
            "step",
            "action_id",
        ]
        for channel, source_key, available_key in CHANNELS:
            header.extend([f"{channel}_source", f"{channel}_available"])
        header.append("missing_channels")
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for r in rows:
                rec = [
                    str(r.get("_eval_id", "")),
                    str(r.get("_agent_name", "")),
                    str(r.get("_matchup_profile", "")),
                    int(r.get("step", 0) or 0),
                    str(r.get("action_id", "") or ""),
                ]
                for channel, source_key, available_key in CHANNELS:
                    rec.append(str(r.get(source_key, "missing")))
                    rec.append(bool(r.get(available_key, False)))
                rec.append(";".join(_missing_channels(r)))
                writer.writerow(rec)
        print(f"\nCSV written: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

