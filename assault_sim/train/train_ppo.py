import torch
import torch.optim as optim
import torch.distributions as torch_dist

import numpy as np
from pathlib import Path

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.engine.env_factory import create_env
from assault_sim.engine.hrl_factory import create_hrl_controller
from assault_sim.engine.rollout import collect_rollout


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RL_SIDE = "US"

TOTAL_EPISODES = 1000
ROLLOUT_STEPS = 64
PPO_EPOCHS = 6

CLIP_EPS = 0.15
GAMMA = 0.99
LAMBDA = 0.95
VALUE_COEF = 0.5
ENTROPY_COEF = 0.05


# -------------------------------------------------
# GAE
# -------------------------------------------------
def compute_gae(rewards, values, dones, gamma, lam):
    advantages = []
    gae = 0.0

    values = values + [0.0]

    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * values[t + 1] * (1 - dones[t]) - values[t]
        gae = delta + gamma * lam * (1 - dones[t]) * gae
        advantages.insert(0, gae)

    return advantages


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    print(">>> PPO HRL (ENGINE MODE)")
    print(f">>> RL SIDE: {RL_SIDE}")

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    env = create_env(
        config_path=Path("assault_sim/config/sim_config.yaml"),
        scenario="phase01_seq001_initial_contact",
        rl_side=RL_SIDE,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    # -------------------------------------------------
    # POLICY
    # -------------------------------------------------
    num_options = len(TacticalOption)

    policy = PolicyNet(input_dim=input_dim, max_actions=num_options)
    optimizer = optim.Adam(policy.parameters(), lr=3e-4)

    controller = create_hrl_controller(policy, RL_SIDE)

    rollout_idx = 0

    # -------------------------------------------------
    # TRAIN LOOP
    # -------------------------------------------------
    while rollout_idx < TOTAL_EPISODES:

        print(f"\n[ROLLOUT {rollout_idx}]")

        rollout = collect_rollout(
            env=env,
            controller=controller,
            steps=ROLLOUT_STEPS,
        )

        if len(rollout["rewards"]) == 0:
            print("⚠️ empty rollout")
            rollout_idx += 1
            continue

        # -------------------------------------------------
        # TENSORS
        # -------------------------------------------------
        obs_t = torch.tensor(np.array(rollout["obs"]), dtype=torch.float32)
        act_t = torch.tensor(rollout["actions"], dtype=torch.long)
        old_logp_t = torch.stack(rollout["logp"])
        value_buf = rollout["values"]

        # -------------------------------------------------
        # GAE
        # -------------------------------------------------
        advantages = compute_gae(
            rollout["rewards"],
            value_buf,
            rollout["dones"],
            GAMMA,
            LAMBDA,
        )

        returns = [a + v for a, v in zip(advantages, value_buf)]

        advantages = torch.tensor(advantages, dtype=torch.float32)
        returns = torch.tensor(returns, dtype=torch.float32)

        if advantages.numel() > 1:
            advantages = (advantages - advantages.mean()) / (
                advantages.std() + 1e-8
            )

        # -------------------------------------------------
        # PPO UPDATE
        # -------------------------------------------------
        for _ in range(PPO_EPOCHS):

            logits, values = policy(obs_t)
            dist = torch_dist.Categorical(logits=logits)

            logp = dist.log_prob(act_t)
            ratio = torch.exp(logp - old_logp_t)

            clipped = torch.clamp(
                ratio,
                1 - CLIP_EPS,
                1 + CLIP_EPS,
            )

            policy_loss = -torch.min(
                ratio * advantages,
                clipped * advantages
            ).mean()

            value_loss = (returns - values.squeeze()).pow(2).mean()
            entropy = dist.entropy().mean()

            loss = (
                policy_loss
                + VALUE_COEF * value_loss
                - ENTROPY_COEF * entropy
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        avg_reward = sum(rollout["rewards"]) / len(rollout["rewards"])

        print(f"[ROLLOUT {rollout_idx}] reward={avg_reward:.3f}")

        rollout_idx += 1

    # -------------------------------------------------
    # SAVE
    # -------------------------------------------------
    ckpt = Path("assault_sim/checkpoints/ppo_us.pt")
    ckpt.parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "model_state_dict": policy.state_dict(),
            "input_dim": input_dim,
            "max_actions": num_options,
        },
        ckpt,
    )

    print(f">>> SAVED: {ckpt}")


if __name__ == "__main__":
    main()
