# assault_sim/train/train.py

from pathlib import Path
import argparse

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

RL_SIDE = "US"


# -----------------------------------------------------
# CLI
# -----------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Assault runner")

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("assault_sim/config/sim_config.yaml"),
    )
    parser.add_argument("--scenario", type=str)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-observability", action="store_true")

    return parser.parse_args()


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------
def main():
    args = parse_args()

    sim_config = load_sim_config(args.config)

    if args.scenario:
        sim_config.scenario_name = args.scenario

    if args.seed is not None:
        sim_config.seed = args.seed

    debug_cfg = DebugConfig(enabled=args.debug and not args.no_observability)

    controller = TacticalPathHeuristic()

    sim_env = SimEnv(
        sim_config,
        debug_config=debug_cfg,
        controller=None,   # control manual
    )

    training_env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=RL_SIDE,
    )

    observer = ConsoleObserver(rl_side=RL_SIDE)

    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)

    obs = training_env.reset()
    done = False

    print("\n=== SIMULATION START ===")
    print(f"Scenario: {sim_config.scenario_name}")
    print("========================\n")

    step_count = 0

    while not done:
        state = sim_env.game_state
        active = state.active_unit

        if active:
            action = controller.choose_action(state)
        else:
            action = None

        obs, reward, done, _ = training_env.step(action)

        step_count += 1

        if step_count > 500:
            print("⚠️ Forced stop")
            break

    state = sim_env.game_state

    print("\n=== SIMULATION FINISHED ===")
    print(f"Winner: {state.winner}")
    print(f"Reason: {state.end_reason}")
    print(f"Turns:  {state.turn}")

    if state.vp_tracker:
        print(f"Final VP: {state.vp_tracker.total_points}")


if __name__ == "__main__":
    main()