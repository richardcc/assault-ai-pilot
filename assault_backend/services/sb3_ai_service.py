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

        self.rl_side = PPOConfig.RL_SIDE
        self.heuristic = TacticalPathHeuristic()
        self.executor = OptionExecutor(self.heuristic, avoid_bad_trades=False, adv_threshold=-0.5)

        repo_root = Path(__file__).resolve().parents[2]
        candidates = [
            model_path,
            repo_root / "models" / "sb3_latest.zip",
            repo_root / "models" / "sb3_best" / "best_model.zip",
        ]
        chosen = next((p for p in candidates if p is not None and p.exists()), None)
        if chosen is None:
            raise FileNotFoundError(
                "No SB3 checkpoint found. Expected one of: "
                f"{repo_root / 'models' / 'sb3_latest.zip'} or "
                f"{repo_root / 'models' / 'sb3_best' / 'best_model.zip'}"
            )

        self.model = PPO.load(str(chosen), device="cpu")
        self.model_path = chosen

    def can_control_side(self, side: str | None) -> bool:
        return side == self.rl_side

    def choose_action(self, env, unit):
        state = env.game_state
        scenario = getattr(env, "scenario", None)
        max_turns = getattr(scenario, "max_turns", None)
        obs = encode_state(state, unit=unit, rl_side=self.rl_side, max_turns=max_turns)
        action_pair, _ = self.model.predict(obs, deterministic=True)
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

