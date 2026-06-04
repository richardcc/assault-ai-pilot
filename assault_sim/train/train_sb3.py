from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import torch

from assault_sim.config.train_config import load_train_config
from assault_sim.envs.gym_assault_env import GymAssaultEnv


def main():
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import EvalCallback
        from stable_baselines3.common.vec_env import DummyVecEnv
        from stable_baselines3.common.monitor import Monitor
        from stable_baselines3.common.vec_env import VecNormalize
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "stable-baselines3 is not installed. Install with: pip install stable-baselines3 gymnasium"
        ) from exc

    repo_root = Path(__file__).resolve().parents[2]
    model_dir = repo_root / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    train_config_path = repo_root / "assault_sim" / "config" / "train_config.json"
    cfg = load_train_config(train_config_path)
    requested_device = cfg.sb3_device.strip().lower()
    if requested_device == "cuda" and not torch.cuda.is_available():
        print("⚠️ sb3_device='cuda' but CUDA is not available. Falling back to CPU.")
        effective_device = "cpu"
    else:
        effective_device = requested_device

    def make_env():
        env = GymAssaultEnv(
            scenario=cfg.scenario,
            rl_side=cfg.rl_side,
            seed=cfg.seed,
            max_decisions=cfg.sb3_max_decisions,
            zero_damage_penalty=cfg.sb3_zero_damage_penalty,
            extra_good_trade_bonus=cfg.sb3_extra_good_trade_bonus,
        )
        return Monitor(env)

    num_envs = cfg.sb3_num_envs
    train_env = DummyVecEnv([make_env for _ in range(num_envs)])
    train_env = VecNormalize(
        train_env,
        norm_obs=True,
        norm_reward=True,
        clip_obs=10.0,
    )
    eval_env = DummyVecEnv([make_env])
    eval_env = VecNormalize(
        eval_env,
        training=False,
        norm_obs=True,
        norm_reward=False,
    )

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    tb_log = repo_root / "models" / "runs" / f"sb3_{run_id}"

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        n_steps=cfg.sb3_n_steps,
        batch_size=cfg.sb3_batch_size,
        n_epochs=cfg.sb3_n_epochs,
        gamma=cfg.sb3_gamma,
        gae_lambda=cfg.sb3_gae_lambda,
        ent_coef=cfg.sb3_ent_coef,
        clip_range=cfg.sb3_clip_range,
        learning_rate=cfg.sb3_learning_rate,
        policy_kwargs={"net_arch": list(cfg.sb3_net_arch)},
        tensorboard_log=str(tb_log),
        seed=cfg.seed,
        device=effective_device,
    )

    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(model_dir / "sb3_best"),
        log_path=str(model_dir / "sb3_eval"),
        eval_freq=cfg.sb3_eval_freq,
        deterministic=True,
        render=False,
        n_eval_episodes=cfg.sb3_eval_episodes,
    )

    total_timesteps = cfg.sb3_total_timesteps
    model.learn(total_timesteps=total_timesteps, callback=eval_cb)
    out_path = model_dir / "sb3_latest.zip"
    model.save(str(out_path))
    vecnorm_path = model_dir / "sb3_vecnormalize.pkl"
    train_env.save(str(vecnorm_path))

    meta = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "algorithm": "SB3_PPO",
        "total_timesteps": total_timesteps,
        "seed": cfg.seed,
        "scenario": cfg.scenario,
        "rl_side": cfg.rl_side,
        "train_config_path": str(train_config_path),
        "model_path": str(out_path),
        "vecnormalize_path": str(vecnorm_path),
        "num_envs": num_envs,
        "n_steps": cfg.sb3_n_steps,
        "batch_size": cfg.sb3_batch_size,
        "n_epochs": cfg.sb3_n_epochs,
        "gamma": cfg.sb3_gamma,
        "gae_lambda": cfg.sb3_gae_lambda,
        "ent_coef": cfg.sb3_ent_coef,
        "clip_range": cfg.sb3_clip_range,
        "device": effective_device,
        "net_arch": list(cfg.sb3_net_arch),
        "max_decisions": cfg.sb3_max_decisions,
        "zero_damage_penalty": cfg.sb3_zero_damage_penalty,
        "extra_good_trade_bonus": cfg.sb3_extra_good_trade_bonus,
    }
    with open(model_dir / "sb3_latest.meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"SB3 training complete -> {out_path}")


if __name__ == "__main__":
    main()

