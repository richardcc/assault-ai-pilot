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
    # 2. Controllers (heuristics)
    # -----------------------------------------------------
    # 👉 SAME heuristic for both sides (new architecture)
    controller = TacticalPathHeuristic()

    # -----------------------------------------------------
    # 3. Create simulation environment
    #    (heuristic injected here)
    # -----------------------------------------------------
    sim_env = SimEnv(
        sim_config,
        debug_config=sim_config.debug,
        controller=controller,   # ✅ CLAVE
    )

    training_env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    # -----------------------------------------------------
    # 4. Observers
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
    # ✅ NO decision logic here
    # ✅ SimEnv + controller own decision making
    while not done:
        state, reward, done, info = training_env.step(None)

    print("Simulation finished.")
    if state.vp_tracker:
        print(f"Final VP: {state.vp_tracker.total_points}")


if __name__ == "__main__":
    main()