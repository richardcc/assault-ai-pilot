# assault_sim/train/train.py

from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.debug.console_observer import ConsoleObserver

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


def main():
    # -----------------------------------------------------
    # 1. Load simulation configuration
    # -----------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )

    # -----------------------------------------------------
    # 2. Create simulation environment
    # -----------------------------------------------------
    sim_env = SimEnv(sim_config, debug_config=sim_config.debug)
    training_env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    # -----------------------------------------------------
    # 3. Observers
    # -----------------------------------------------------
    observer = ConsoleObserver()
    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)

    # -----------------------------------------------------
    # 4. Controllers (heuristics)
    # -----------------------------------------------------
    # 👉 MISMO heurístico para ambos bandos (por ahora)
    controllers = {
        "GE": TacticalPathHeuristic(),
        "US": TacticalPathHeuristic(),
    }

    # -----------------------------------------------------
    # 5. Reset
    # -----------------------------------------------------
    state = training_env.reset()
    done = False

    # -----------------------------------------------------
    # 6. Main loop
    # -----------------------------------------------------
    while not done:
        active = state.active_unit

        if active is None:
            action = None
        else:
            controller = controllers.get(active.side)
            action = controller.choose_action(state)

        state, reward, done, info = training_env.step(action)

    print("Simulation finished.")
    if state.vp_tracker:
        print(f"Final VP: {state.vp_tracker.total_points}")


if __name__ == "__main__":
    main()