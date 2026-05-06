# assault_sim/train/train.py

from pathlib import Path
import argparse

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


# -----------------------------------------------------
# CLI argument parsing (NO game logic here)
# -----------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Assault simulation runner"
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("assault_sim/config/sim_config.yaml"),
        help="Path to sim_config.yaml"
    )

    parser.add_argument(
        "--scenario",
        type=str,
        help="Override scenario name (e.g. phase01_seq001_initial_contact)"
    )

    parser.add_argument(
        "--seed",
        type=int,
        help="Override random seed"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (EventBus ON)"
    )

    parser.add_argument(
        "--no-observability",
        action="store_true",
        help="Disable EventBus (same as debug OFF)"
    )

    return parser.parse_args()


def main():
    # -----------------------------------------------------
    # 0. Parse CLI arguments
    # -----------------------------------------------------
    args = parse_args()

    # -----------------------------------------------------
    # 1. Load base simulation configuration
    # -----------------------------------------------------
    sim_config = load_sim_config(args.config)

    # -----------------------------------------------------
    # 1.1 Apply CLI overrides
    # -----------------------------------------------------

    # ✅ Scenario override (THIS was missing before)
    if args.scenario:
        sim_config.scenario_name = args.scenario

    if args.seed is not None:
        sim_config.seed = args.seed

    # ✅ EventBus is controlled ONLY via DebugConfig
    debug_enabled = args.debug and not args.no_observability
    debug_cfg = DebugConfig(enabled=debug_enabled)

    # -----------------------------------------------------
    # 2. Controller (heuristic)
    # -----------------------------------------------------
    controller = TacticalPathHeuristic()

    # -----------------------------------------------------
    # 3. Create simulation environment (ORIGINAL SIGNATURE)
    # -----------------------------------------------------
    sim_env = SimEnv(
        sim_config,
        debug_config=debug_cfg,
        controller=controller,
    )

    training_env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        scenario_override=args.scenario,  # kept for future curriculum logic
    )

    # -----------------------------------------------------
    # 4. Observers (only if EventBus exists)
    # -----------------------------------------------------
    observer = ConsoleObserver()
    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)

    # -----------------------------------------------------
    # 5. Reset
    # -----------------------------------------------------
    state = training_env.reset()
    done = False

    # -----------------------------------------------------
    # 6. Main loop
    # -----------------------------------------------------
    while not done:
        state, reward, done, info = training_env.step(None)

    print("Simulation finished.")
    if state.vp_tracker:
        print(f"Final VP: {state.vp_tracker.total_points}")


if __name__ == "__main__":
    main()
