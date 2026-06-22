from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from assault_sim.config.train_config import load_train_config
from assault_sim.envs.gym_assault_env import GymAssaultEnv
from assault_sim.evaluation.eval_sb3 import (
    _resolve_model_path_for_side,
    _resolve_vecnorm_path_for_side,
)
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.rl.tactical_options import TacticalOption


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAIN_CONFIG_PATH = REPO_ROOT / "assault_sim" / "config" / "train_config.json"


def _build_obs_normalizer(scenario: str, rl_side: str, seed: int):
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

    vecnorm_path = _resolve_vecnorm_path_for_side(REPO_ROOT, rl_side)
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

    def _normalize_obs(obs: np.ndarray) -> np.ndarray:
        arr = np.asarray(obs, dtype=np.float32)
        return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

    return _normalize_obs, vecnorm_path


def _safe_enum_name(enum_cls, idx: int) -> str:
    try:
        return enum_cls(int(idx)).name
    except Exception:
        return f"UNKNOWN_{idx}"


def _resolve_scenario(cfg, explicit: str | None) -> str:
    if explicit:
        return explicit
    if getattr(cfg, "scenario_schedule", None):
        return str(cfg.scenario_schedule[0].id)
    return str(cfg.scenario)


def _resolve_side(cfg, explicit: str | None) -> str:
    if explicit:
        return explicit.upper()
    if getattr(cfg, "rl_sides", None):
        return str(cfg.rl_sides[0]).upper()
    return str(cfg.rl_side).upper()


def _build_step_trace_entry(
    *,
    step_idx: int,
    info: dict[str, Any],
    strategy_idx: int,
    option_idx: int,
    attack_mode: int,
    unit_slot: int,
    reward: float,
    done: bool,
    truncated: bool,
) -> dict[str, Any]:
    info = dict(info or {})
    return {
        "step": step_idx,
        "turn": info.get("turn"),
        "decision_action": {
            "strategy_idx": strategy_idx,
            "strategy": _safe_enum_name(StrategicIntent, strategy_idx),
            "option_idx": option_idx,
            "option": _safe_enum_name(TacticalOption, option_idx),
            "attack_mode": attack_mode,
            "unit_slot": unit_slot,
        },
        "executed": {
            "unit_id": info.get("unit_id"),
            "action_id": info.get("action_id"),
            "action_class": info.get("action_class"),
            "sampled_option": info.get("sampled_option"),
            "resolved_option": info.get("resolved_option"),
            "executed_option": info.get("executed_option"),
            "forced": bool(info.get("forced", False)),
        },
        "capture_debug": {
            "l3_strategy": info.get("l3_strategy"),
            "l2_option": info.get("l2_option"),
            "fallback_to_attack": bool(info.get("capture_fallback_to_attack", False)),
            "fallback_reason": info.get("capture_fallback_reason"),
            "emergency_override": bool(info.get("capture_emergency_override", False)),
            "legal_override": bool(info.get("capture_legal_override", False)),
            "override_reason": info.get("capture_override_reason"),
            "move_block_profile": info.get("capture_move_block_profile"),
            "objective_delta": info.get("objective_captured_delta"),
            "objective_before": info.get("objective_captured_before"),
            "objective_after": info.get("objective_captured_after"),
            "objective_dist_before": info.get("objective_dist_before"),
            "objective_dist_after": info.get("objective_dist_after"),
            "capture_target_dist_before": info.get("capture_target_dist_before"),
            "capture_target_dist_after": info.get("capture_target_dist_after"),
            "move_candidates_total": info.get("capture_move_candidates_total"),
            "progress_candidates": info.get("capture_progress_candidates"),
            "equal_candidates": info.get("capture_equal_candidates"),
            "increase_candidates": info.get("capture_increase_candidates"),
            "reversal_filtered": info.get("capture_reversal_filtered"),
            "progress_available": bool(info.get("capture_progress_available", False)),
            "selected_move_reason": info.get("capture_selected_move_reason"),
            "selected_dist_delta": info.get("capture_selected_dist_delta"),
            "suspected_progress_miss": bool(info.get("capture_suspected_progress_miss", False)),
            "vp_stepin_legal": bool(info.get("vp_stepin_legal", False)),
            "vp_stepin_selected": bool(info.get("vp_stepin_selected", False)),
            "vp_stepin_block_reason": info.get("vp_stepin_block_reason"),
            "vp_nearest_uncaptured_dist": info.get("vp_nearest_uncaptured_dist"),
            "vp_opening_attack_candidates_count": int(info.get("vp_opening_attack_candidates_count", 0) or 0),
        },
        "plan_debug": {
            "intent": info.get("plan_intent"),
            "unit_role": info.get("plan_unit_role"),
            "role_unknown_reason": info.get("plan_role_unknown_reason"),
            "capture_branch": info.get("capture_branch"),
            "focus_vp_id": info.get("plan_focus_vp_id"),
            "plan_step_id": info.get("plan_step_id"),
            "budget_state": info.get("plan_budget_state"),
            "budget_remaining_by_role": info.get("plan_budget_remaining_by_role"),
            "budget_violation_count": int(info.get("plan_budget_violation_count", 0) or 0),
            "budget_violation_delta": int(info.get("plan_budget_violation_delta", 0) or 0),
            "fallback_reason": info.get("plan_fallback_reason"),
            "plan_progress_stub": info.get("plan_progress_stub"),
            "intent_alignment_stub": info.get("intent_alignment_stub"),
        },
        "reward": float(reward),
        "done": bool(done),
        "truncated": bool(truncated),
    }


def record_trace(
    *,
    rl_side: str | None = None,
    scenario: str | None = None,
    episodes: int = 1,
    seed: int | None = None,
    out_path: Path | None = None,
) -> Path:
    from stable_baselines3 import PPO

    cfg = load_train_config(TRAIN_CONFIG_PATH)
    rl_side = _resolve_side(cfg, rl_side)
    scenario = _resolve_scenario(cfg, scenario)
    base_seed = int(seed if seed is not None else cfg.seed)

    model_path = _resolve_model_path_for_side(REPO_ROOT, rl_side)
    if model_path is None:
        raise SystemExit(f"SB3 model not found for side={rl_side}.")
    model = PPO.load(str(model_path), device="cpu")

    obs_normalizer, vecnorm_path = _build_obs_normalizer(scenario, rl_side, base_seed)

    traces: list[dict[str, Any]] = []
    for ep in range(int(episodes)):
        ep_seed = base_seed + ep
        env = GymAssaultEnv(
            scenario=scenario,
            rl_side=rl_side,
            seed=ep_seed,
        )
        obs, _ = env.reset(seed=ep_seed)
        done = False
        truncated = False
        step_idx = 0
        ep_trace: list[dict[str, Any]] = []

        while not done and not truncated:
            model_obs = obs_normalizer(obs) if obs_normalizer is not None else obs
            action, _ = model.predict(model_obs, deterministic=True)
            action_vec = np.asarray(action).reshape(-1).tolist()
            if len(action_vec) < 4:
                action_vec = action_vec + [0]
            strategy_idx, option_idx, attack_mode, unit_slot = [int(x) for x in action_vec[:4]]

            obs, reward, done, truncated, info = env.step(np.array(action_vec[:4], dtype=np.int64))
            info = dict(info or {})

            ep_trace.append(
                _build_step_trace_entry(
                    step_idx=step_idx,
                    info=info,
                    strategy_idx=strategy_idx,
                    option_idx=option_idx,
                    attack_mode=attack_mode,
                    unit_slot=unit_slot,
                    reward=reward,
                    done=done,
                    truncated=truncated,
                )
            )
            step_idx += 1

        final_state = env._train_env.sim.game_state  # noqa: SLF001
        traces.append(
            {
                "episode": ep,
                "seed": ep_seed,
                "winner": getattr(final_state, "winner", None),
                "end_reason": getattr(final_state, "end_reason", None),
                "turn": getattr(final_state, "turn", None),
                "steps": len(ep_trace),
                "trace": ep_trace,
            }
        )
        env.close()

    payload = {
        "meta": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "scenario": scenario,
            "rl_side": rl_side,
            "episodes": int(episodes),
            "base_seed": base_seed,
            "model_path": str(model_path),
            "vecnormalize_path": str(vecnorm_path) if vecnorm_path is not None else None,
        },
        "episodes": traces,
    }

    if out_path is None:
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out_path = REPO_ROOT / "assault_sim" / "session" / "replays" / f"sb3_trace_{scenario}_{rl_side}_{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[OK] Trace saved: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Record SB3 decision trace (JSON, no video).")
    parser.add_argument("--side", type=str, default=None, help="RL side (default from train_config)")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario id (default first from schedule)")
    parser.add_argument("--episodes", type=int, default=1, help="Number of episodes to record")
    parser.add_argument("--seed", type=int, default=None, help="Base seed")
    parser.add_argument("--out", type=str, default=None, help="Output json path")
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    record_trace(
        rl_side=args.side,
        scenario=args.scenario,
        episodes=args.episodes,
        seed=args.seed,
        out_path=out,
    )


if __name__ == "__main__":
    main()

