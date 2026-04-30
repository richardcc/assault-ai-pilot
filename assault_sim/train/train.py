# assault_sim/train/train.py
#
# Training entry point.
# Wires together:
# - simulation config (YAML)
# - observability (DebugConfig)
# - SimEnv + TrainingEnv
# - ConsoleObserver
#
# Produces rich, structured output per turn and per action
# when observability is enabled in sim_config.yaml.

from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.heuristics.heuristic_base import HeuristicBase


def main():
    # -----------------------------------------------------
    # 1. Load simulation configuration (YAML)
    # -----------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )

    # Debug / observability configuration (high-level)
    print("DEBUG CONFIG:", sim_config.debug)

    # -----------------------------------------------------
    # 2. Create SimEnv with DebugConfig
    # -----------------------------------------------------
    env = SimEnv(
        sim_config,
        debug_config=sim_config.debug
    )

    # -----------------------------------------------------
    # 3. Attach console observer (structured observability)
    # -----------------------------------------------------
    if env.event_bus:
        env.event_bus.subscribe(ConsoleObserver())

    # -----------------------------------------------------
    # 4. Wrap SimEnv with TrainingEnv (controllers, env_config)
    # -----------------------------------------------------
    training_env = TrainingEnv(
        env,
        Path("assault_sim/config/env_config.json")
    )

    print("Resetting environment...")
    state = training_env.reset()

    step = 0
    done = False

    # -----------------------------------------------------
    # 5. Main simulation loop
    # -----------------------------------------------------
    while not done:
        # Select action from heuristic (deterministic baseline)
        action = HeuristicBase.choose_action(state)

        state, reward, done, _ = training_env.step(action)

        step += 1
        print(f"Step {step} | Turn {state.turn} | Reward {reward}")

    # -----------------------------------------------------
    # 6. End of simulation summary
    # -----------------------------------------------------
    print("Simulation finished.")
    print(f"Final VP: {state.vp_tracker.total_points}")
    print(f"Total steps: {step}")


if __name__ == "__main__":
    main()