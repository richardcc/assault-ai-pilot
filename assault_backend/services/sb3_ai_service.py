from __future__ import annotations

from pathlib import Path
import numpy as np
import os

from assault_model.actions.status import WaitAction
from assault_sim.config.ppo_config import PPOConfig
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.state_encoder import encode_state
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent


class SB3AIService:
    """
    Backend inference wrapper to drive /api/game/ai-turn with SB3 PPO.
    """

    def __init__(self, model_path: Path | None = None):
        try:
            from stable_baselines3 import PPO
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "stable-baselines3 is required for SB3AIService"
            ) from exc

        self.default_rl_side = PPOConfig.RL_SIDE
        self.heuristic = TacticalPathHeuristic()
        self.executor = OptionExecutor(self.heuristic, avoid_bad_trades=False, adv_threshold=-0.5)
        self.repo_root = Path(__file__).resolve().parents[2]
        self._explicit_model_path = model_path
        self._models_by_side: dict[str, object] = {}
        self._model_path_by_side: dict[str, Path] = {}
        self._strategy_lock_by_side: dict[str, tuple[int, StrategicIntent]] = {}
        self._vecnorm_by_side: dict[str, object] = {}

        any_default = self._resolve_model_path_for_side(self.default_rl_side)
        if any_default is None:
            raise FileNotFoundError(
                "No SB3 checkpoint found. Expected side-specific checkpoints, e.g.: "
                f"{self.repo_root / 'models' / 'sb3_latest_<SIDE>.zip'} or "
                f"{self.repo_root / 'models' / 'sb3_best_<SIDE>' / 'best_model.zip'}"
            )

    def _resolve_model_path_for_side(self, side: str | None) -> Path | None:
        normalized_side = (side or "").strip().upper()
        candidates = [
            self._explicit_model_path,
            self.repo_root / "models" / f"sb3_latest_{normalized_side}.zip" if normalized_side else None,
            self.repo_root / "models" / f"sb3_best_{normalized_side}" / "best_model.zip" if normalized_side else None,
        ]
        return next((p for p in candidates if p is not None and p.exists()), None)

    def _get_model_for_side(self, side: str | None):
        normalized_side = (side or "").strip().upper()
        if normalized_side in self._models_by_side:
            return self._models_by_side[normalized_side]
        chosen = self._resolve_model_path_for_side(normalized_side)
        if chosen is None:
            return None
        try:
            from stable_baselines3 import PPO
            model = PPO.load(str(chosen), device="cpu")
        except Exception:
            return None
        self._models_by_side[normalized_side] = model
        self._model_path_by_side[normalized_side] = chosen
        return model

    def can_control_side(self, side: str | None) -> bool:
        return self._get_model_for_side(side) is not None

    def _resolve_vecnormalize_path_for_side(self, side: str | None) -> Path | None:
        normalized_side = (side or "").strip().upper()
        candidates = [
            self.repo_root / "models" / f"sb3_vecnormalize_{normalized_side}.pkl" if normalized_side else None,
            self.repo_root / "models" / "sb3_vecnormalize.pkl",
        ]
        return next((p for p in candidates if p is not None and p.exists()), None)

    def _build_obs_normalizer_for_side(self, side: str | None):
        normalized_side = (side or "").strip().upper()
        if normalized_side in self._vecnorm_by_side:
            return self._vecnorm_by_side[normalized_side]
        vecnorm_path = self._resolve_vecnormalize_path_for_side(normalized_side)
        if vecnorm_path is None:
            self._vecnorm_by_side[normalized_side] = None
            return None
        try:
            from stable_baselines3.common.monitor import Monitor
            from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
            from assault_sim.envs.gym_assault_env import GymAssaultEnv
        except Exception:
            self._vecnorm_by_side[normalized_side] = None
            return None
        try:
            # Seed is only required to build a shape-compatible env for loading stats.
            def _make_env():
                return Monitor(
                    GymAssaultEnv(
                        scenario=getattr(PPOConfig, "SCENARIO", None),
                        rl_side=normalized_side or PPOConfig.RL_SIDE,
                        seed=int(os.getenv("ASSAULT_UI_SB3_SEED", "42")),
                    )
                )
            norm_env = DummyVecEnv([_make_env])
            vecnorm = VecNormalize.load(str(vecnorm_path), norm_env)
            vecnorm.training = False
            vecnorm.norm_reward = False
            self._vecnorm_by_side[normalized_side] = vecnorm
            return vecnorm
        except Exception:
            self._vecnorm_by_side[normalized_side] = None
            return None

    def _normalize_obs(self, side: str | None, obs: np.ndarray) -> np.ndarray:
        vecnorm = self._build_obs_normalizer_for_side(side)
        if vecnorm is None:
            return obs
        arr = np.asarray(obs, dtype=np.float32)
        return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

    def _objective_tracked_side(self, env) -> str | None:
        outcomes = getattr(getattr(env, "scenario", None), "victory_outcomes", None) or {}
        metric = str(outcomes.get("metric", "")).strip()
        timing = str(outcomes.get("timing", "")).strip()
        tracked = str(outcomes.get("tracked_side", "")).strip().upper()
        if metric == "objectives_captured" and timing == "end_of_last_turn" and tracked:
            return tracked
        return None

    def choose_unit_and_action(self, env, side: str | None):
        rl_side = (side or "").upper()
        state = env.game_state
        model = self._get_model_for_side(rl_side)
        if model is None:
            return None, None, "WAIT_NO_MODEL"
        candidates = sorted(
            [
                u for u in getattr(state, "units", [])
                if getattr(u, "alive", False)
                and str(getattr(u, "side", "")).upper() == rl_side
                and getattr(u, "unit_id", None) not in getattr(env.runtime, "activated_units", set())
            ],
            key=lambda u: str(getattr(u, "unit_id", "")),
        )
        if not candidates:
            return None, WaitAction("SYSTEM"), "WAIT_NO_CANDIDATES"
        scenario = getattr(env, "scenario", None)
        max_turns = getattr(scenario, "max_turns", None)
        obs = encode_state(state, unit=None, rl_side=rl_side, max_turns=max_turns, scenario=scenario)
        obs = self._normalize_obs(rl_side, obs)
        action_pair, _ = model.predict(obs, deterministic=True)
        action_vec = np.asarray(action_pair).reshape(-1)
        if action_vec.size not in (3, 4):
            raise RuntimeError(
                f"Expected action [strategy, option, attack_mode(, unit_slot)], got shape={action_vec.shape}"
            )
        strategy_idx = int(action_vec[0])
        option_idx = int(action_vec[1])
        attack_mode = int(action_vec[2])
        unit_slot = int(action_vec[3]) if action_vec.size >= 4 else 0
        unit = candidates[unit_slot % len(candidates)]

        sampled_strategy = StrategicIntent(strategy_idx)
        turn_now = int(getattr(state, "turn", 0))
        prev = self._strategy_lock_by_side.get(rl_side)
        if prev is None or prev[0] != turn_now:
            self._strategy_lock_by_side[rl_side] = (turn_now, sampled_strategy)
            strategy = sampled_strategy
        else:
            strategy = prev[1]
        option = TacticalOption(option_idx)
        action = self.executor.execute(
            state=state,
            unit=unit,
            option=option,
            attack_mode=attack_mode,
            strategy=strategy,
            objective_tracked_side=self._objective_tracked_side(env),
        )
        if action is None:
            action = WaitAction(unit.unit_id)
        action.unit_id = unit.unit_id
        return unit, action, option.name

    def choose_action(self, env, unit):
        rl_side = unit.side
        state = env.game_state
        scenario = getattr(env, "scenario", None)
        max_turns = getattr(scenario, "max_turns", None)
        model = self._get_model_for_side(rl_side)
        if model is None:
            action = WaitAction(unit.unit_id)
            action.unit_id = unit.unit_id
            return action, "WAIT_NO_MODEL"
        obs = encode_state(state, unit=unit, rl_side=rl_side, max_turns=max_turns, scenario=scenario)
        obs = self._normalize_obs(rl_side, obs)
        action_pair, _ = model.predict(obs, deterministic=True)
        action_vec = np.asarray(action_pair).reshape(-1)
        if action_vec.size not in (3, 4):
            raise RuntimeError(
                f"Expected action [strategy, option, attack_mode(, unit_slot)], got shape={action_vec.shape}"
            )
        strategy_idx = int(action_vec[0])
        option_idx = int(action_vec[1])
        attack_mode = int(action_vec[2])

        sampled_strategy = StrategicIntent(strategy_idx)
        turn_now = int(getattr(state, "turn", 0))
        prev = self._strategy_lock_by_side.get(rl_side)
        if prev is None or prev[0] != turn_now:
            self._strategy_lock_by_side[rl_side] = (turn_now, sampled_strategy)
            strategy = sampled_strategy
        else:
            strategy = prev[1]
        option = TacticalOption(option_idx)

        action = self.executor.execute(
            state=state,
            unit=unit,
            option=option,
            attack_mode=attack_mode,
            strategy=strategy,
            objective_tracked_side=self._objective_tracked_side(env),
        )
        if action is None:
            action = WaitAction(unit.unit_id)
        action.unit_id = unit.unit_id
        return action, option.name

