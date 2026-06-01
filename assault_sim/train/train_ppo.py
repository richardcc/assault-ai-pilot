import torch
import torch.optim as optim
import multiprocessing as mp
import numpy as np
import time
from datetime import datetime
import socket
from torch.utils.tensorboard import SummaryWriter
from pathlib import Path

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.engine.env_factory import make_env
from assault_sim.rewards.shaped_reward import ShapedReward

from assault_sim.train.worker import worker_loop
from assault_sim.train.ppo_schedule import ppo_schedule
from assault_sim.train.ppo_trainer import ppo_update, compute_gae


MODEL_DIR = Path("C:/repos/python/assault/models")
LATEST_PATH = MODEL_DIR / "latest.pt"


def main(reward_fn=None):

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f">>> Using device: {device}")

    config_path = Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
    scenario = "phase01_seq001_initial_contact"

    # reward shaping: allow injecting a custom reward_fn (used by grid runs)
    if reward_fn is None:
        reward_fn = ShapedReward(rl_side=PPOConfig.RL_SIDE)
    env = make_env(config_path, PPOConfig.RL_SIDE, scenario, reward_fn=reward_fn)
    obs = env.reset()
    input_dim = obs.shape[0]

    print(f">>> OBS DIM: {input_dim}")

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    ).to(device)

    # TensorBoard writer
    run_name = f"ppo_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}_{socket.gethostname()}"
    writer = SummaryWriter(log_dir=(MODEL_DIR / "runs" / run_name))

    optimizer = optim.Adam(policy.parameters(), lr=PPOConfig.LR)

    if LATEST_PATH.exists():
        try:
            print(f">>> Loading existing model: {LATEST_PATH}")
            policy.load_state_dict(torch.load(LATEST_PATH, map_location=device))
        except Exception as e:
            print(f"⚠️ Could not load model: {e}")
            print(">>> Starting from scratch")

    rollout_queue = mp.Queue(maxsize=32)
    weights_queue = mp.Queue(maxsize=1)

    workers = []
    for _ in range(PPOConfig.NUM_ENVS):
        p = mp.Process(
            target=worker_loop,
            args=(rollout_queue, config_path, scenario, weights_queue, None, reward_fn),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    rollout_idx = 0
    buffer = []

    start_time = time.time()
    last_log_time = start_time
    last_update = 0

    while rollout_idx < PPOConfig.TOTAL_UPDATES:

        rollout = rollout_queue.get()
        buffer.append(rollout)

        if len(buffer) < PPOConfig.BATCH_ROLLOUTS:
            continue

        # ---------------- MERGE ----------------

        combined = {k: [] for k in rollout.keys() if k != "reward_by_action"}
        reward_tracker = {}

        for r in buffer:

            for k in combined:
                combined[k].extend(r[k])

            for action, stats in r.get("reward_by_action", {}).items():
                if action not in reward_tracker:
                    reward_tracker[action] = {"sum": 0.0, "count": 0}

                reward_tracker[action]["sum"] += stats["sum"]
                reward_tracker[action]["count"] += stats["count"]

        buffer = []

        # ---------------- GAE ----------------

        advantages = compute_gae(
            combined["rewards"],
            combined["values"],
            combined["dones"],
            PPOConfig.GAMMA,
            PPOConfig.LAMBDA,
        )

        returns = [a + v for a, v in zip(advantages, combined["values"])]

        advantages = torch.tensor(advantages, dtype=torch.float32).to(device)
        returns = torch.tensor(returns, dtype=torch.float32).to(device)

        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # ---------------- TENSORS ----------------

        batch = {
            "obs": torch.tensor(np.array(combined["obs"]), dtype=torch.float32).to(device),
            "actions": torch.tensor(np.array(combined["actions"]), dtype=torch.long).to(device),
            "attack_modes": torch.tensor(np.array(combined["attack_modes"]), dtype=torch.long).to(device),
            "old_logp": torch.stack(combined["logp"]).to(device),
            "returns": returns,
            "advantages": advantages,
            "teacher": torch.tensor(np.array(combined["teacher_actions"]), dtype=torch.long).to(device),
        }

        schedule = ppo_schedule(rollout_idx)

        entropy_coef = PPOConfig.ENTROPY_COEF * (
            1.0 - rollout_idx / PPOConfig.TOTAL_UPDATES
        )
        entropy_coef = max(entropy_coef, 0.01)

        loss = ppo_update(
            policy,
            optimizer,
            batch,
            schedule,
            device,
            entropy_coef,
        )

        # ---------------- SYNC ----------------

        safe_state = {k: v.detach().cpu().clone() for k, v in policy.state_dict().items()}
        if not weights_queue.full():
            weights_queue.put(safe_state)

        # ---------------- SAVE ----------------

        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        if rollout_idx % 100 == 0:
            torch.save(policy.state_dict(), LATEST_PATH)
            print(f"✅ Saved latest → {LATEST_PATH}")

        if rollout_idx % 500 == 0:
            ckpt_path = MODEL_DIR / f"checkpoint_{rollout_idx}.pt"
            torch.save(policy.state_dict(), ckpt_path)
            print(f"📦 Saved checkpoint → {ckpt_path}")

        # ---------------- LOGGING ----------------

        if rollout_idx % 20 == 0:

            current_time = time.time()
            elapsed = current_time - last_log_time

            updates_done = rollout_idx - last_update
            throughput = updates_done / elapsed if elapsed > 0 else 0.0

            samples = (
                PPOConfig.NUM_ENVS *
                PPOConfig.ROLLOUT_STEPS *
                PPOConfig.BATCH_ROLLOUTS
            )
            samples_per_sec = samples / elapsed if elapsed > 0 else 0.0

            avg_reward = float(np.mean(combined['rewards']))
            print(f"[UPDATE {rollout_idx}] loss={loss:.3f}")
            print(f"avg_reward={avg_reward:.3f}")
            # TensorBoard scalars
            writer.add_scalar('train/loss', float(loss), rollout_idx)
            writer.add_scalar('train/avg_reward', avg_reward, rollout_idx)
            writer.add_scalar('train/entropy_coef', float(entropy_coef), rollout_idx)
            print(f"UPDATES/sec: {throughput:.2f}")
            print(f"SAMPLES/sec: {samples_per_sec:.0f}")

            # ✅ NUEVO
            print("REWARD BY ACTION:")
            for action, stats in reward_tracker.items():
                if stats["count"] > 0:
                    avg = stats["sum"] / stats["count"]
                    print(f"  {action}: avg={avg:.3f}")
                    writer.add_scalar(f'reward_by_action/{action}', float(avg), rollout_idx)

            last_log_time = current_time
            last_update = rollout_idx

            # ACTION USAGE
            actions = combined["actions"]
            unique, counts = np.unique(actions, return_counts=True)

            print("ACTION USAGE:")
            total = len(actions)

            for u, c in zip(unique, counts):
                try:
                    name = TacticalOption(u).name
                except:
                    name = str(u)
                print(f"  {name}: {c} ({100*c/total:.1f}%)")
                writer.add_scalar(f'action_usage/{name}', int(c), rollout_idx)

            # ATTACK MODES
            attack_modes = combined["attack_modes"]
            unique_a, counts_a = np.unique(attack_modes, return_counts=True)

            print("ATTACK MODES:")
            total_a = len(attack_modes)

            for u, c in zip(unique_a, counts_a):
                print(f"  mode {u}: {c} ({100*c/total_a:.1f}%)")
                writer.add_scalar(f'attack_modes/mode_{u}', int(c), rollout_idx)

            print("-" * 50)

        rollout_idx += 1

    # close writer
    writer.close()


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()