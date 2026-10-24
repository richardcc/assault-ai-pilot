from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from assault_sim.config.config_loader import load_sim_config
from assault_sim.config.train_config import load_train_config
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


REPO_ROOT = Path(__file__).resolve().parents[1]
SIM_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "sim_config.yaml"
ENV_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "env_config.json"
TRAIN_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "train_config.json"


def axial_to_ui_label(pos: tuple[int, int] | None) -> str | None:
    if pos is None:
        return None
    q, r = pos
    return f"{chr(65 + int(q))}{int(r) + 1}"


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
        out[coords] = ownership_to_side.get(getattr(hs, "ownership", None))
    return out


def run_episode(seed: int, scenario: str, rl_side: str, model, obs_normalizer):
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
    controller = SB3EvalController(model, rl_side, env.sim, obs_normalizer=obs_normalizer)
    controller.training_mode = False
    controller.reset()
    runner = MatchRunner(env, controller=controller)

    initial_owners = vp_owner_map(env.sim.game_state)
    prev = dict(initial_owners)
    us_initial_vps = {coords for coords, owner in initial_owners.items() if owner == "US"}

    step = 0
    done = False
    first_loss = None
    # Per-unit recent route (sequence of visited positions over actions).
    route_by_unit: dict[str, deque[tuple[int, int] | None]] = defaultdict(lambda: deque(maxlen=10))

    while not done:
        state_before = env.sim.game_state
        pos_before_by_unit = {
            u.unit_id: ((u.position.q, u.position.r) if u.position is not None else None)
            for u in getattr(state_before, "units", [])
        }
        step_data = runner.step(controller, obs)
        if not step_data:
            break
        obs = step_data.get("obs")
        done = bool(step_data.get("done", False))
        step += 1

        state_after = env.sim.game_state
        now = vp_owner_map(state_after)

        actor = step_data.get("unit")
        actor_id = getattr(actor, "unit_id", None)
        actor_side = step_data.get("side")
        action_obj = step_data.get("action")
        action_name = action_obj.__class__.__name__ if action_obj is not None else "UNKNOWN"
        pos_before = pos_before_by_unit.get(actor_id)
        unit_after = next(
            (u for u in getattr(state_after, "units", []) if getattr(u, "unit_id", None) == actor_id),
            None,
        )
        pos_after = (
            (unit_after.position.q, unit_after.position.r)
            if unit_after is not None and unit_after.position is not None
            else None
        )
        if actor_id:
            route = route_by_unit[actor_id]
            if not route or route[-1] != pos_before:
                route.append(pos_before)
            if route[-1] != pos_after:
                route.append(pos_after)

        for coords in us_initial_vps:
            if prev.get(coords) == "US" and now.get(coords) != "US":
                first_loss = {
                    "seed": seed,
                    "step": step,
                    "turn": int(getattr(state_after, "turn", 0)),
                    "vp_coords": list(coords),
                    "vp_label": axial_to_ui_label(coords),
                    "owner_before": prev.get(coords),
                    "owner_after": now.get(coords),
                    "actor_side": actor_side,
                    "actor_id": actor_id,
                    "action": action_name,
                    "pos_before": list(pos_before) if pos_before is not None else None,
                    "pos_after": list(pos_after) if pos_after is not None else None,
                    "pos_before_label": axial_to_ui_label(pos_before),
                    "pos_after_label": axial_to_ui_label(pos_after),
                    "actor_route_recent": [
                        list(p) if p is not None else None
                        for p in route_by_unit.get(actor_id, [])
                    ],
                    "actor_route_recent_labels": [
                        axial_to_ui_label(p)
                        for p in route_by_unit.get(actor_id, [])
                    ],
                }
                break
        if first_loss is not None:
            break

        prev = now

    final_owners = vp_owner_map(env.sim.game_state)
    return {
        "seed": seed,
        "first_us_vp_loss": first_loss,
        "initial_owners": {str(k): v for k, v in initial_owners.items()},
        "final_owners": {str(k): v for k, v in final_owners.items()},
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze first US VP loss across episodes/seeds.")
    parser.add_argument("--episodes", type=int, default=20, help="Number of episodes to run.")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for first episode.")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario id override.")
    parser.add_argument("--side", type=str, default=None, help="RL side override.")
    parser.add_argument(
        "--out",
        type=str,
        default=str(REPO_ROOT / "assault_sim" / "session" / "reports" / "vp_loss_scan.json"),
        help="Output JSON report path.",
    )
    args = parser.parse_args()

    cfg = load_train_config(TRAIN_CONFIG_PATH)
    rl_side = (
        args.side.upper()
        if args.side
        else (cfg.rl_sides[0] if getattr(cfg, "rl_sides", None) else cfg.rl_side).upper()
    )
    scenario = (
        args.scenario
        if args.scenario
        else (str(cfg.scenario_schedule[0].id) if getattr(cfg, "scenario_schedule", None) else str(cfg.scenario))
    )

    model_path = _resolve_model_path_for_side(REPO_ROOT, rl_side)
    if model_path is None:
        raise SystemExit(f"Model not found for side={rl_side}")
    model = PPO.load(str(model_path), device="cpu")

    results = []
    for i in range(args.episodes):
        seed = int(args.seed_start) + i
        obs_normalizer = build_obs_normalizer(REPO_ROOT, scenario, rl_side, seed)
        ep = run_episode(seed=seed, scenario=scenario, rl_side=rl_side, model=model, obs_normalizer=obs_normalizer)
        results.append(ep)
        loss = ep["first_us_vp_loss"]
        if loss is None:
            print(f"[seed={seed}] no US VP loss detected")
        else:
            route_labels = loss.get("actor_route_recent_labels") or []
            print(
                f"[seed={seed}] first loss turn={loss['turn']} step={loss['step']} "
                f"vp={loss.get('vp_label')} actor={loss['actor_side']}:{loss['actor_id']} "
                f"{loss['action']} {loss.get('pos_before_label')}->{loss.get('pos_after_label')} "
                f"route={route_labels}"
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "episodes": int(args.episodes),
        "seed_start": int(args.seed_start),
        "scenario": scenario,
        "rl_side": rl_side,
        "results": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nSaved report: {out_path}")


if __name__ == "__main__":
    main()
