import torch
import torch.optim as optim
import torch.distributions as dist
import numpy as np
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RL_SIDE = "US"

TOTAL_EPISODES = 1000
ROLLOUT_STEPS = 64
PPO_EPOCHS = 4

CLIP_EPS = 0.2
GAMMA = 0.99
LAMBDA = 0.95
VALUE_COEF = 0.5
ENTROPY_COEF = 0.03


# -------------------------------------------------
# GAE
# -------------------------------------------------
def compute_gae(rewards, values, dones, gamma, lam):
    advantages = []
    gae = 0.0

    values = values + [0.0]  # bootstrap

    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * values[t + 1] * (1 - dones[t]) - values[t]
        gae = delta + gamma * lam * (1 - dones[t]) * gae
        advantages.insert(0, gae)

    return advantages


def main():
    print(">>> PPO HRL training started")
    print(f">>> RL SIDE: {RL_SIDE}")

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    sim_config = load_sim_config(Path("assault_sim/config/sim_config.yaml"))
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    sim_env = SimEnv(sim_config, controller=None)
    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=RL_SIDE,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    print(f">>> OBS DIM: {input_dim}")

    # -------------------------------------------------
    # POLICY
    # -------------------------------------------------
    num_options = len(TacticalOption)

    policy = PolicyNet(input_dim=input_dim, max_actions=num_options)
    optimizer = optim.Adam(policy.parameters(), lr=3e-4)

    option_policy = OptionPolicy(policy)
    heuristic_controller = TacticalPathHeuristic()
    option_executor = OptionExecutor(heuristic_controller)

    hrl_controller = HRLController(
        option_policy=option_policy,
        option_executor=option_executor,
        rl_side=RL_SIDE,
    )

    rollout_idx = 0

    # -------------------------------------------------
    # PPO LOOP
    # -------------------------------------------------
    while rollout_idx < TOTAL_EPISODES:

        print(f"\n[ROLLOUT {rollout_idx}]")

        obs_buf = []
        act_buf = []
        old_logp_buf = []
        value_buf = []
        reward_buf = []
        done_buf = []

        steps = 0

        while steps < ROLLOUT_STEPS:

            state = env.state
            active = state.active_unit if state else None

            # avanzar si no hay unidad
            if active is None:
                obs, _, done, _ = env.step(None)
                steps += 1
                continue

            # -------------------------
            # DECISION
            # -------------------------
            if active.side == RL_SIDE:

                action = hrl_controller.choose_action(state, obs)

                # ✅ GUARDAMOS TEMPORALMENTE (NO EN BUFFER)
                last_obs = obs
                last_action = option_policy.last_option.value
                last_logp = option_policy.last_log_prob.detach()
                last_value = option_policy.last_value.item()

                reward_for_rl = True

            else:
                action = heuristic_controller.choose_action(state)
                reward_for_rl = False

            if action is None:
                obs, _, done, _ = env.step(None)
                steps += 1
                continue

            # -------------------------
            # STEP
            # -------------------------
            next_obs, reward, done, _ = env.step(action)

            # ✅ SOLO AQUÍ GUARDAMOS TODO (FIX CRÍTICO)
            if reward_for_rl:

                obs_buf.append(last_obs)
                act_buf.append(last_action)
                old_logp_buf.append(last_logp)
                value_buf.append(last_value)

                reward_buf.append(reward)
                done_buf.append(done)

            obs = next_obs
            steps += 1

            if done:
                obs = env.reset()

        # -------------------------
        # VALIDACIÓN
        # -------------------------
        if len(reward_buf) == 0:
            rollout_idx += 1
            continue

        assert len(obs_buf) == len(reward_buf), "Buffer mismatch"

        # -------------------------
        # GAE
        # -------------------------
        advantages = compute_gae(
            reward_buf,
            value_buf,
            done_buf,
            GAMMA,
            LAMBDA
        )

        returns = [a + v for a, v in zip(advantages, value_buf)]

        advantages = torch.tensor(advantages, dtype=torch.float32)
        returns = torch.tensor(returns, dtype=torch.float32)

        if advantages.numel() > 1:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        obs_t = torch.tensor(np.array(obs_buf), dtype=torch.float32)
        act_t = torch.tensor(act_buf, dtype=torch.long)
        old_logp_t = torch.stack(old_logp_buf)

        # -------------------------
        # PPO UPDATE
        # -------------------------
        for _ in range(PPO_EPOCHS):

            logits, values = policy(obs_t)
            dist_opt = dist.Categorical(logits=logits)

            logp = dist_opt.log_prob(act_t)
            ratio = torch.exp(logp - old_logp_t)

            clipped = torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS)

            policy_loss = -torch.min(
                ratio * advantages,
                clipped * advantages
            ).mean()

            value_loss = (returns - values.squeeze()).pow(2).mean()
            entropy = dist_opt.entropy().mean()

            loss = policy_loss + VALUE_COEF * value_loss - ENTROPY_COEF * entropy

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        avg_reward = sum(reward_buf) / len(reward_buf) if reward_buf else 0.0
        print(f"[ROLLOUT {rollout_idx}] avg_reward={avg_reward:.2f} steps={len(reward_buf)}")
      
        
        rollout_idx += 1

    # -------------------------------------------------
    # SAVE
    # -------------------------------------------------
    ckpt_path = Path("assault_sim/checkpoints") / f"ppo_{RL_SIDE}.pt"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "model_state_dict": policy.state_dict(),
            "input_dim": input_dim,
            "max_actions": num_options,
        },
        ckpt_path,
    )

    print(f">>> TRAINING FINISHED: {ckpt_path}")


if __name__ == "__main__":
    main()