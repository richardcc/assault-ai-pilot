from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import torch

from assault_sim.config.train_config import load_train_config
from assault_sim.envs.gym_assault_env import GymAssaultEnv


def _scenario_sides(repo_root: Path, scenario_id: str) -> set[str]:
    scenario_path = repo_root / "assault_sim" / "assets" / "scenarios" / f"{scenario_id}.json"
    if not scenario_path.exists():
        return set()
    try:
        with open(scenario_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return set()
    units = payload.get("units", [])
    return {
        str(u.get("side", "")).upper()
        for u in units
        if isinstance(u, dict) and u.get("side")
    }


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

    def make_env_for_scenario(scenario_id: str, rl_side: str):
        env = GymAssaultEnv(
            scenario=scenario_id,
            rl_side=rl_side,
            seed=cfg.seed,
            max_decisions=cfg.sb3_max_decisions,
            zero_damage_penalty=cfg.sb3_zero_damage_penalty,
            extra_good_trade_bonus=cfg.sb3_extra_good_trade_bonus,
        )
        return Monitor(env)

    num_envs = cfg.sb3_num_envs

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    tb_log = repo_root / "models" / "runs" / f"sb3_{run_id}"
    trained_any = False
    for rl_side in cfg.rl_sides:
        model = None
        train_env = None
        total_timesteps = 0
        final_scenario = None
        print(f"=== TRAIN SIDE {rl_side} ===")

        for phase_idx, phase in enumerate(cfg.scenario_schedule, start=1):
            scenario_id = phase.id
            phase_timesteps = int(phase.episodes * cfg.sb3_max_decisions)
            if phase_timesteps <= 0:
                continue
            sides_in_scenario = _scenario_sides(repo_root, scenario_id)
            if rl_side not in sides_in_scenario:
                print(
                    f"⚠️ SKIP PHASE side={rl_side} scenario={scenario_id}: "
                    f"side not present in scenario units (found={sorted(sides_in_scenario)})"
                )
                continue

            print(
                f"=== TRAIN PHASE {phase_idx}/{len(cfg.scenario_schedule)} "
                f"side={rl_side} scenario={scenario_id} episodes={phase.episodes} "
                f"timesteps={phase_timesteps} ==="
            )

            train_env = DummyVecEnv(
                [lambda sid=scenario_id, side=rl_side: make_env_for_scenario(sid, side) for _ in range(num_envs)]
            )
            train_env = VecNormalize(
                train_env,
                norm_obs=True,
                norm_reward=True,
                clip_obs=10.0,
            )
            eval_env = DummyVecEnv(
                [lambda sid=scenario_id, side=rl_side: make_env_for_scenario(sid, side)]
            )
            eval_env = VecNormalize(
                eval_env,
                training=False,
                norm_obs=True,
                norm_reward=False,
            )

            if model is None:
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
            else:
                model.set_env(train_env)

            eval_cb = EvalCallback(
                eval_env,
                best_model_save_path=str(model_dir / f"sb3_best_{rl_side}"),
                log_path=str(model_dir / f"sb3_eval_{rl_side}"),
                eval_freq=cfg.sb3_eval_freq,
                deterministic=True,
                render=False,
                n_eval_episodes=cfg.sb3_eval_episodes,
            )

            model.learn(total_timesteps=phase_timesteps, callback=eval_cb)
            total_timesteps += phase_timesteps
            final_scenario = scenario_id

        if model is None or train_env is None:
            continue
        trained_any = True

        out_path = model_dir / f"sb3_latest_{rl_side}.zip"
        model.save(str(out_path))
        vecnorm_path = model_dir / f"sb3_vecnormalize_{rl_side}.pkl"
        train_env.save(str(vecnorm_path))

        # Keep compatibility symlink/copy-style latest aliases for first side.
        if rl_side == cfg.rl_sides[0]:
            model.save(str(model_dir / "sb3_latest.zip"))
            train_env.save(str(model_dir / "sb3_vecnormalize.pkl"))

        meta = {
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "algorithm": "SB3_PPO",
            "total_timesteps": total_timesteps,
            "seed": cfg.seed,
            "scenario": final_scenario,
            "scenario_schedule": [
                {"id": p.id, "episodes": p.episodes}
                for p in cfg.scenario_schedule
            ],
            "rl_side": rl_side,
            "rl_sides": list(cfg.rl_sides),
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
        with open(model_dir / f"sb3_latest_{rl_side}.meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        if rl_side == cfg.rl_sides[0]:
            with open(model_dir / "sb3_latest.meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

        print(f"SB3 training complete for {rl_side} -> {out_path}")

    if not trained_any:
        raise SystemExit("No training phases executed; check scenario_schedule/rl_sides in train_config.json.")


if __name__ == "__main__":
    main()

