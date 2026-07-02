from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator
from voec_sim.ui_contract.timeline import build_episode_timeline


def _policy_from_name(name: str):
    policy = str(name).strip().lower()
    if policy == "random":
        return lambda legal: random.choice(legal)
    return lambda legal: legal[0]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export VOEC episode timeline to JSON.")
    parser.add_argument(
        "--voec-config",
        default="voec_sim/configs/voec_config.yaml",
        help="Path to VOEC YAML config.",
    )
    parser.add_argument(
        "--scenario",
        default="",
        help="Scenario id override. Default comes from VOEC config.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Episode seed.")
    parser.add_argument(
        "--policy",
        default="first",
        choices=["first", "random"],
        help="Policy used to choose legal actions.",
    )
    parser.add_argument("--max-steps", type=int, default=200, help="Max episode steps.")
    parser.add_argument(
        "--out",
        default="runs/ui_timeline_latest.json",
        help="Output JSON path.",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    voec_cfg = load_voec_config(Path(args.voec_config))
    scenario_id = str(args.scenario).strip() or voec_cfg.default_scenario_id

    sim = VOECSimulator(assets=voec_cfg.assets)
    timeline = build_episode_timeline(
        sim=sim,
        scenario_id=scenario_id,
        seed=int(args.seed),
        policy_fn=_policy_from_name(args.policy),
        max_steps=int(args.max_steps),
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timeline.to_dict(), indent=2), encoding="utf-8")
    print(f"[VOEC] timeline_exported={out}")


if __name__ == "__main__":
    main()
