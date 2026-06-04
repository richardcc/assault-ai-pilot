from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import numpy as np

from assault_model.actions.status import WaitAction
from assault_sim.config.ppo_config import PPOConfig
from assault_sim.decision.action_bridge import ActionBridge
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.engine.env_factory import make_env
from assault_sim.evaluation.eval_dashboard import EvalDashboard
from assault_sim.evaluation.evaluator import Evaluator
from assault_sim.evaluation.results_analyzer import ResultsAnalyzer
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rewards.shaped_reward import ShapedReward


class SB3EvalController:
    def __init__(self, model, rl_side: str, sim_env, obs_normalizer=None):
        self.model = model
        self.rl_side = rl_side
        self.sim_env = sim_env
        self.obs_normalizer = obs_normalizer
        self.heuristic = TacticalPathHeuristic()
        self.executor = OptionExecutor(self.heuristic, avoid_bad_trades=False, adv_threshold=-0.5)
        self.action_bridge = ActionBridge()

        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_decision_trace = None
        self.current_strategy = None
        self.training_mode = False
        self._strategy_stub = type("SB3Strategy", (), {})

    def reset(self):
        self.current_option = None
        self.current_option_sampled = None
        self.current_option_resolved = None
        self.current_attack_mode = 0
        self.last_decision_trace = None

    def _enemy_action(self, state, unit):
        for opt in (
            TacticalOption.ATTACK,
            TacticalOption.FLANK,
            TacticalOption.ADVANCE,
            TacticalOption.RETREAT,
            TacticalOption.HOLD,
        ):
            action = self.heuristic.choose_action(state, unit, opt)
            if action is not None:
                return action
        return WaitAction(unit.unit_id)

    def act(self, state, side, unit, obs):
        if side != self.rl_side:
            action = self._enemy_action(state, unit)
            action.unit_id = unit.unit_id
            self.sim_env.runtime.activated_units.add(unit.unit_id)
            return action

        model_obs = obs
        if self.obs_normalizer is not None:
            model_obs = self.obs_normalizer(obs)
        action_pair, _ = self.model.predict(model_obs, deterministic=True)
        option_idx = int(action_pair[0])
        attack_mode = int(action_pair[1])
        sampled_option = TacticalOption(option_idx)
        resolved_option = sampled_option
        # Expose a synthetic L3 label so L3 metrics are not empty in SB3 eval.
        strategy_name = (
            "ATTACK"
            if sampled_option == TacticalOption.ATTACK
            else "MANEUVER"
            if sampled_option in (TacticalOption.ADVANCE, TacticalOption.FLANK)
            else "HOLD"
        )
        self.current_strategy = self._strategy_stub()
        self.current_strategy.name = strategy_name

        action = self.executor.execute(
            state=state,
            unit=unit,
            option=resolved_option,
            attack_mode=attack_mode,
        )
        if action is None:
            action = WaitAction(unit.unit_id)

        executed_option = self.action_bridge.infer_executed_option(action, resolved_option)
        self.current_option_sampled = sampled_option
        self.current_option_resolved = resolved_option
        self.current_option = executed_option
        self.current_attack_mode = attack_mode if executed_option == TacticalOption.ATTACK else 0
        self.last_decision_trace = self.action_bridge.build_trace(
            sampled_option=sampled_option,
            resolved_option=resolved_option,
            executed_option=executed_option,
            strategy_name=strategy_name,
        )

        action.unit_id = unit.unit_id
        self.sim_env.runtime.activated_units.add(unit.unit_id)
        return action


def evaluate_sb3(episodes: int = 100):
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.monitor import Monitor
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "stable-baselines3 is not installed. Install with: pip install stable-baselines3 gymnasium"
        ) from exc

    repo_root = Path(__file__).resolve().parents[2]
    model_candidates = [
        repo_root / "models" / "sb3_latest.zip",
        repo_root / "models" / "sb3_best" / "best_model.zip",
    ]
    model_path = next((p for p in model_candidates if p.exists()), None)
    if model_path is None:
        tried = "\n".join(f" - {p}" for p in model_candidates)
        raise SystemExit(
            "SB3 model not found. Tried:\n"
            f"{tried}\n"
            "Tip: if training is still running, wait for first eval checkpoint "
            "(best_model.zip) or training end (sb3_latest.zip)."
        )
    vecnorm_path = repo_root / "models" / "sb3_vecnormalize.pkl"

    env = make_env(
        config_path=repo_root / "assault_sim" / "config" / "sim_config.yaml",
        env_config_path=repo_root / "assault_sim" / "config" / "env_config.json",
        rl_side=PPOConfig.RL_SIDE,
        scenario=PPOConfig.SCENARIO,
        reward_fn=ShapedReward(rl_side=PPOConfig.RL_SIDE),
        seed=PPOConfig.SEED,
    )

    model = PPO.load(str(model_path), device="cpu")
    obs_normalizer = None
    if vecnorm_path.exists():
        try:
            from assault_sim.envs.gym_assault_env import GymAssaultEnv

            def make_norm_env():
                return Monitor(
                    GymAssaultEnv(
                        scenario=PPOConfig.SCENARIO,
                        rl_side=PPOConfig.RL_SIDE,
                        seed=PPOConfig.SEED,
                    )
                )

            norm_env = DummyVecEnv([make_norm_env])
            vecnorm = VecNormalize.load(str(vecnorm_path), norm_env)
            vecnorm.training = False
            vecnorm.norm_reward = False

            def _normalize_obs(obs):
                arr = np.asarray(obs, dtype=np.float32)
                return vecnorm.normalize_obs(arr.reshape(1, -1))[0]

            obs_normalizer = _normalize_obs
            print(f"Loaded VecNormalize stats: {vecnorm_path}")
        except Exception as e:
            print(f"⚠️ Could not load VecNormalize stats, continuing without normalization: {e}")
    else:
        print("⚠️ VecNormalize stats not found, evaluating without obs normalization")

    controller = SB3EvalController(model, PPOConfig.RL_SIDE, env.sim, obs_normalizer=obs_normalizer)
    evaluator = Evaluator(
        env=env,
        rl_controller=controller,
        enemy_controller=None,
        rl_side=PPOConfig.RL_SIDE,
    )
    results = evaluator.evaluate(episodes)

    analyzer = ResultsAnalyzer(results, PPOConfig.RL_SIDE)
    analyzer.print_report()

    dashboard = EvalDashboard()
    for r in results:
        dashboard.add_episode(r)
    dashboard.save_csv("metrics_sb3.csv")

    report = {
        "meta": {
            "episodes": episodes,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model": str(model_path),
            "scenario": PPOConfig.SCENARIO,
            "vecnormalize_path": str(vecnorm_path) if vecnorm_path.exists() else None,
            "obs_normalized": bool(obs_normalizer is not None),
        },
        "summary": analyzer.summary(),
        "combat": analyzer.combat_metrics(),
        "advanced": analyzer.advanced_metrics(),
        "policy_alignment": analyzer.policy_alignment(),
        "action_execution": analyzer.action_execution(),
    }
    out_name = f"metrics_sb3_report_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved SB3 report -> {out_name}")


if __name__ == "__main__":
    evaluate_sb3()

