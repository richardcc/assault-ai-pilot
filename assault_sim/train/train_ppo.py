import torch
import torch.optim as optim
import multiprocessing as mp
import numpy as np
from pathlib import Path

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.engine.env_factory import make_env

from assault_sim.train.worker import worker_loop
from assault_sim.train.ppo_schedule import ppo_schedule
from assault_sim.train.ppo_trainer import ppo_update, compute_gae


# =================================================
# ✅ CONFIG
# =================================================
MODEL_DIR = Path("C:/repos/python/assault/models")
LATEST_PATH = MODEL_DIR / "latest.pt"


def main():

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f">>> Using device: {device}")

    config_path = Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
    scenario = "phase01_seq001_initial_contact"

    env = make_env(config_path, PPOConfig.RL_SIDE, scenario)
    obs = env.reset()
    input_dim = obs.shape[0]

    print(f">>> OBS DIM: {input_dim}")

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    ).to(device)

    optimizer = optim.Adam(policy.parameters(), lr=PPOConfig.LR)

    # -------------------------------------------------
    # ✅ (OPCIONAL) LOAD EXISTING MODEL
    # -------------------------------------------------
    if LATEST_PATH.exists():
        try:
            print(f">>> Loading existing model: {LATEST_PATH}")
            policy.load_state_dict(torch.load(LATEST_PATH, map_location=device))
        except Exception as e:
            print(f"⚠️ Could not load model (dimension mismatch likely): {e}")
            print(">>> Starting from scratch")

    rollout_queue = mp.Queue(maxsize=32)
    weights_queue = mp.Queue(maxsize=1)

    # -------------------------------------------------
    # WORKERS
    # -------------------------------------------------
    workers = []

    for _ in range(PPOConfig.NUM_ENVS):
        p = mp.Process(
            target=worker_loop,
            args=(rollout_queue, config_path, scenario, weights_queue, None),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    rollout_idx = 0
    buffer = []

    # =================================================
    # TRAIN LOOP
    # =================================================
    while rollout_idx < PPOConfig.TOTAL_UPDATES:

        rollout = rollout_queue.get()
        buffer.append(rollout)

        if len(buffer) < PPOConfig.BATCH_ROLLOUTS:
            continue

        # -------------------------------------------------
        # MERGE ROLLOUTS
        # -------------------------------------------------
        combined = {k: [] for k in rollout.keys()}

        for r in buffer:
            for k in combined:
                combined[k].extend(r[k])

        buffer = []

        # -------------------------------------------------
        # GAE
        # -------------------------------------------------
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

        # -------------------------------------------------
        # TENSORS
        # -------------------------------------------------
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

        # ✅ ENTROPY DECAY (AQUÍ)
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
            entropy_coef,   # ✅ nuevo parámetro
)

        # -------------------------------------------------
        # ✅ SYNC WEIGHTS (workers)
        # -------------------------------------------------
        safe_state = {k: v.detach().cpu().clone() for k, v in policy.state_dict().items()}

        if not weights_queue.full():
            weights_queue.put(safe_state)

        # =================================================
        # ✅ 💾 SAVE MODEL (CLAVE)
        # =================================================
        MODEL_DIR.mkdir(parents=True, exist_ok=True)

        # ✅ guardar último modelo (frecuente)
        if rollout_idx % 100 == 0:
            torch.save(policy.state_dict(), LATEST_PATH)
            print(f"✅ Saved latest → {LATEST_PATH}")

        # ✅ checkpoints históricos
        if rollout_idx % 500 == 0:
            ckpt_path = MODEL_DIR / f"checkpoint_{rollout_idx}.pt"
            torch.save(policy.state_dict(), ckpt_path)
            print(f"📦 Saved checkpoint → {ckpt_path}")

        # =================================================
        # ✅ LOGGING
        # =================================================
        if rollout_idx % 20 == 0:

            print(f"[UPDATE {rollout_idx}] loss={loss:.3f}")
            print(f"avg_reward={np.mean(combined['rewards']):.3f}")

            # -------------------------
            # ACTION USAGE
            # -------------------------
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

            # -------------------------
            # ATTACK MODES
            # -------------------------
            attack_modes = combined["attack_modes"]
            unique_a, counts_a = np.unique(attack_modes, return_counts=True)

            print("ATTACK MODES:")
            total_a = len(attack_modes)

            for u, c in zip(unique_a, counts_a):
                print(f"  mode {u}: {c} ({100*c/total_a:.1f}%)")

            print("-" * 50)

        rollout_idx += 1


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()