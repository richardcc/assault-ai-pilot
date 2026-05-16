import torch
import torch.optim as optim
import torch.distributions as torch_dist

import numpy as np
from pathlib import Path
import multiprocessing as mp

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.engine.env_factory import make_env
from assault_sim.engine.hrl_factory import create_hrl_controller
from assault_sim.engine.rollout import collect_rollout


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RL_SIDE = "US"

TOTAL_UPDATES = 4000
ROLLOUT_STEPS = 32
PPO_EPOCHS = 2

CLIP_EPS = 0.1
GAMMA = 0.99
LAMBDA = 0.95
VALUE_COEF = 0.5

NUM_ENVS = 10
BATCH_ROLLOUTS = 24


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
# ✅ WORKER LOOP (CONTINUO)
# -------------------------------------------------
def worker_loop(
    rollout_queue,
    config_path,
    scenario,
    rl_side,
    weights_queue,
    progress_queue
):

    import torch
    torch.set_num_threads(1)
    torch.cuda.is_available = lambda: False

    env = make_env(config_path, rl_side, scenario)

    obs = env.reset()
    input_dim = obs.shape[0]
    num_options = len(TacticalOption)

    from assault_sim.rl.policy_net import PolicyNet

    policy = PolicyNet(input_dim=input_dim, max_actions=num_options)
    policy.eval()

    controller = create_hrl_controller(policy, rl_side)

    # 🔥 reward progresivo
    reward_fn = env.reward_fn

    while True:

        # -------------------------------------------------
        # actualizar policy
        # -------------------------------------------------
        if not weights_queue.empty():
            new_weights = weights_queue.get()
            policy.load_state_dict(new_weights)

        # -------------------------------------------------
        # actualizar progreso (reward progresivo)
        # -------------------------------------------------
        if not progress_queue.empty():
            progress = progress_queue.get()
            reward_fn.current_update = progress

        rollout = collect_rollout(env, controller, ROLLOUT_STEPS)
        rollout_queue.put(rollout)


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(">>> Using device:", DEVICE)

    config_path = Path("assault_sim/config/sim_config.yaml")
    scenario = "phase01_seq001_initial_contact"

    # sample env
    env = make_env(config_path, RL_SIDE, scenario)
    obs = env.reset()
    input_dim = obs.shape[0]

    num_options = len(TacticalOption)

    policy = PolicyNet(input_dim=input_dim, max_actions=num_options).to(DEVICE)
    optimizer = optim.Adam(policy.parameters(), lr=3e-4)

    # -------------------------------------------------
    # 🔥 QUEUES
    # -------------------------------------------------
    rollout_queue = mp.Queue(maxsize=64)
    weights_queue = mp.Queue(maxsize=1)
    progress_queue = mp.Queue(maxsize=1)

    # -------------------------------------------------
    # 🔥 WORKERS
    # -------------------------------------------------
    workers = []
    for _ in range(NUM_ENVS):
        p = mp.Process(
            target=worker_loop,
            args=(
                rollout_queue,
                config_path,
                scenario,
                RL_SIDE,
                weights_queue,
                progress_queue
            )
        )
        p.daemon = True
        p.start()
        workers.append(p)

    rollout_idx = 0
    buffer = []

    # -------------------------------------------------
    # 🔥 TRAIN LOOP
    # -------------------------------------------------
    while rollout_idx < TOTAL_UPDATES:

        rollout = rollout_queue.get()
        buffer.append(rollout)

        if len(buffer) < BATCH_ROLLOUTS:
            continue

        # -------------------------------------------------
        # COMBINE
        # -------------------------------------------------
        combined = {
            "obs": [],
            "actions": [],
            "logp": [],
            "values": [],
            "rewards": [],
            "dones": []
        }

        for roll in buffer:
            for k in combined:
                combined[k].extend(roll[k])

        buffer = []

        # -------------------------------------------------
        # TENSORS
        # -------------------------------------------------
        obs_t = torch.from_numpy(np.array(combined["obs"])).float().to(DEVICE)
        act_t = torch.tensor(combined["actions"], dtype=torch.long).to(DEVICE)
        old_logp_t = torch.stack(combined["logp"]).to(DEVICE)

        value_buf = combined["values"]

        advantages = compute_gae(
            combined["rewards"],
            value_buf,
            combined["dones"],
            GAMMA,
            LAMBDA,
        )

        returns = [a + v for a, v in zip(advantages, value_buf)]

        advantages = torch.tensor(advantages, dtype=torch.float32).to(DEVICE)
        returns = torch.tensor(returns, dtype=torch.float32).to(DEVICE)

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

            clipped = torch.clamp(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS)

            policy_loss = -torch.min(
                ratio * advantages,
                clipped * advantages
            ).mean()

            value_loss = (returns - values.squeeze()).pow(2).mean()
            entropy = dist.entropy().mean()

            loss = (
                policy_loss +
                VALUE_COEF * value_loss -
                0.01 * entropy
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # -------------------------------------------------
        # 🔥 ENVIAR NUEVA POLICY
        # -------------------------------------------------
        safe_state = {
            k: v.detach().cpu().clone()
            for k, v in policy.state_dict().items()
        }

        if not weights_queue.full():
            weights_queue.put(safe_state)

        # 🔥 enviar progreso a reward
        if not progress_queue.full():
            progress_queue.put(rollout_idx)

        torch.cuda.empty_cache()

        # -------------------------------------------------
        # LOG
        # -------------------------------------------------
        if rollout_idx % 20 == 0:
            avg_reward = sum(combined["rewards"]) / len(combined["rewards"])
            print(f"[UPDATE {rollout_idx}] reward={avg_reward:.3f}")
            print(f"batch size: {len(combined['obs'])}")

        rollout_idx += 1


# -------------------------------------------------
# WINDOWS
# -------------------------------------------------
if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()