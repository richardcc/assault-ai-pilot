"""
Offline Series Orchestrator (NEW)

Canonical offline analysis entry point.
"""

import sys
import argparse
from pathlib import Path
from time import time
from typing import List, Dict

# --------------------------------------------------
# PATHS
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"

MODEL_PATTERN = "ppo_*.zip"
MIN_AGE_SECONDS = 15

DEFAULT_EPISODES = 50
DEFAULT_SAVE_REPLAYS = 5
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "analysis_outputs" / "offline_series"

# --------------------------------------------------
# IMPORTS (project-local)
# --------------------------------------------------

from assault_runner.rl_runner import RLPolicyAdapter
from assault_runner.series.match_series_runner import MatchSeriesRunner
from assault_runner.analysis.save_diagnostics import save_series_results
from assault_runner.analysis.engine_diagnostics_result import EngineDiagnosticsResult

# ✅ NO imports de heurísticas aquí


# --------------------------------------------------
# MODEL DISCOVERY
# --------------------------------------------------

def find_latest_stable_model() -> Path:
    now = time()
    candidates: List[Path] = []

    for p in MODELS_DIR.glob(MODEL_PATTERN):
        age = now - p.stat().st_mtime
        if age >= MIN_AGE_SECONDS:
            candidates.append(p)

    if not candidates:
        raise FileNotFoundError(
            f"No model matching '{MODEL_PATTERN}' "
            f"older than {MIN_AGE_SECONDS}s found in {MODELS_DIR}"
        )

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    print(f"📦 Using latest stable RL model: {latest.name}")

    return latest


# --------------------------------------------------
# MAIN PIPELINE
# --------------------------------------------------

def run_offline_series(
    *,
    scenario_id: str,
    episodes: int,
    save_replays: int,
    output_dir: Path,
    debug: bool,
    mode: str,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    model_path = find_latest_stable_model()

    # --------------------------------------------------
    # MODE SEMANTICS
    # --------------------------------------------------

    if mode == "benchmark":
        deterministic = True
        base_seed = 1234
    elif mode == "evaluation":
        deterministic = False
        base_seed = 1234
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # ✅ RL policy only
    rl_policy = RLPolicyAdapter(
        model_path=str(model_path),
        deterministic=deterministic,
    )

    # ✅ Heuristic enemy handled INSIDE the environment
    runner = MatchSeriesRunner(
        scenario_id=scenario_id,
        policy_A=rl_policy,
        policy_B=None,
        episodes=episodes,
        save_replays=save_replays,
        seed=base_seed,
        debug=debug,
    )

    if debug:
        print(f"🛠 Engine debug ENABLED ({mode} mode)")

    print(f"▶ Running offline match series [{mode}]")
    result = runner.run()

    # --------------------------------------------------
    # ENGINE DIAGNOSTICS
    # --------------------------------------------------

    engine_steps: List[Dict] = []

    for game in result["games"]:
        for frame in game.get("frames", []):
            if "diagnostics_event" in frame:
                engine_steps.append(frame["diagnostics_event"])

    engine_diagnostics = EngineDiagnosticsResult.from_steps(engine_steps)

    # --------------------------------------------------
    # SERIES CONFIG
    # --------------------------------------------------

    series_config = {
        "analysis_mode": mode,
        "scenario": scenario_id,
        "episodes": episodes,
        "policy_A": {
            "name": "RL",
            "side": "US",
        },
        "policy_B": {
            "name": "heuristic_enemy",
            "side": "GE",
        },
        "debug": debug,
    }

    # --------------------------------------------------
    # Persist results
    # --------------------------------------------------

    save_series_results(
        output_dir=str(output_dir),
        series_summary={
            "config": series_config,
            "outcomes": result["outcomes"],
            "rates": result["rates"],
            "engine_diagnostics": engine_diagnostics.to_dict(),
        },
        game_diagnostics=[
            engine_diagnostics.to_dict()
        ],
        replays=result["replays"],
    )

    print("✅ Offline series analysis completed")
    print(f"📁 Results written to: {output_dir}")


# --------------------------------------------------
# ENTRY POINT (CLI)
# --------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Offline batch evaluation using the latest stable RL snapshot"
    )

    parser.add_argument("--scenario", required=True)
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--save-replays", type=int, default=DEFAULT_SAVE_REPLAYS)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--mode",
        choices=["benchmark", "evaluation"],
        default="benchmark",
        help="Analysis mode: benchmark (deterministic) or evaluation (stochastic)",
    )
    parser.add_argument("--debug", action="store_true", default=False)

    args = parser.parse_args()

    try:
        run_offline_series(
            scenario_id=args.scenario,
            episodes=args.episodes,
            save_replays=args.save_replays,
            output_dir=Path(args.output),
            debug=args.debug,
            mode=args.mode,
        )
    except Exception as e:
        print("❌ Offline analysis failed:")
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()