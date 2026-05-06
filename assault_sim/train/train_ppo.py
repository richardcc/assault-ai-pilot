# assault_sim/train/train_ppo.py

import torch
import torch.optim as optim
import torch.distributions as dist
import numpy as np
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.controller import RLPolicyController
from assault_sim.rl.side_controller import SideAwareController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.state_encoder import encode_state


# -------------------------------------------------
# PPO Hyperparameters
# -------------------------------------------------
TOTAL_EPISODES = 300
ROLLOUT_STEPS = 64
PPO_EPOCHS = 4

CLIP_EPS = 0.2
GAMMA = 0.99

VALUE_COEF = 0.5
ENTROPY_COEF = 0.01

MAX_STEPS = 50
STEP_PENALTY = -0.01


def main():
    print(">>> PPO training started (final, fixed)")

    # -------------------------------------------------
    # Config & scenario
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    # -------------------------------------------------
    # Policy & optimizer
    # -------------------------------------------------
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

    episode = 0
    state = env.reset()

    # -------------------------------------------------
    # PPO Main Loop
    # -------------------------------------------------
    while episode < TOTAL_EPISODES:
        print(f"\n[ROLLOUT start @ episode {episode}]")

        obs_buf = []
        act_buf = []
        old_logp_buf = []
        value_buf = []
        reward_buf = []
        done_buf = []

        steps = 0

        # -------------------------
        # Collect rollout
        # -------------------------
        while steps < ROLLOUT_STEPS:
            action = controller.choose_action(state)

            if action is None:
                state = env.reset()
                continue

            # Only RL-controlled side contributes to learning
            if state.active_unit and state.active_unit.side == "GE":
                obs_buf.append(encode_state(state))
                act_buf.append(rl_controller.last_action_index)
                old_logp_buf.append(rl_controller.last_log_prob.detach())
                value_buf.append(rl_controller.last_value.detach())

            next_state, _, done, _ = env.step(action)

            reward_buf.append(STEP_PENALTY)
            done_buf.append(done)

            state = next_state
            steps += 1

            if done or steps >= MAX_STEPS:
                # ✅ Añadimos el VP final como reward terminal
                final_vp = (
                    state.vp_tracker.total_points
                    if state.vp_tracker else 0
                )
                if reward_buf:
                    reward_buf[-1] += final_vp

                state = env.reset()
                episode += 1
                if episode >= TOTAL_EPISODES:
                    break

        # -------------------------
        # Compute returns (aligned)
        # -------------------------
        returns = []
        G = 0.0
        for r, d in zip(reversed(reward_buf), reversed(done_buf)):
            G = r + GAMMA * G * (1 - int(d))
            returns.insert(0, G)

        returns = torch.tensor(returns, dtype=torch.float32)

        values = torch.stack(value_buf)

        # ✅ Alineamos explícitamente longitudes
        returns = returns[: len(values)]

        advantages = returns - values
        advantages = (advantages - advantages.mean()) / (
            advantages.std() + 1e-8
        )

        # -------------------------
        # Prepare tensors (sin warning)
        # -------------------------
        obs_t = torch.tensor(np.array(obs_buf), dtype=torch.float32)
        act_t = torch.tensor(act_buf, dtype=torch.long)
        old_logp_t = torch.stack(old_logp_buf)

        # -------------------------
        # PPO Update
        # -------------------------
        for _ in range(PPO_EPOCHS):
            logits, new_values = policy(obs_t)

            action_logits = logits[torch.arange(len(act_t)), act_t]
            dist_action = dist.Categorical(logits=action_logits)

            new_logp = dist_action.log_prob(act_t)
            entropy = dist_action.entropy().mean()

            ratio = torch.exp(new_logp - old_logp_t)

            clipped = torch.clamp(
                ratio,
                1.0 - CLIP_EPS,
                1.0 + CLIP_EPS,
            )

            policy_loss = -torch.min(
                ratio * advantages,
                clipped * advantages,
            ).mean()

            value_loss = (returns - new_values.squeeze()).pow(2).mean()

            loss = (
                policy_loss
                + VALUE_COEF * value_loss
                - ENTROPY_COEF * entropy
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        print(
            f"[ROLLOUT DONE] episode={episode} "
            f"loss={loss.item():.4f}"
        )

    # -------------------------------------------------
    # Save PPO checkpoint (robust path)
    # -------------------------------------------------
    checkpoint_dir = (
        Path(__file__).resolve()
        .parent.parent / "checkpoints"
    )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = checkpoint_dir / "ppo_phase01.pt"

    torch.save(
        {
            "model_state_dict": policy.state_dict(),
            "input_dim": 4,
            "max_actions": 64,
        },
        checkpoint_path,
    )

    print(f">>> PPO checkpoint saved to {checkpoint_path}")
    print(">>> PPO training finished")


if __name__ == "__main__":
    main()
