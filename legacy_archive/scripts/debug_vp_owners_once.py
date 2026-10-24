# scripts/debug_vp_owners_once.py
from __future__ import annotations

from pathlib import Path

from stable_baselines3 import PPO

from assault_sim.config.train_config import load_train_config
from assault_sim.config.config_loader import load_sim_config
from assault_sim.debug.debug_config import DebugConfig
from assault_sim.engine.match_runner import MatchRunner
from assault_sim.envs.gym_assault_env import GymAssaultEnv
from assault_sim.evaluation.eval_sb3 import (
    SB3EvalController,
    _resolve_model_path_for_side,
    _resolve_vecnorm_path_for_side,
)
from assault_sim.rewards.shaped_reward import ShapedReward
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize


REPO_ROOT = Path(__file__).resolve().parents[1]
SIM_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "sim_config.yaml"
ENV_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "env_config.json"
TRAIN_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "train_config.json"


def build_obs_normalizer(repo_root: Path, scenario: str, rl_side: str, seed: int):
    vecnorm_path = _resolve_vecnorm_path_for_side(repo_root, rl_side)
    if vecnorm_path is None or not vecnorm_path.exists():
        return None

    def make_norm_env():
        return Monitor(GymAssaultEnv(scenario=scenario, rl_side=rl_side, seed=seed))

    norm_env = DummyVecEnv([make_norm_env])
    vecnorm = VecNormalize.load(str(vecnorm_path), norm_env)
    vecnorm.training = False
    vecnorm.norm_reward = False

    def _normalize_obs(obs):
        import numpy as np
        arr = np.asarray(obs, dtype=np.float32)
        return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

    return _normalize_obs


def vp_owner_map(game_state):
    side_to_ownership = getattr(game_state, "side_to_ownership", {}) or {}
    ownership_to_side = {v: k for k, v in side_to_ownership.items()}
    points = getattr(getattr(game_state, "victory", None), "points", []) or []

    out = {}
    for vp in points:
        coords = tuple(vp.hex_coords)
        hs = game_state.hex_states.get(coords)
        owner_side = ownership_to_side.get(getattr(hs, "ownership", None))
        out[coords] = owner_side
    return out


def print_vp_snapshot(tag: str, game_state):
    points = getattr(getattr(game_state, "victory", None), "points", []) or []
    owners = vp_owner_map(game_state)
    print(f"\n=== {tag} ===")
    for vp in points:
        coords = tuple(vp.hex_coords)
        print(f"VP {coords} value={int(vp.per_turn)} owner={owners.get(coords)}")


def main():
    cfg = load_train_config(TRAIN_CONFIG_PATH)
    rl_side = (cfg.rl_sides[0] if getattr(cfg, "rl_sides", None) else cfg.rl_side).upper()
    scenario = str(cfg.scenario_schedule[0].id) if getattr(cfg, "scenario_schedule", None) else str(cfg.scenario)
    seed = int(cfg.seed)

    model_path = _resolve_model_path_for_side(REPO_ROOT, rl_side)
    if model_path is None:
        raise SystemExit(f"Model not found for side={rl_side}")

    model = PPO.load(str(model_path), device="cpu")

    sim_cfg = load_sim_config(SIM_CONFIG_PATH)
    sim_cfg.scenario_name = scenario
    sim = SimEnv(config=sim_cfg, controller=None, debug_config=DebugConfig(enabled=False))

    env = TrainingEnv(
        sim_env=sim,
        env_config_path=ENV_CONFIG_PATH,
        rl_side=rl_side,
        scenario_override=scenario,
        reward_fn=ShapedReward(rl_side=rl_side),
        seed=seed,
    )

    obs = env.reset()
    obs_normalizer = build_obs_normalizer(REPO_ROOT, scenario, rl_side, seed)
    controller = SB3EvalController(model, rl_side, env.sim, obs_normalizer=obs_normalizer)
    controller.training_mode = False
    controller.reset()

    state = env.sim.game_state
    print_vp_snapshot("INITIAL VP OWNERS", state)

    prev = vp_owner_map(state)
    step = 0
    runner = MatchRunner(env, controller=controller)

    done = False
    while not done:
        state_before = env.sim.game_state
        pos_before_by_unit = {
            u.unit_id: ((u.position.q, u.position.r) if u.position is not None else None)
            for u in getattr(state_before, "units", [])
        }
        step_data = runner.step(controller, obs)
        if not step_data:
            break
        next_obs = step_data.get("obs")
        done = bool(step_data.get("done", False))
        step += 1
        state = env.sim.game_state
        now = vp_owner_map(state)
        actor = step_data.get("unit")
        actor_id = getattr(actor, "unit_id", None)
        actor_side = step_data.get("side")
        action_obj = step_data.get("action")
        action_name = action_obj.__class__.__name__ if action_obj is not None else "UNKNOWN"
        pos_before = pos_before_by_unit.get(actor_id)
        unit_after = next(
            (u for u in getattr(state, "units", []) if getattr(u, "unit_id", None) == actor_id),
            None,
        )
        pos_after = (
            (unit_after.position.q, unit_after.position.r)
            if unit_after is not None and unit_after.position is not None
            else None
        )

        # imprime solo cuando cambia propietario de algún VP
        for coords in sorted(now.keys()):
            if prev.get(coords) != now.get(coords):
                print(
                    f"[STEP {step:04d}][TURN {state.turn}] VP {coords}: "
                    f"{prev.get(coords)} -> {now.get(coords)} | "
                    f"actor={actor_side}:{actor_id} action={action_name} "
                    f"pos={pos_before}->{pos_after}"
                )

        prev = now
        obs = next_obs

    print_vp_snapshot("FINAL VP OWNERS", state)


if __name__ == "__main__":
    main()