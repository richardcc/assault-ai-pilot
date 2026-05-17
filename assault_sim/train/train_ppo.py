import torch
import torch.optim as optim
import torch.distributions as torch_dist

import numpy as np
from pathlib import Path
import multiprocessing as mp

from assault_sim.config.ppo_config import PPOConfig

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.engine.env_factory import make_env
from assault_sim.engine.hrl_factory import create_hrl_controller
from assault_sim.engine.rollout import collect_rollout


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
# WORKER LOOP
# -------------------------------------------------
def worker_loop(
    rollout_queue,
    config_path,
    scenario,
    weights_queue,
    progress_queue
):
    torch.set_num_threads(1)
    torch.cuda.is_available = lambda: False

    env = make_env(config_path, PPOConfig.RL_SIDE, scenario)
    obs = env.reset()
    input_dim = obs.shape[0]

    policy_net = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    )
    policy_net.eval()

    policy = OptionPolicy(policy_net)
    controller = create_hrl_controller(policy, PPOConfig.RL_SIDE)

    reward_fn = env.reward_fn

    while True:

        # sync weights (safe)
        try:
            state_dict = weights_queue.get_nowait()
            policy_net.load_state_dict(state_dict)
        except:
            pass

        # sync training progress
        try:
            reward_fn.current_update = progress_queue.get_nowait()
        except:
            pass

        rollout = collect_rollout(env, controller, PPOConfig.ROLLOUT_STEPS)

        if "attack_modes" not in rollout:
            rollout["attack_modes"] = [0] * len(rollout["actions"])

        # 🔥 evita enviar LSTM hidden
        controller.policy.reset_hidden()

        try:
            rollout_queue.put(rollout, timeout=1)
        except:
            pass


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f">>> Using device: {DEVICE}")

    config_path = Path("assault_sim/config/sim_config.yaml")
    scenario = "phase01_seq001_initial_contact"

    env = make_env(config_path, PPOConfig.RL_SIDE, scenario)
    obs = env.reset()
    input_dim = obs.shape[0]

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    ).to(DEVICE)

    optimizer = optim.Adam(policy.parameters(), lr=PPOConfig.LR)

    rollout_queue = mp.Queue(maxsize=32)
    weights_queue = mp.Queue(maxsize=1)
    progress_queue = mp.Queue(maxsize=1)

    # -------------------------------------------------
    # WORKERS
    # -------------------------------------------------
    workers = []
    for _ in range(PPOConfig.NUM_ENVS):
        p = mp.Process(
            target=worker_loop,
            args=(
                rollout_queue,
                config_path,
                scenario,
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
    # TRAIN LOOP
    # -------------------------------------------------
    while rollout_idx < PPOConfig.TOTAL_UPDATES:

        rollout = rollout_queue.get()

        if "attack_modes" not in rollout:
            rollout["attack_modes"] = [0] * len(rollout["actions"])

        buffer.append(rollout)

        if len(buffer) < PPOConfig.BATCH_ROLLOUTS:
            continue

        combined = {k: [] for k in [
            "obs", "actions", "attack_modes", "logp",
            "values", "rewards", "dones"
        ]}

        for roll in buffer:
            for k in combined:
                combined[k].extend(roll[k])

        buffer = []

        # -------------------------------------------------
        # METRICS
        # -------------------------------------------------
        option_counts = {k.name: 0 for k in TacticalOption}
        total_actions = len(combined["actions"])

        for a in combined["actions"]:
            option_counts[TacticalOption(a).name] += 1

        # -------------------------------------------------
        # TENSORS (optimizado)
        # -------------------------------------------------

        # ✅ CORRECTO (rápido)
        obs_arr = np.array(combined["obs"], dtype=np.float32)
        obs_t = torch.from_numpy(obs_arr).to(DEVICE)

        # ✅ estos están bien (listas simples)
        act_t = torch.tensor(combined["actions"], dtype=torch.long).to(DEVICE)
        attack_mode_t = torch.tensor(combined["attack_modes"], dtype=torch.long).to(DEVICE)

        # ✅ ya es tensor → OK
        old_logp_t = torch.stack(combined["logp"]).to(DEVICE)

        value_buf = combined["values"]

        advantages = compute_gae(
            combined["rewards"],
            value_buf,
            combined["dones"],
            PPOConfig.GAMMA,
            PPOConfig.LAMBDA,
        )

        returns = [a + v for a, v in zip(advantages, value_buf)]

        advantages = torch.tensor(advantages, dtype=torch.float32).to(DEVICE)
        returns = torch.tensor(returns, dtype=torch.float32).to(DEVICE)

        if advantages.numel() > 1:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # -------------------------------------------------
        # PPO UPDATE
        # -------------------------------------------------
        for _ in range(PPOConfig.PPO_EPOCHS):

            hidden = policy.init_hidden(
                batch_size=obs_t.size(0),
                device=DEVICE
            )

            option_logits, attack_logits, values, _ = policy(obs_t, hidden)

            option_dist = torch_dist.Categorical(logits=option_logits)
            attack_dist = torch_dist.Categorical(logits=attack_logits)

            logp_option = option_dist.log_prob(act_t)
            logp_attack = attack_dist.log_prob(attack_mode_t)
            logp = logp_option + logp_attack

            ratio = torch.exp(torch.clamp(logp - old_logp_t, -10, 10))
            clipped = torch.clamp(ratio, 1 - PPOConfig.CLIP_EPS, 1 + PPOConfig.CLIP_EPS)

            policy_loss = -torch.min(
                ratio * advantages,
                clipped * advantages
            ).mean()

            value_loss = (returns - values.view(-1)).pow(2).mean()

            entropy = (
                option_dist.entropy().mean()
                + 0.5 * attack_dist.entropy().mean()
            )

            loss = (
                policy_loss
                + PPOConfig.VALUE_COEF * value_loss
                - PPOConfig.ENTROPY_COEF * entropy
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # -------------------------------------------------
        # SAVE
        # -------------------------------------------------
        if rollout_idx % 200 == 0:
            Path("models").mkdir(exist_ok=True)
            torch.save(policy.state_dict(), "models/latest.pt")

        # -------------------------------------------------
        # SYNC
        # -------------------------------------------------
        safe_state = {
            k: v.detach().cpu().clone()
            for k, v in policy.state_dict().items()
        }

        if not weights_queue.full():
            weights_queue.put(safe_state)

        if not progress_queue.full():
            progress_queue.put(rollout_idx)

        torch.cuda.empty_cache()

        # -------------------------------------------------
        # LOG
        # -------------------------------------------------
        if rollout_idx % 20 == 0:
            avg_reward = np.mean(combined["rewards"])
            avg_mode = np.mean(combined["attack_modes"])

            print(f"[UPDATE {rollout_idx}] reward={avg_reward:.3f}")
            print(f"batch size: {len(combined['obs'])}")
            print(f"attack_mode avg: {avg_mode:.2f}")

            print("ACTION USAGE:")
            for k, v in option_counts.items():
                pct = (v / total_actions) * 100 if total_actions > 0 else 0
                print(f"  {k}: {v} ({pct:.1f}%)")

            print("-" * 40)

        rollout_idx += 1


# -------------------------------------------------
if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
