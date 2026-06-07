from __future__ import annotations

from pathlib import Path

from assault_model.actions.status import WaitAction
from assault_sim.config.ppo_config import PPOConfig
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.state_encoder import encode_state
from assault_sim.rl.tactical_options import TacticalOption


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
        obs = encode_state(state, unit=unit, rl_side=rl_side, max_turns=max_turns)
        action_pair, _ = model.predict(obs, deterministic=True)
        option_idx = int(action_pair[0])
        attack_mode = int(action_pair[1])

        try:
            option = TacticalOption(option_idx)
        except Exception:
            option = TacticalOption.HOLD

        action = self.executor.execute(
            state=state,
            unit=unit,
            option=option,
            attack_mode=attack_mode,
        )
        if action is None:
            action = WaitAction(unit.unit_id)
        action.unit_id = unit.unit_id
        return action, option.name

