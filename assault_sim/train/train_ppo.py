import torch
import torch.optim as optim
import multiprocessing as mp
import numpy as np
import time
import random
import os
from datetime import datetime
import socket
from torch.utils.tensorboard import SummaryWriter
from pathlib import Path

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.config.train_config import load_train_config
from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.engine.env_factory import make_env
from assault_sim.rewards.shaped_reward import ShapedReward

from assault_sim.train.worker import worker_loop
from assault_sim.train.ppo_schedule import ppo_schedule
from assault_sim.train.ppo_trainer import ppo_update, compute_gae
from assault_sim.train.checkpointing import (
    build_checkpoint_payload,
    load_model_state,
    save_latest,
    save_numbered,
)
from assault_sim.train.eval_gate import composite_eval_score, should_promote_best
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.decision.decision_engine_controller import DecisionEngineController
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.evaluation.evaluator import Evaluator


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = REPO_ROOT / "models"
LATEST_PATH = MODEL_DIR / "latest.pt"
SIM_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "sim_config.yaml"
ENV_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "env_config.json"
TRAIN_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "train_config.json"


def set_global_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def evaluate_policy_snapshot(policy: PolicyNet, cfg, reward_fn=None):
    eval_env = make_env(
        config_path=SIM_CONFIG_PATH,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=cfg.rl_side,
        scenario=cfg.scenario,
        reward_fn=reward_fn,
        seed=cfg.seed,
    )
    controller = DecisionEngineController(
        rl_side=cfg.rl_side,
        decision_engine=DecisionEngine(),
        option_policy=OptionPolicy(policy),
        heuristic=TacticalPathHeuristic(),
        sim_env=eval_env.sim,
    )
    controller.training_mode = False
    evaluator = Evaluator(
        env=eval_env,
        rl_controller=controller,
        enemy_controller=None,
        rl_side=cfg.rl_side,
    )
    results = evaluator.evaluate(cfg.eval_episodes)
    if not results:
        return {"win_rate": 0.0, "damage_ratio": 0.0, "episodes": 0}
    wins = 0.0
    rl_damage = 0.0
    enemy_damage = 0.0
    for r in results:
        winner = r.get("winner")
        if winner == cfg.rl_side:
            wins += 1.0
        elif winner is None:
            wins += 0.5
        rl_damage += r.get("side", {}).get("RL", {}).get("damage", 0)
        enemy_damage += r.get("side", {}).get("ENEMY", {}).get("damage", 0)
    return {
        "win_rate": float(wins / len(results)),
        "damage_ratio": float(rl_damage / max(1.0, enemy_damage)),
        "episodes": len(results),
    }


def main(reward_fn=None):
    cfg = load_train_config(TRAIN_CONFIG_PATH)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_global_seed(cfg.seed)
    print(f">>> Using device: {device}")

    scenario = cfg.scenario
    print(">>> Effective train config:")
    print(f"    seed={cfg.seed} scenario={scenario} rl_side={cfg.rl_side}")
    print(f"    train_config={TRAIN_CONFIG_PATH}")
    print(f"    sim_config={SIM_CONFIG_PATH}")
    print(f"    env_config={ENV_CONFIG_PATH}")
    print(f"    model_dir={MODEL_DIR}")

    # reward shaping: allow injecting a custom reward_fn (used by grid runs)
    if reward_fn is None:
        reward_fn = ShapedReward(rl_side=cfg.rl_side)
    env = make_env(
        config_path=SIM_CONFIG_PATH,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=cfg.rl_side,
        scenario=scenario,
        reward_fn=reward_fn,
        seed=cfg.seed,
    )
    print(f"    max_steps={env.max_steps}")
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

    optimizer = optim.Adam(policy.parameters(), lr=cfg.lr)

    if LATEST_PATH.exists():
        try:
            print(f">>> Loading existing model: {LATEST_PATH}")
            state_dict, _ = load_model_state(LATEST_PATH, device)
            policy.load_state_dict(state_dict)
        except Exception as e:
            print(f"⚠️ Could not load model: {e}")
            print(">>> Starting from scratch")

    rollout_queue = mp.Queue(maxsize=32)
    weights_queue = mp.Queue(maxsize=1)

    workers = []
    for worker_id in range(cfg.num_envs):
        p = mp.Process(
            target=worker_loop,
            args=(
                rollout_queue,
                SIM_CONFIG_PATH,
                ENV_CONFIG_PATH,
                scenario,
                weights_queue,
                None,
                reward_fn,
                cfg.seed,
                worker_id,
                cfg.rl_side,
                cfg.rollout_steps,
            ),
        )
        p.daemon = True
        p.start()
        workers.append(p)

    rollout_idx = 0
    buffer = []

    start_time = time.time()
    last_log_time = start_time
    last_update = 0
    best_eval_score = -1e9

    while rollout_idx < cfg.total_updates:

        rollout = rollout_queue.get()
        buffer.append(rollout)

        if len(buffer) < cfg.batch_rollouts:
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
            "dones": torch.tensor(np.array(combined["dones"]), dtype=torch.float32).to(device),
        }

        schedule = ppo_schedule(rollout_idx)

        entropy_coef = PPOConfig.ENTROPY_COEF * (
            1.0 - rollout_idx / cfg.total_updates
        )
        entropy_coef = max(entropy_coef, 0.01)

        train_stats = ppo_update(
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
        checkpoint_payload = build_checkpoint_payload(
            policy=policy,
            optimizer=optimizer,
            rollout_idx=rollout_idx,
            seed=cfg.seed,
            scenario=scenario,
            rl_side=cfg.rl_side,
            hostname=socket.gethostname(),
            sim_config_path=SIM_CONFIG_PATH,
            env_config_path=ENV_CONFIG_PATH,
            ppo_config={
                k: v
                for k, v in PPOConfig.__dict__.items()
                if k.isupper() and isinstance(v, (int, float, str, bool))
            },
            train_stats=train_stats,
        )

        if rollout_idx % 100 == 0:
            latest_path = save_latest(checkpoint_payload, MODEL_DIR, latest_name="latest.pt")
            print(f"✅ Saved latest → {latest_path}")

        if rollout_idx % 500 == 0:
            ckpt_path = save_numbered(checkpoint_payload, MODEL_DIR, rollout_idx)
            print(f"📦 Saved checkpoint → {ckpt_path}")

        if rollout_idx > 0 and rollout_idx % cfg.eval_interval == 0:
            eval_stats = evaluate_policy_snapshot(policy, cfg, reward_fn=reward_fn)
            eval_score = composite_eval_score(eval_stats, damage_weight=0.25)
            writer.add_scalar("eval/win_rate", eval_stats["win_rate"], rollout_idx)
            writer.add_scalar("eval/damage_ratio", eval_stats["damage_ratio"], rollout_idx)
            writer.add_scalar("eval/score", eval_score, rollout_idx)
            print(f"EVAL win_rate={eval_stats['win_rate']:.3f} damage_ratio={eval_stats['damage_ratio']:.3f} score={eval_score:.3f}")
            if should_promote_best(
                score=eval_score,
                best_score=best_eval_score,
                min_improvement=cfg.eval_min_improvement,
            ):
                best_eval_score = eval_score
                best_path = MODEL_DIR / "best.pt"
                torch.save(checkpoint_payload, best_path)
                print(f"🏆 Promoted best checkpoint → {best_path}")

        # ---------------- LOGGING ----------------

        if rollout_idx % 20 == 0:

            current_time = time.time()
            elapsed = current_time - last_log_time

            updates_done = rollout_idx - last_update
            throughput = updates_done / elapsed if elapsed > 0 else 0.0

            samples = (
                cfg.num_envs *
                cfg.rollout_steps *
                cfg.batch_rollouts
            )
            samples_per_sec = samples / elapsed if elapsed > 0 else 0.0

            avg_reward = float(np.mean(combined['rewards']))
            print(f"[UPDATE {rollout_idx}] loss={train_stats['loss']:.3f}")
            print(f"avg_reward={avg_reward:.3f}")
            # TensorBoard scalars
            writer.add_scalar('train/loss', float(train_stats["loss"]), rollout_idx)
            writer.add_scalar('train/policy_loss', float(train_stats["policy_loss"]), rollout_idx)
            writer.add_scalar('train/value_loss', float(train_stats["value_loss"]), rollout_idx)
            writer.add_scalar('train/entropy', float(train_stats["entropy"]), rollout_idx)
            writer.add_scalar('train/approx_kl', float(train_stats["approx_kl"]), rollout_idx)
            writer.add_scalar('train/clip_fraction', float(train_stats["clip_fraction"]), rollout_idx)
            writer.add_scalar('train/imitation_loss', float(train_stats["imitation_loss"]), rollout_idx)
            writer.add_scalar('train/grad_norm', float(train_stats["grad_norm"]), rollout_idx)
            writer.add_scalar('train/samples_used', int(train_stats["samples_used"]), rollout_idx)
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

            if "l2_sampled" in combined and len(combined["l2_sampled"]) == len(combined["l2"]):
                forced = sum(
                    1 for s, e in zip(combined["l2_sampled"], combined["l2"])
                    if s != e
                )
                forced_ratio = forced / max(1, len(combined["l2"]))
                writer.add_scalar("policy/forced_option_ratio", float(forced_ratio), rollout_idx)
                print(f"forced_option_ratio={forced_ratio:.3f}")

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
    if os.environ.get("ASSAULT_ALLOW_CUSTOM_PPO", "0") != "1":
        raise SystemExit(
            "train_ppo.py is disabled (project is SB3-only). "
            "Use: python -m assault_sim.train.train_sb3\n"
            "If you really need legacy custom PPO, run with ASSAULT_ALLOW_CUSTOM_PPO=1."
        )
    mp.set_start_method("spawn", force=True)
    main()