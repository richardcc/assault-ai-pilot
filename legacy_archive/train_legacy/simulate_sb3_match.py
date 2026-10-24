from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from assault_sim.config.train_config import load_train_config
from assault_sim.engine.match_runner import MatchRunner
from assault_sim.evaluation.eval_sb3 import (
    SB3EvalController,
    _resolve_model_path_for_side,
    _resolve_vecnorm_path_for_side,
)
from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.rewards.shaped_reward import ShapedReward
from assault_sim.debug.replay_observer import ReplayObserver
from assault_sim.debug.replay_writer import ReplayWriter
from assault_sim.debug.replay_utils import extract_initial_state
from assault_sim.debug.console_observer import ConsoleObserver


REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "sim_config.yaml"
ENV_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "env_config.json"
TRAIN_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "train_config.json"


def _build_obs_normalizer(repo_root: Path, scenario: str, rl_side: str, seed: int):
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
    from assault_sim.envs.gym_assault_env import GymAssaultEnv

    vecnorm_path = _resolve_vecnorm_path_for_side(repo_root, rl_side)
    if vecnorm_path is None or not vecnorm_path.exists():
        return None, None

    def make_norm_env():
        return Monitor(
            GymAssaultEnv(
                scenario=scenario,
                rl_side=rl_side,
                seed=seed,
            )
        )

    norm_env = DummyVecEnv([make_norm_env])
    vecnorm = VecNormalize.load(str(vecnorm_path), norm_env)
    vecnorm.training = False
    vecnorm.norm_reward = False

    def _normalize_obs(obs):
        arr = np.asarray(obs, dtype=np.float32)
        return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

    return _normalize_obs, vecnorm_path


def _resolve_scenario_from_cfg(cfg, explicit: str | None) -> str:
    if explicit:
        return explicit
    if getattr(cfg, "scenario_schedule", None):
        return str(cfg.scenario_schedule[0].id)
    return str(cfg.scenario)


def _resolve_rl_side_from_cfg(cfg, explicit: str | None) -> str:
    if explicit:
        return explicit.upper()
    if getattr(cfg, "rl_sides", None):
        return str(cfg.rl_sides[0]).upper()
    return str(cfg.rl_side).upper()


def run_simulation(
    rl_side: str | None = None,
    scenario: str | None = None,
    seed: int | None = None,
    show_console: bool = True,
) -> Path:
    from stable_baselines3 import PPO

    cfg = load_train_config(TRAIN_CONFIG_PATH)
    rl_side = _resolve_rl_side_from_cfg(cfg, rl_side)
    scenario = _resolve_scenario_from_cfg(cfg, scenario)
    sim_seed = int(seed if seed is not None else cfg.seed)

    model_path = _resolve_model_path_for_side(REPO_ROOT, rl_side)
    if model_path is None:
        raise SystemExit(f"SB3 model not found for side={rl_side}. Expected under {REPO_ROOT / 'models'}")

    model = PPO.load(str(model_path), device="cpu")
    sim_config = load_sim_config(SIM_CONFIG_PATH)
    sim_config.scenario_name = scenario
    sim_env = SimEnv(
        config=sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=bool(show_console)),
    )
    env = TrainingEnv(
        sim_env=sim_env,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=rl_side,
        scenario_override=scenario,
        reward_fn=ShapedReward(rl_side=rl_side),
        seed=sim_seed,
    )

    obs = env.reset()
    obs_normalizer, vecnorm_path = _build_obs_normalizer(REPO_ROOT, scenario, rl_side, sim_seed)
    controller = SB3EvalController(model, rl_side, env.sim, obs_normalizer=obs_normalizer)
    controller.training_mode = False
    controller.reset()

    replay_observer = ReplayObserver()
    console_observer = ConsoleObserver(rl_side=rl_side) if show_console else None
    if env.sim is not None and getattr(env.sim, "event_bus", None) is not None:
        if console_observer is not None:
            env.sim.event_bus.subscribe(console_observer)
        env.sim.event_bus.subscribe(replay_observer)

    replay_observer.replay.initial_state = extract_initial_state(env.sim.game_state)
    replay_observer.replay.meta = {
        "scenario_id": scenario,
        "rl_side": rl_side,
        "model_path": str(model_path),
        "vecnormalize_path": str(vecnorm_path) if vecnorm_path is not None else None,
        "seed": sim_seed,
    }

    runner = MatchRunner(env, controller=controller)
    done = False
    step_count = 0
    while not done:
        step = runner.step(controller, obs)
        if not step:
            break
        obs = step.get("obs")
        done = bool(step.get("done", False))
        step_count += 1

    final_state = env.sim.game_state
    replay_observer.replay.meta["result"] = {
        "winner": getattr(final_state, "winner", None),
        "reason": getattr(final_state, "end_reason", None),
        "steps": step_count,
        "turn": getattr(final_state, "turn", None),
    }

    out_dir = REPO_ROOT / "assault_sim" / "session" / "replays"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base_name = f"sb3_{scenario}_{rl_side}_{stamp}"
    replay_path = out_dir / f"{base_name}.json"
    summary_path = out_dir / f"{base_name}.summary.json"

    ReplayWriter.write(replay_observer.replay, replay_path)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(replay_observer.replay.meta, f, indent=2)

    print(f"[OK] Replay saved: {replay_path}")
    print(f"[OK] Summary saved: {summary_path}")
    return replay_path


def main():
    parser = argparse.ArgumentParser(description="Simulate one SB3 match and save replay.")
    parser.add_argument("--side", type=str, default=None, help="RL side (default from train_config)")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario id (default first from schedule)")
    parser.add_argument("--seed", type=int, default=None, help="Seed override")
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="Disable live console observer output while simulating",
    )
    args = parser.parse_args()

    run_simulation(
        rl_side=args.side,
        scenario=args.scenario,
        seed=args.seed,
        show_console=not bool(args.no_console),
    )


if __name__ == "__main__":
    main()

