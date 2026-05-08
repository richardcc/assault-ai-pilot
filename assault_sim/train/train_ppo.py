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


# -------------------------------------------------
# PPO Hyperparameters
# -------------------------------------------------
TOTAL_EPISODES = 800
ROLLOUT_STEPS = 64
PPO_EPOCHS = 4

CLIP_EPS = 0.2
GAMMA = 0.99

VALUE_COEF = 0.25
ENTROPY_COEF = 0.01


def main():
    print(">>> PPO training started")

    # -------------------------------------------------
    # Config & scenario
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    rl_side = "US"

    # -------------------------------------------------
    # Environment
    # -------------------------------------------------
    sim_env = SimEnv(sim_config, controller=None)
    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
    )

    # -------------------------------------------------
    # Reset environment & infer input_dim
    # -------------------------------------------------
    obs = env.reset()
    input_dim = obs.shape[0]
    max_turns = sim_env.scenario.max_turns

    print(f">>> OBS DIM USED FOR TRAINING: {input_dim}")

    # -------------------------------------------------
    # Policy & optimizer
    # -------------------------------------------------
    policy = PolicyNet(input_dim=input_dim, max_actions=64)
    optimizer = optim.Adam(policy.parameters(), lr=3e-4)

    heuristic_controller = TacticalPathHeuristic()

    # -------------------------------------------------
    # Controllers
    # -------------------------------------------------
    rl_controller = RLPolicyController(
        policy_net=policy,
        rl_side=rl_side,
        max_turns=max_turns,
    )

    controller = SideAwareController(
        rl_controller=rl_controller,
        heuristic_controller=heuristic_controller,
        rl_side=rl_side,
    )

    sim_env.controller = controller

    episode = 0

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

        while steps < ROLLOUT_STEPS:
            game_state = sim_env.game_state
            action = controller.choose_action(game_state, obs)

            if action is None:
                obs = env.reset()
                continue

            took_rl_action = rl_controller.last_rl_action

            if took_rl_action:
                obs_buf.append(obs)
                act_buf.append(rl_controller.last_action_index)
                old_logp_buf.append(rl_controller.last_log_prob.detach())
                value_buf.append(rl_controller.last_value.detach())

            next_obs, reward, done, info = env.step(action)

            if took_rl_action:
                reward_buf.append(reward)
                done_buf.append(done)

            obs = next_obs
            steps += 1

            if done:
                obs = env.reset()
                episode += 1
                break

        # -------------------------------------------------
        # Skip PPO update if no RL actions occurred
        # -------------------------------------------------
        if len(value_buf) == 0:
            obs = env.reset()
            episode += 1
            print("[ROLLOUT SKIPPED] no PPO actions in rollout")
            continue

        # -------------------------------------------------
        # Compute returns
        # -------------------------------------------------
        returns = []
        G = 0.0
        for r, d in zip(reversed(reward_buf), reversed(done_buf)):
            G = r + GAMMA * G * (1 - int(d))
            returns.insert(0, G)

        returns = torch.tensor(returns, dtype=torch.float32)
        values = torch.stack(value_buf)

        advantages = returns - values

        # ✅ CRITICAL FIX: do NOT normalize if only 1 sample
        if advantages.numel() > 1:
            advantages = (advantages - advantages.mean()) / (
                advantages.std() + 1e-8
            )

        obs_t = torch.tensor(np.array(obs_buf), dtype=torch.float32)
        act_t = torch.tensor(act_buf, dtype=torch.long)
        old_logp_t = torch.stack(old_logp_buf)

        # -------------------------------------------------
        # PPO Update
        # -------------------------------------------------
        for _ in range(PPO_EPOCHS):
            logits, new_values = policy(obs_t)

            # Safety guard (optional but helpful)
            if torch.isnan(logits).any():
                print("⚠️ NaNs detected in logits, skipping update")
                continue

            dist_action = dist.Categorical(logits=logits)
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

        print(f"[ROLLOUT DONE] episode={episode} loss={loss.item():.4f}")

    # -------------------------------------------------
    # Save checkpoint
    # -------------------------------------------------
    checkpoint_dir = (
        Path(__file__).resolve().parent.parent / "checkpoints"
    )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = checkpoint_dir / f"ppo_{rl_side}_phase01.pt"

    torch.save(
        {
            "model_state_dict": policy.state_dict(),
            "input_dim": input_dim,
            "max_actions": 64,
            "rl_side": rl_side,
        },
        checkpoint_path,
    )

    print(f">>> PPO checkpoint saved to {checkpoint_path}")
    print(">>> PPO training finished")

    # -------------------------------------------------
    # Print combat metrics
    # -------------------------------------------------
    print("\n=== TRAINING COMBAT METRICS ===")
    print(f"RL attacks:        {env.rl_attacks}")
    print(f"RL total damage:   {env.rl_damage}")
    print(f"RL kills:          {env.rl_kills}")
    print()
    print(f"Heuristic attacks: {env.heuristic_attacks}")
    print(f"Heuristic damage:  {env.heuristic_damage}")
    print(f"Heuristic kills:   {env.heuristic_kills}")


if __name__ == "__main__":
    main()