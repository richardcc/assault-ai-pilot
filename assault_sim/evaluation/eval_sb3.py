from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import numpy as np

from assault_model.actions.status import WaitAction
from assault_sim.config.train_config import load_train_config
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


def _resolve_model_path_for_side(repo_root: Path, rl_side: str) -> Path | None:
    side = (rl_side or "").strip().upper()
    candidates = [
        repo_root / "models" / f"sb3_latest_{side}.zip",
        repo_root / "models" / "sb3_latest.zip",
        repo_root / "models" / f"sb3_best_{side}" / "best_model.zip",
        repo_root / "models" / "sb3_best" / "best_model.zip",
    ]
    return next((p for p in candidates if p.exists()), None)


def _resolve_vecnorm_path_for_side(repo_root: Path, rl_side: str) -> Path | None:
    side = (rl_side or "").strip().upper()
    candidates = [
        repo_root / "models" / f"sb3_vecnormalize_{side}.pkl",
        repo_root / "models" / "sb3_vecnormalize.pkl",
    ]
    return next((p for p in candidates if p.exists()), None)


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


def _safe_name(value: str) -> str:
    return "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in value)


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
    train_config_path = repo_root / "assault_sim" / "config" / "train_config.json"
    cfg = load_train_config(train_config_path)
    scenario_schedule = list(cfg.scenario_schedule)
    rl_sides = list(cfg.rl_sides)
    if not rl_sides:
        rl_sides = [PPOConfig.RL_SIDE]

    all_reports: dict[str, dict[str, dict]] = {}
    all_models = {}
    comparison_rows = []

    for rl_side in rl_sides:
        model_path = _resolve_model_path_for_side(repo_root, rl_side)
        if model_path is None:
            print(f"⚠️ SB3 model not found for side={rl_side}; skipping.")
            continue

        vecnorm_path = _resolve_vecnorm_path_for_side(repo_root, rl_side)
        model = PPO.load(str(model_path), device="cpu")
        all_reports[rl_side] = {}
        all_models[rl_side] = str(model_path)

        for phase in scenario_schedule:
            scenario = phase.id
            sides_in_scenario = _scenario_sides(repo_root, scenario)
            if rl_side not in sides_in_scenario:
                print(
                    f"⚠️ Skip eval side={rl_side} scenario={scenario}: "
                    f"side not present in scenario units (found={sorted(sides_in_scenario)})"
                )
                continue

            print(f"\n=== EVAL side={rl_side} scenario={scenario} episodes={episodes} ===")
            env = make_env(
                config_path=repo_root / "assault_sim" / "config" / "sim_config.yaml",
                env_config_path=repo_root / "assault_sim" / "config" / "env_config.json",
                rl_side=rl_side,
                scenario=scenario,
                reward_fn=ShapedReward(rl_side=rl_side),
                seed=PPOConfig.SEED,
            )

            obs_normalizer = None
            if vecnorm_path is not None and vecnorm_path.exists():
                try:
                    from assault_sim.envs.gym_assault_env import GymAssaultEnv

                    def make_norm_env():
                        return Monitor(
                            GymAssaultEnv(
                                scenario=scenario,
                                rl_side=rl_side,
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
                    print(f"Loaded VecNormalize stats for {rl_side}: {vecnorm_path}")
                except Exception as e:
                    print(f"⚠️ Could not load VecNormalize stats ({rl_side}), continuing without normalization: {e}")
            else:
                print(f"⚠️ VecNormalize stats not found for {rl_side}, evaluating without obs normalization")

            controller = SB3EvalController(model, rl_side, env.sim, obs_normalizer=obs_normalizer)
            evaluator = Evaluator(
                env=env,
                rl_controller=controller,
                enemy_controller=None,
                rl_side=rl_side,
            )
            results = evaluator.evaluate(episodes)

            analyzer = ResultsAnalyzer(results, rl_side)
            analyzer.print_report()

            dashboard = EvalDashboard()
            for r in results:
                dashboard.add_episode(r)
            csv_name = f"metrics_sb3_{_safe_name(rl_side)}_{_safe_name(scenario)}.csv"
            dashboard.save_csv(csv_name)

            side_report = {
                "meta": {
                    "episodes": episodes,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "model": str(model_path),
                    "scenario": scenario,
                    "rl_side": rl_side,
                    "vecnormalize_path": str(vecnorm_path) if vecnorm_path is not None and vecnorm_path.exists() else None,
                    "obs_normalized": bool(obs_normalizer is not None),
                    "csv": csv_name,
                },
                "summary": analyzer.summary(),
                "combat": analyzer.combat_metrics(),
                "advanced": analyzer.advanced_metrics(),
                "policy_alignment": analyzer.policy_alignment(),
                "action_execution": analyzer.action_execution(),
            }
            all_reports[rl_side][scenario] = side_report
            comparison_rows.append({
                "rl_side": rl_side,
                "scenario": scenario,
                "episodes": side_report["summary"].get("episodes", 0),
                "win_rate": side_report["summary"].get("win_rate", 0.0),
                "draws": side_report["summary"].get("draws", 0),
                "avg_vp": side_report["summary"].get("avg_vp", 0.0),
                "avg_steps": side_report["summary"].get("avg_steps", 0.0),
                "end_reason_counts": side_report["summary"].get("end_reason_counts", {}),
                "win_rate_by_end_reason": side_report["summary"].get("win_rate_by_end_reason", {}),
                "trade_mean": side_report["combat"].get("trade_mean", 0.0),
                "damage_ratio": side_report["combat"].get("damage_ratio", 0.0),
            })

    if not all_reports:
        raise SystemExit("No SB3 model found for any configured side.")

    print("\n=== COMPARATIVE SUMMARY (SIDE x SCENARIO) ===")
    if not comparison_rows:
        print("(no valid side/scenario combinations evaluated)")
    else:
        for row in comparison_rows:
            reason_counts = row.get("end_reason_counts", {})
            reason_rates = row.get("win_rate_by_end_reason", {})
            reasons_str = ", ".join(
                f"{reason}:{reason_rates.get(reason, 0.0):.2f} ({count})"
                for reason, count in reason_counts.items()
            ) or "-"
            print(
                f"side={row['rl_side']} scenario={row['scenario']} "
                f"win_rate={row['win_rate']:.3f} avg_vp={row['avg_vp']:.3f} "
                f"avg_steps={row['avg_steps']:.1f} trade_mean={row['trade_mean']:.3f} "
                f"damage_ratio={row['damage_ratio']:.3f} draws={row['draws']} "
                f"reasons=[{reasons_str}]"
            )

    report = {
        "meta": {
            "episodes": episodes,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "scenario_schedule": [
                {"id": p.id, "episodes": p.episodes}
                for p in scenario_schedule
            ],
            "rl_sides": rl_sides,
            "models": all_models,
            "train_config_path": str(train_config_path),
        },
        "by_side_and_scenario": all_reports,
        "comparison": comparison_rows,
    }
    out_name = f"metrics_sb3_report_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved multi-side SB3 report -> {out_name}")


if __name__ == "__main__":
    evaluate_sb3()

