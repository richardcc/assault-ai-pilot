# assault_sim/train/eval_ppo.py

import torch
from pathlib import Path
import statistics

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.controller import RLPolicyController
from assault_sim.rl.side_controller import SideAwareController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


# -------------------------------------------------
# Evaluation config
# -------------------------------------------------
EPISODES = 50
MAX_STEPS = 50


def main():
    print(">>> PPO evaluation started")

    # -------------------------------------------------
    # Load checkpoint
    # -------------------------------------------------
    checkpoint = torch.load("assault_sim/checkpoints/ppo_phase01.pt")

    policy = PolicyNet(
        input_dim=checkpoint["input_dim"],
        max_actions=checkpoint["max_actions"],
    )
    policy.load_state_dict(checkpoint["model_state_dict"])
    policy.eval()

    print("✅ Loaded PPO checkpoint")

    rl_controller = RLPolicyController(policy)
    heuristic_controller = TacticalPathHeuristic()

    controller = SideAwareController(
        rl_controller=rl_controller,
        heuristic_controller=heuristic_controller,
        rl_side="GE",
    )

    # -------------------------------------------------
    # Environment
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    sim_env = SimEnv(sim_config, controller=controller)
    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    vp_scores = []
    steps_taken = []
    wins = 0

    # -------------------------------------------------
    # Evaluation loop
    # -------------------------------------------------
    for ep in range(EPISODES):
        state = env.reset()
        done = False
        steps = 0

        while not done and steps < MAX_STEPS:
            action = controller.choose_action(state)
            if action is None:
                break

            state, _, done, _ = env.step(action)
            steps += 1

        vp = state.vp_tracker.total_points if state.vp_tracker else 0

        vp_scores.append(vp)
        steps_taken.append(steps)

        if vp > 0:
            wins += 1

        print(f"[EVAL {ep}] VP={vp} steps={steps}")

    # -------------------------------------------------
    # Metrics
    # -------------------------------------------------
    print("\n=== EVALUATION SUMMARY ===")
    print(f"Episodes:       {EPISODES}")
    print(f"Win rate:       {wins / EPISODES:.2%}")
    print(f"Avg VP:         {statistics.mean(vp_scores):.2f}")
    print(f"Avg steps:      {statistics.mean(steps_taken):.1f}")
    print(f"Median steps:   {statistics.median(steps_taken)}")
    print("==========================")

    print("\n>>> PPO evaluation finished")


if __name__ == "__main__":
    main()
