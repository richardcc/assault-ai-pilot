# assault_sim/train/train_rl.py

import torch
import torch.optim as optim
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.controller import RLPolicyController
from assault_sim.rl.side_controller import SideAwareController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


# -------------------------------
# Hyperparameters
# -------------------------------
EPISODES = 300
MAX_STEPS = 50
STEP_PENALTY = -0.01
FAIL_PENALTY = -1.0
VALUE_COEF = 0.5
ENTROPY_COEF = 0.01


def main():
    print(">>> Actor-Critic training started (A2C minimal)")

    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    policy = PolicyNet(input_dim=4, max_actions=64)
    optimizer = optim.Adam(policy.parameters(), lr=3e-4)

    rl_controller = RLPolicyController(policy)
    heuristic_controller = TacticalPathHeuristic()

    controller = SideAwareController(
        rl_controller=rl_controller,
        heuristic_controller=heuristic_controller,
        rl_side="GE",
    )

    sim_env = SimEnv(sim_config, controller=controller)
    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    for episode in range(EPISODES):
        print(f"\n[EP {episode}] reset")

        state = env.reset()
        done = False

        log_probs = []
        values = []
        rewards = []

        steps = 0

        while not done and steps < MAX_STEPS:
            action = controller.choose_action(state)
            if action is None:
                break

            if state.active_unit and state.active_unit.side == "GE":
                log_probs.append(rl_controller.last_log_prob)
                values.append(rl_controller.last_value)

            try:
                state, _, done, _ = env.step(action)
                reward = STEP_PENALTY
            except Exception as e:
                print(f"  ❌ env.step failed: {e}")
                reward = FAIL_PENALTY
                done = True

            rewards.append(reward)
            print(f"  step={steps} reward={reward:.2f}")
            steps += 1

        final_vp = (
            state.vp_tracker.total_points
            if state.vp_tracker else 0
        )

        returns = sum(rewards) + final_vp

        if log_probs:
            advantages = returns - torch.stack(values)

            policy_loss = -(torch.stack(log_probs) * advantages.detach()).mean()
            value_loss = advantages.pow(2).mean()

            loss = policy_loss + VALUE_COEF * value_loss

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            loss_value = loss.item()
        else:
            loss_value = 0.0

        print(
            f"[EP {episode} DONE] "
            f"steps={steps} "
            f"return={returns:.2f} "
            f"VP={final_vp} "
            f"loss={loss_value:.4f}"
        )

    print("\n>>> A2C training finished")


if __name__ == "__main__":
    main()