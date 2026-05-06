# assault_sim/train/run_match_rl_vs_heuristic.py

import torch
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.controller import RLPolicyController
from assault_sim.rl.side_controller import SideAwareController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.debug.console_observer import ConsoleObserver


def main():
    print(">>> Replaying: RL (GE) vs Heuristic (US)")

    # -------------------------------------------------
    # Load trained PPO checkpoint
    # -------------------------------------------------
    checkpoint_path = (
        Path(__file__).resolve()
        .parent.parent / "checkpoints" / "ppo_phase01.pt"
    )

    checkpoint = torch.load(checkpoint_path)

    policy = PolicyNet(
        input_dim=checkpoint["input_dim"],
        max_actions=checkpoint["max_actions"],
    )
    policy.load_state_dict(checkpoint["model_state_dict"])
    policy.eval()   # 🔑 inference mode

    print("✅ PPO model loaded")

    # -------------------------------------------------
    # Controllers
    # -------------------------------------------------
    rl_controller = RLPolicyController(policy)
    heuristic_controller = TacticalPathHeuristic()

    controller = SideAwareController(
        rl_controller=rl_controller,
        heuristic_controller=heuristic_controller,
        rl_side="GE",     # RL plays GE
    )

    # -------------------------------------------------
    # Environment
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42     # 🔑 reproducible match

    sim_env = SimEnv(
        sim_config,
        controller=controller,
        debug_config=sim_config.debug,
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    # -------------------------------------------------
    # Observer (prints actions & turns)
    # -------------------------------------------------
    observer = ConsoleObserver()
    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)

    # -------------------------------------------------
    # Run one full match
    # -------------------------------------------------
    state = env.reset()
    done = False
    step = 0

    while not done:
        state, reward, done, _ = env.step(None)
        step += 1

    vp = state.vp_tracker.total_points if state.vp_tracker else 0

    print("\n=== MATCH FINISHED ===")
    print(f"Total steps: {step}")
    print(f"Final VP:    {vp}")


if __name__ == "__main__":
    main()