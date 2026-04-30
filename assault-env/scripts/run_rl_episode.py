import torch
import random
from pathlib import Path
from typing import Optional

from stable_baselines3 import PPO

from assault_env.env import AssaultEnv
from assault_env.renderer import AsciiRenderer

from assault.replay.snapshot import snapshot
from assault.replay.replay import Replay
from assault.replay.serialization import save_replay_to_json


ACTION_NAMES = {
    0: "WAIT",
    1: "MOVE_FORWARD",
    2: "ATTACK",
    3: "MOVE_BACKWARD",
    4: "MOVE_LEFT",
    5: "MOVE_RIGHT",
    6: "WAIT",
}


def find_latest_model(models_dir: Path) -> Path:
    """
    Find the most recent PPO explainable model.
    """
    candidates = [
        p for p in models_dir.glob("*.zip")
        if "ppo" in p.name and "explainable" in p.name
    ]

    if not candidates:
        raise FileNotFoundError(
            f"No PPO explainable models found in {models_dir}"
        )

    # Sort by modification time (newest last)
    candidates.sort(key=lambda p: p.stat().st_mtime)

    return candidates[-1]


def get_unit(state, unit_id):
    for units in state.units.values():
        if unit_id in units:
            return units[unit_id]
    return None


def build_obs(state, unit_id):
    unit = get_unit(state, unit_id)
    if unit is None:
        return None

    return state  # minimal obs, compatible with PPO


def run_episode():
    env = AssaultEnv()
    renderer = AsciiRenderer()

    # ---------------------------------
    # Dynamic model resolution ✅
    # ---------------------------------
    project_root = Path(__file__).resolve().parents[2]
    models_dir = project_root / "models"

    model_path = find_latest_model(models_dir)
    print(f"✅ Loading model: {model_path.name}")

    model = PPO.load(model_path)
    policy = model.policy

    replay_states = []

    obs, _ = env.reset()
    done = False
    turn = 0

    activation_order = (
        list(env.state.units["IT"].keys()) +
        list(env.state.units["EN"].keys())
    )
    activation_idx = 0

    env.state.turn = turn
    replay_states.append(snapshot(env.state))
    renderer.render(env.state, turn=turn)

    while not done:

        # ---- activation order (copied logic) ----
        active_unit_id = None
        for _ in range(len(activation_order)):
            candidate = activation_order[activation_idx]
            activation_idx = (activation_idx + 1) % len(activation_order)
            if get_unit(env.state, candidate) is not None:
                active_unit_id = candidate
                break

        if active_unit_id is None:
            break

        obs = build_obs(env.state, active_unit_id)
        if obs is None:
            continue

        # ---- RL action + rationale ----
        with torch.no_grad():
            obs_tensor, _ = policy.obs_to_tensor(obs)
            outputs = policy.forward(obs_tensor)

            action, _ = model.predict(obs, deterministic=True)

            learned_rationale: Optional[int] = None
            if isinstance(outputs, tuple) and len(outputs) >= 2:
                rationale_logits = outputs[1]
                if rationale_logits is not None:
                    learned_rationale = int(
                        rationale_logits.argmax(dim=-1).item()
                    )

        action_name = ACTION_NAMES[int(action)]

        obs, _, terminated, truncated, info = env.step(int(action))
        done = terminated or truncated
        turn += 1

        decision = {
            "unit_id": active_unit_id,
            "action": action_name,
            "learned_rationale": learned_rationale,
            "heuristic_rationale": None,
        }

        env.state.turn = turn
        replay_states.append(snapshot(env.state, decision=decision))
        renderer.render(env.state, turn=turn)

    replay = Replay(replay_states)
    save_replay_to_json(replay, "replays/rl_simple_duel_run_latest.json")

    print("✅ RL replay generated successfully")


if __name__ == "__main__":
    run_episode()
