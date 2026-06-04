from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json

from assault_sim.config.ppo_config import PPOConfig
from assault_sim.envs.gym_assault_env import GymAssaultEnv


def main():
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import EvalCallback
        from stable_baselines3.common.vec_env import DummyVecEnv
        from stable_baselines3.common.monitor import Monitor
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "stable-baselines3 is not installed. Install with: pip install stable-baselines3 gymnasium"
        ) from exc

    repo_root = Path(__file__).resolve().parents[2]
    model_dir = repo_root / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    def make_env():
        env = GymAssaultEnv(
            scenario=PPOConfig.SCENARIO,
            rl_side=PPOConfig.RL_SIDE,
            seed=PPOConfig.SEED,
        )
        return Monitor(env)

    train_env = DummyVecEnv([make_env for _ in range(6)])
    eval_env = DummyVecEnv([make_env])

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    tb_log = repo_root / "models" / "runs" / f"sb3_{run_id}"

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        n_steps=1024,
        batch_size=512,
        learning_rate=2.5e-4,
        tensorboard_log=str(tb_log),
        seed=PPOConfig.SEED,
        device="cpu",
    )

    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(model_dir / "sb3_best"),
        log_path=str(model_dir / "sb3_eval"),
        eval_freq=10_000,
        deterministic=True,
        render=False,
        n_eval_episodes=5,
    )

    total_timesteps = 300_000
    model.learn(total_timesteps=total_timesteps, callback=eval_cb)
    out_path = model_dir / "sb3_latest.zip"
    model.save(str(out_path))

    meta = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "algorithm": "SB3_PPO",
        "total_timesteps": total_timesteps,
        "seed": PPOConfig.SEED,
        "scenario": PPOConfig.SCENARIO,
        "rl_side": PPOConfig.RL_SIDE,
        "model_path": str(out_path),
    }
    with open(model_dir / "sb3_latest.meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"SB3 training complete -> {out_path}")


if __name__ == "__main__":
    main()

