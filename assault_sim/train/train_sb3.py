from __future__ import annotations

import argparse
import cProfile
import os
from pathlib import Path
from datetime import datetime
import shutil
import json
import pstats
import io
import torch

from assault_sim.config.train_config import load_train_config
from assault_sim.envs.gym_assault_env import GymAssaultEnv


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _configure_torch_threads_for_cpu() -> tuple[int, int]:
    # Prefer explicit env overrides, otherwise use a high-utilization default.
    cpu_total = int(os.cpu_count() or 8)
    default_threads = max(1, min(20, cpu_total))
    default_interop = max(1, min(8, max(2, cpu_total // 3)))
    num_threads = max(1, _env_int("ASSAULT_TORCH_NUM_THREADS", default_threads))
    interop_threads = max(1, _env_int("ASSAULT_TORCH_INTEROP_THREADS", default_interop))

    try:
        torch.set_num_threads(num_threads)
    except Exception as exc:
        print(f"[WARN] torch.set_num_threads({num_threads}) failed: {exc}")
    try:
        torch.set_num_interop_threads(interop_threads)
    except Exception as exc:
        print(f"[WARN] torch.set_num_interop_threads({interop_threads}) failed: {exc}")

    actual_num_threads = int(torch.get_num_threads())
    try:
        actual_interop = int(torch.get_num_interop_threads())
    except Exception:
        actual_interop = interop_threads
    return actual_num_threads, actual_interop


def _make_env_factory(
    scenario_id: str,
    rl_side: str,
    seed: int,
    max_decisions: int,
    zero_damage_penalty: float,
    extra_good_trade_bonus: float,
    train_lean: bool,
):
    def _init():
        from stable_baselines3.common.monitor import Monitor

        env = GymAssaultEnv(
            scenario=scenario_id,
            rl_side=rl_side,
            seed=seed,
            max_decisions=max_decisions,
            zero_damage_penalty=zero_damage_penalty,
            extra_good_trade_bonus=extra_good_trade_bonus,
            train_lean=train_lean,
        )
        return Monitor(env)

    return _init


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


def _cleanup_model_workspace(model_dir: Path, rl_sides: tuple[str, ...]) -> None:
    """Remove prior artifacts only for requested RL sides."""
    side_keys = tuple(str(s).upper() for s in (rl_sides or ()))
    file_patterns = tuple(
        p
        for side in side_keys
        for p in (
            f"sb3_latest_{side}.zip",
            f"sb3_vecnormalize_{side}.pkl",
            f"sb3_latest_{side}.meta.json",
        )
    )
    dir_patterns = tuple(
        p
        for side in side_keys
        for p in (
            f"sb3_best_{side}",
            f"sb3_eval_{side}",
        )
    )
    removed_files = 0
    removed_dirs = 0
    for pattern in file_patterns:
        for path in model_dir.glob(pattern):
            if path.is_file():
                path.unlink(missing_ok=True)
                removed_files += 1
    for pattern in dir_patterns:
        for path in model_dir.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed_dirs += 1
    print(
        f"[cleanup] model workspace cleaned: files={removed_files} dirs={removed_dirs} under {model_dir}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Train SB3 PPO for configured sides/scenarios."
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to train_config.json (defaults to assault_sim/config/train_config.json)",
    )
    args = parser.parse_args()

    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import EvalCallback, BaseCallback
        from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
        from stable_baselines3.common.vec_env import VecNormalize
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "stable-baselines3 is not installed. Install with: pip install stable-baselines3 gymnasium"
        ) from exc

    repo_root = Path(__file__).resolve().parents[2]
    train_config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else (repo_root / "assault_sim" / "config" / "train_config.json")
    )
    cfg = load_train_config(train_config_path)
    os.environ["ASSAULT_P4_ADVANCED_PLANNER"] = "1" if bool(getattr(cfg, "p4_advanced_planner_enabled", False)) else "0"
    os.environ["ASSAULT_P4_ADVANCED_HORIZON"] = str(int(getattr(cfg, "p4_advanced_planner_horizon", 2) or 2))
    models_root = repo_root / "models"
    requested_device = cfg.sb3_device.strip().lower()
    if requested_device == "cuda" and not torch.cuda.is_available():
        print("[WARN] sb3_device='cuda' but CUDA is not available. Falling back to CPU.")
        effective_device = "cpu"
    else:
        effective_device = requested_device
    if effective_device == "cpu":
        t_num, t_interop = _configure_torch_threads_for_cpu()
        print(
            "[perf] torch thread config:"
            f" num_threads={t_num}"
            f" interop_threads={t_interop}"
            f" cpu_count={os.cpu_count() or 'n/a'}"
        )

    class PeriodicArtifactCallback(BaseCallback):
        """Periodic saver for model + VecNormalize stats."""

        def __init__(self, save_freq: int, model_path: Path, vecnorm_path: Path):
            super().__init__(verbose=0)
            self.save_freq = max(1, int(save_freq))
            self.model_path = model_path
            self.vecnorm_path = vecnorm_path
            self._last_save_step = 0

        def _on_step(self) -> bool:
            try:
                cur_steps = int(getattr(self.model, "num_timesteps", 0))
                if cur_steps - self._last_save_step >= self.save_freq:
                    self.model.save(str(self.model_path))
                    vec = self.model.get_vec_normalize_env()
                    if vec is not None:
                        vec.save(str(self.vecnorm_path))
                    self._last_save_step = cur_steps
            except Exception as exc:
                print(f"[WARN] periodic artifact save failed: {exc}")
            return True

    num_envs = cfg.sb3_num_envs
    vec_env_type = str(getattr(cfg, "sb3_vec_env_type", "dummy")).strip().lower()

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    trained_any = False
    for rl_side in cfg.rl_sides:
        side_scenario = str(cfg.scenario or "").strip()
        models_subdir = cfg.resolve_models_subdir(
            scenario_id=side_scenario,
            side=rl_side,
        )
        model_dir = (models_root / models_subdir) if models_subdir else models_root
        model_dir.mkdir(parents=True, exist_ok=True)
        if bool(getattr(cfg, "sb3_clean_models_before_train", True)):
            _cleanup_model_workspace(model_dir, (rl_side,))
        else:
            print(
                f"[INFO] model workspace cleanup skipped for side={rl_side} "
                "(sb3_clean_models_before_train=false)."
            )
        tb_log = model_dir / "runs" / f"sb3_{run_id}"
        model = None
        train_env = None
        total_timesteps = 0
        final_scenario = None
        out_path = model_dir / f"sb3_latest_{rl_side}.zip"
        vecnorm_path = model_dir / f"sb3_vecnormalize_{rl_side}.pkl"
        print(f"=== TRAIN SIDE {rl_side} (models_subdir='{models_subdir or '.'}') ===")

        for phase_idx, phase in enumerate(cfg.scenario_schedule, start=1):
            scenario_id = phase.id
            phase_timesteps = int(phase.episodes * cfg.sb3_max_decisions)
            if phase_timesteps <= 0:
                continue
            curriculum_enabled = bool(getattr(cfg, "sb3_enable_curriculum", True))
            total_phases = len(cfg.scenario_schedule)
            warmup_capture_phase = curriculum_enabled and total_phases > 1 and phase_idx == 1
            mixed_capture_phase = curriculum_enabled and total_phases > 2 and phase_idx < total_phases and phase_idx > 1
            if warmup_capture_phase:
                curriculum_stage = "SIMPLE"
            elif mixed_capture_phase:
                curriculum_stage = "MIXED"
            else:
                curriculum_stage = "FULL"
            phase_force_capture = True if warmup_capture_phase else bool(getattr(cfg, "diagnostic_force_capture_only", False))
            os.environ["ASSAULT_CAPTURE_GUARDRAILS_ENABLED"] = (
                "1" if bool(getattr(cfg, "capture_guardrails_enabled", True)) else "0"
            )
            os.environ["ASSAULT_DIAGNOSTIC_FORCE_CAPTURE_ONLY"] = (
                "1" if phase_force_capture else "0"
            )
            os.environ["ASSAULT_CURRICULUM_STAGE"] = str(curriculum_stage)
            os.environ["ASSAULT_FINALIZER_OVERRIDE_PROFILE"] = str(
                getattr(cfg, "finalizer_override_profile", "strict") or "strict"
            ).strip().lower()
            sides_in_scenario = _scenario_sides(repo_root, scenario_id)
            if rl_side not in sides_in_scenario:
                print(
                    f"[WARN] SKIP PHASE side={rl_side} scenario={scenario_id}: "
                    f"side not present in scenario units (found={sorted(sides_in_scenario)})"
                )
                continue

            print(
                f"=== TRAIN PHASE {phase_idx}/{len(cfg.scenario_schedule)} "
                f"side={rl_side} scenario={scenario_id} episodes={phase.episodes} "
                f"timesteps={phase_timesteps} curriculum_stage={curriculum_stage} ==="
            )
            if warmup_capture_phase:
                print("Curriculum warmup: forcing CAPTURE intent for phase 1.")

            train_fns = [
                _make_env_factory(
                    scenario_id=scenario_id,
                    rl_side=rl_side,
                    # Keep worker seeds aligned with previous behavior to avoid
                    # introducing an unintended exploration distribution shift.
                    seed=cfg.seed,
                    max_decisions=cfg.sb3_max_decisions,
                    zero_damage_penalty=cfg.sb3_zero_damage_penalty,
                    extra_good_trade_bonus=cfg.sb3_extra_good_trade_bonus,
                    train_lean=bool(getattr(cfg, "sb3_train_lean", True)),
                )
                for _env_idx in range(num_envs)
            ]
            if vec_env_type == "subproc" and num_envs > 1:
                try:
                    train_vec = SubprocVecEnv(train_fns, start_method="spawn")
                    print(f"Using SubprocVecEnv with num_envs={num_envs}")
                except Exception as exc:
                    print(f"[WARN] SubprocVecEnv unavailable ({exc}); falling back to DummyVecEnv.")
                    train_vec = DummyVecEnv(train_fns)
            else:
                train_vec = DummyVecEnv(train_fns)
                print(f"Using DummyVecEnv with num_envs={num_envs}")

            train_env = train_vec
            train_env = VecNormalize(
                train_env,
                norm_obs=True,
                norm_reward=True,
                clip_obs=10.0,
            )
            eval_env = DummyVecEnv(
                [
                    _make_env_factory(
                        scenario_id=scenario_id,
                        rl_side=rl_side,
                        seed=cfg.seed,
                        max_decisions=cfg.sb3_max_decisions,
                        zero_damage_penalty=cfg.sb3_zero_damage_penalty,
                        extra_good_trade_bonus=cfg.sb3_extra_good_trade_bonus,
                        train_lean=False,
                    )
                ]
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

            periodic_cb = PeriodicArtifactCallback(
                save_freq=cfg.sb3_eval_freq,
                model_path=out_path,
                vecnorm_path=vecnorm_path,
            )
            if bool(getattr(cfg, "sb3_profile_train", False)):
                profiler = cProfile.Profile()
                profiler.enable()
                model.learn(total_timesteps=phase_timesteps, callback=[eval_cb, periodic_cb])
                profiler.disable()
                profile_base = model_dir / (
                    f"sb3_profile_{rl_side}_{scenario_id}_phase{phase_idx}_{run_id}"
                )
                profiler.dump_stats(str(profile_base.with_suffix(".prof")))
                s = io.StringIO()
                stats = pstats.Stats(profiler, stream=s).sort_stats(
                    str(getattr(cfg, "sb3_profile_sort", "cumulative") or "cumulative")
                )
                stats.print_stats(int(getattr(cfg, "sb3_profile_top_n", 40) or 40))
                profile_base.with_suffix(".txt").write_text(s.getvalue(), encoding="utf-8")
                print(f"[PROFILE] Saved cProfile stats -> {profile_base.with_suffix('.prof')}")
                print(f"[PROFILE] Saved cProfile summary -> {profile_base.with_suffix('.txt')}")
            else:
                model.learn(total_timesteps=phase_timesteps, callback=[eval_cb, periodic_cb])
            total_timesteps += phase_timesteps
            final_scenario = scenario_id

        if model is None or train_env is None:
            continue
        trained_any = True

        # Final save (periodic saves already created interim artifacts).
        model.save(str(out_path))
        train_env.save(str(vecnorm_path))

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
            "models_subdir": models_subdir,
            "num_envs": num_envs,
            "vec_env_type": vec_env_type,
            "clean_models_before_train": bool(
                getattr(cfg, "sb3_clean_models_before_train", True)
            ),
            "train_lean": bool(getattr(cfg, "sb3_train_lean", True)),
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
            "finalizer_override_profile": str(
                getattr(cfg, "finalizer_override_profile", "strict") or "strict"
            ).strip().lower(),
        }
        with open(model_dir / f"sb3_latest_{rl_side}.meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        print(f"SB3 training complete for {rl_side} -> {out_path}")

    if not trained_any:
        raise SystemExit("No training phases executed; check scenario_schedule/rl_sides in train_config.json.")


if __name__ == "__main__":
    main()

